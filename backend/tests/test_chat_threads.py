import asyncio
import json
from datetime import timedelta
from uuid import uuid4

import pytest

from app.domain import ChatThread
from app.services import chat_threads_service
from app.services.llm import LLMBudgetExceeded

EVERY_DAY = {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]}
GOOD_CHAT = json.dumps({
    "answer": "Gym held on Wednesday. Only one day is logged so far, so there's no pattern to read yet.",
    "next_step": "Log tomorrow's check-in so a second day exists.",
    "cited_days": ["2026-12-30"],
})


def _habit(c, name="Gym"):
    r = c.post("/habits", json={"name": name, "target_frequency": EVERY_DAY})
    assert r.status_code == 201
    return r.json()["id"]


def _seed_data(c):
    hid = _habit(c)
    c.post(f"/habits/{hid}/logs", json={"log_date": "2026-12-30", "status": "done"})
    return hid


# ============================================================ chat threads
def test_first_message_creates_a_thread_and_stores_both_turns(world, user_a):
    c = world.client_as(user_a)
    r = c.post("/chat/messages", json={"message": "how am I doing?"})
    assert r.status_code == 200
    body = r.json()
    assert body["thread"]["title"] == "how am I doing?" and body["thread"]["message_count"] == 2
    assert body["user_message"]["role"] == "user" and body["reply"]["role"] == "assistant"
    assert body["reply"]["mode"] == "no_data"  # nothing logged yet: no model call
    listing = c.get("/chat/threads").json()
    assert [t["id"] for t in listing] == [body["thread"]["id"]] and listing[0]["message_count"] == 2
    detail = c.get(f"/chat/threads/{body['thread']['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"] and detail["has_more"] is False


def test_follow_up_loads_stored_history_server_side(world, user_a):
    c = world.client_as(user_a)
    _seed_data(c)
    world.llm.replies = [GOOD_CHAT, GOOD_CHAT]
    first = c.post("/chat/messages", json={"message": "why do I keep failing at gym?"}).json()
    world.now += timedelta(minutes=1)
    c.post("/chat/messages", json={"message": "and sleep?", "thread_id": first["thread"]["id"]})
    sent = world.llm.calls[1][0]
    contents = [m["content"] for m in sent]
    assert "<user_question>why do I keep failing at gym?</user_question>" in contents
    assert any(m["role"] == "assistant" and m["content"].startswith("Gym held on Wednesday") for m in sent)
    assert sent[-1]["content"] == "<user_question>and sleep?</user_question>"


def test_everything_free_text_is_encrypted_at_rest(world, user_a):
    c = world.client_as(user_a)
    c.post("/chat/messages", json={"message": "a very private worry about exams"})
    stored = list(world.chat_repo.messages.values())
    assert stored and all(b"private worry" not in m.content_encrypted for m in stored)
    assert all(b"private worry" not in t.title_encrypted for t in world.chat_repo.threads.values())


def test_crisis_thread_gets_a_neutral_title_support_reply_and_stays_latched(world, user_a):
    c = world.client_as(user_a)
    _seed_data(c)
    first = c.post("/chat/messages", json={"message": "I want to die"}).json()
    assert first["reply"]["mode"] == "support" and first["support"]["resources"]
    assert first["thread"]["title"] == "Conversation"
    assert world.llm.calls == []
    world.now += timedelta(minutes=1)
    follow = c.post(
        "/chat/messages", json={"message": "ok what about gym", "thread_id": first["thread"]["id"]}
    ).json()
    assert follow["reply"]["mode"] == "support" and world.llm.calls == []  # the stored history latches it
    detail = c.get(f"/chat/threads/{first['thread']['id']}").json()
    assert detail["support"] is not None


def test_threads_are_private_to_their_owner(world, user_a, user_b):
    tid = world.client_as(user_a).post("/chat/messages", json={"message": "hello there"}).json()["thread"]["id"]
    other = world.client_as(user_b)
    assert other.get(f"/chat/threads/{tid}").status_code == 404
    assert other.post("/chat/messages", json={"message": "hi", "thread_id": tid}).status_code == 404
    assert other.patch(f"/chat/threads/{tid}", json={"title": "mine now"}).status_code == 404
    assert other.delete(f"/chat/threads/{tid}").status_code == 404
    assert other.get("/chat/threads").json() == []


def test_rename_delete_and_delete_all(world, user_a):
    c = world.client_as(user_a)
    t1 = c.post("/chat/messages", json={"message": "first one"}).json()["thread"]["id"]
    c.post("/chat/messages", json={"message": "second one"})
    assert c.patch(f"/chat/threads/{t1}", json={"title": " Exam <b>plan</b> "}).json()["title"] == "Exam bplan/b"
    assert c.delete(f"/chat/threads/{t1}").status_code == 204
    assert c.delete(f"/chat/threads/{t1}").status_code == 404
    assert c.delete("/chat/threads").json() == {"deleted": 1}
    assert c.get("/chat/threads").json() == []
    assert world.chat_repo.messages == {}  # messages go with their threads


def test_a_full_thread_is_rejected(world, user_a, monkeypatch):
    monkeypatch.setattr(chat_threads_service, "MAX_MESSAGES_PER_THREAD", 2)
    c = world.client_as(user_a)
    tid = c.post("/chat/messages", json={"message": "one"}).json()["thread"]["id"]
    assert c.post("/chat/messages", json={"message": "two", "thread_id": tid}).status_code == 422


def test_idle_threads_are_pruned_after_the_retention_window(world, user_a):
    old = world.now - timedelta(days=120)
    asyncio.run(
        world.chat_repo.create_thread(
            ChatThread(
                id=uuid4(),
                user_id=user_a,
                created_at=old,
                last_message_at=old,
                title_encrypted=None,
            )
        )
    )
    assert world.client_as(user_a).get("/chat/threads").json() == []


def test_a_blocked_reply_leaves_no_orphan_thread(world, user_a):
    c = world.client_as(user_a)
    _seed_data(c)
    world.llm.error = LLMBudgetExceeded("cap")
    assert c.post("/chat/messages", json={"message": "how is gym going?"}).status_code == 429
    assert world.chat_repo.threads == {} and world.chat_repo.messages == {}


def test_messages_paginate_with_a_cursor(world, user_a):
    c = world.client_as(user_a)
    tid = None
    for text in ("one", "two", "three"):
        world.now += timedelta(minutes=1)
        body = {"message": text, **({"thread_id": tid} if tid else {})}
        tid = c.post("/chat/messages", json=body).json()["thread"]["id"]
    page = c.get(f"/chat/threads/{tid}", params={"limit": 2}).json()
    assert [m["content"] for m in page["messages"]][0] == "three" and page["has_more"] is True
    older = c.get(
        f"/chat/threads/{tid}", params={"limit": 2, "before": page["messages"][0]["created_at"]}
    ).json()
    assert older["messages"][0]["content"] == "two" and older["has_more"] is True


def test_blank_message_is_rejected(world, user_a):
    assert world.client_as(user_a).post("/chat/messages", json={"message": " "}).status_code == 422
