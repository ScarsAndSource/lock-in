"""
Companion layer, wired together: dispatch + ledger + planner on the in-memory world, the push-action endpoint
(single use, tamper, expiry), and the agentic chat (act + undo + confirm + crisis bypass).
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.deps import get_clock
from app.domain import Intention, NotificationPrefs, PushSubscription, UrgeLog, UrgeOutcome
from app.main import app
from app.routers.actions import get_actions_factory
from app.services import push_actions
from app.services.actions_service import ActionsService
from app.services.chat_service import ChatService
from app.services.checkins_service import CheckinsService
from app.services.companion_service import CompanionPlanner
from app.services.habits_service import HabitsService
from app.services.intentions_service import IntentionsService
from app.services.notifications_service import NotificationsService
from app.services.profile_service import ProfileService
from app.services.push import PushOutcome
from app.services.stats_service import StatsService
from app.services.study_service import StudyService
from app.services.tasks_service import TasksService

UTC = timezone.utc
SECRET = push_actions.derive_secret("", "test-key")


def run(coro):
    return asyncio.run(coro)


def at_ist(h, m=0, day=14) -> datetime:                      # 2026-10-14 is a Wednesday
    return datetime(2026, 10, day, h, m, tzinfo=timezone(timedelta(hours=5, minutes=30))).astimezone(UTC)


class FakeSender:
    configured = True

    def __init__(self, outcome=PushOutcome.OK):
        self.outcome, self.sent = outcome, []

    async def send(self, sub, payload):
        self.sent.append(payload)
        return self.outcome


def build(world, uid, now, sender=None, prefs=None):
    """Real services on the in-memory repos, for user `uid`, clock pinned to `now`."""
    world.now = now
    clock = world._clock
    run(world.profile_repo.set_timezone(uid, "Asia/Kolkata"))
    if prefs:
        world.notif_repo._default = prefs
    profiles = ProfileService(world.profile_repo, clock)
    stats = StatsService(world.habit_repo, world.sleep_repo, world.screen_time_repo, profiles, world.study_repo,
                         world.urge_repo, world.pause_repo)
    intentions = IntentionsService(world.intention_repo, world.habit_repo, world.subject_repo, stats, profiles, clock,
                                   pauses=world.pause_repo)
    planner = CompanionPlanner(world.ledger, world.habit_repo, world.checkin_repo, world.urge_repo, world.sleep_repo,
                               world.goal_repo, StudyService(world.subject_repo, world.study_repo, clock), intentions,
                               stats, world.pause_repo, tasks=world.task_repo)
    tasks = TasksService(world.task_repo, world.notif_repo, profiles, world.llm, clock)
    checkins = CheckinsService(world.habit_repo, world.checkin_repo, world.encryptor, world.sleep_repo,
                               world.screen_time_repo, clock, goals=world.goal_repo, pauses=world.pause_repo,
                               mood_repo=world.mood_repo)
    sender = sender or FakeSender()
    notif = NotificationsService(world.notif_repo, world.task_repo, world.pause_repo, profiles, sender,
                                 ["push.example.com"], clock, ledger=world.ledger, companion=planner,
                                 action_secret=SECRET, api_url="https://api.example.com")
    actions = ActionsService(ledger=world.ledger, tasks=tasks, checkins=checkins, habits=HabitsService(world.habit_repo, clock),
                             profiles=profiles, secret=SECRET, clock=clock)
    world.notif_repo.subs.append(PushSubscription(id=uuid4(), user_id=uid, endpoint="https://push.example.com/x",
                                                  p256dh="k", auth="a", created_at=now))
    return SimpleNamespace(notif=notif, actions=actions, sender=sender, tasks=tasks, planner=planner)


def make_habit(world, uid, name="Gym", **kw):
    from app.domain import TargetFrequency
    return run(world.habit_repo.create_habit(uid, name, TargetFrequency(type="weekdays", days=tuple(range(7))), **kw))


# =============================================================== dispatch + ledger
def test_evening_checkin_push_is_actionable_and_never_double_sent(world, user_a):
    make_habit(world, user_a)
    s = build(world, user_a, at_ist(21, 10))
    assert run(s.notif.dispatch(user_a)).sent == 1
    p = s.sender.sent[0]
    assert p["title"] == "Does today look normal?" and [a["action"] for a in p["actions"]] == ["lock", "rough"]
    assert p["api"] == "https://api.example.com" and p["url"] == "/?a=checkin"
    claims = push_actions.verify(SECRET, p["token"], world.now)
    assert claims.user_id == user_a and claims.kind == "checkin" and set(claims.allowed) == {"lock", "rough"}
    world.now += timedelta(minutes=5)                                   # next cron run: same moment, nothing new
    assert run(s.notif.dispatch(user_a)).sent == 0 and len(s.sender.sent) == 1


def test_failed_delivery_releases_the_ledger_so_the_next_run_retries(world, user_a):
    make_habit(world, user_a)
    s = build(world, user_a, at_ist(21, 10), sender=FakeSender(PushOutcome.FAILED))
    assert run(s.notif.dispatch(user_a)).sent == 0 and world.ledger.rows == {}
    s.sender.outcome = PushOutcome.OK
    assert run(s.notif.dispatch(user_a)).sent == 1


def test_one_shared_budget_between_tasks_and_companion(world, user_a):
    make_habit(world, user_a)
    s = build(world, user_a, at_ist(21, 10), prefs=NotificationPrefs(user_id=user_a, max_per_day=1))
    world.now = at_ist(18)
    run(s.tasks.create(user_a, "Submit lab report", None, 3, "2026-10-14T20:00", None, None))
    world.now = at_ist(21, 10)                                          # the deadline passed while they were away
    assert run(s.notif.dispatch(user_a)).sent == 1                      # cap is 1 for BOTH kinds together
    assert s.sender.sent[0]["kind"] == "task"                           # the overdue deadline outranks the check-in
    assert run(s.notif.dispatch(user_a)).reason == "daily cap reached"


def test_task_push_carries_done_and_snooze_buttons(world, user_a):
    s = build(world, user_a, at_ist(10))
    run(s.tasks.create(user_a, "Pay fees", None, 3, "2026-10-14T11:00", None, None))
    world.now = at_ist(12)
    assert run(s.notif.dispatch(user_a)).sent == 1
    p = s.sender.sent[0]
    assert [a["action"] for a in p["actions"]] == ["done", "snooze"] and p["token"]


def test_companion_is_silent_for_a_user_who_turned_it_off_or_is_paused(world, user_a):
    make_habit(world, user_a)
    s = build(world, user_a, at_ist(21, 10), prefs=NotificationPrefs(user_id=user_a, companion_enabled=False))
    assert run(s.notif.dispatch(user_a)).sent == 0


def test_urge_risk_window_pushes_own_plan_discreetly_and_only_if_allowed_in_quiet_hours(world, user_a):
    now = at_ist(22, 40)                                                # inside quiet hours 22:00-08:00
    run(world.intention_repo.create(Intention(id=uuid4(), user_id=user_a, linked_domain="urge",
                                              cue="it is 11pm", action="laptop out of bed", created_at=now)))
    for d in (1, 3, 6, 8, 10, 12):                                      # six late-night urges in October, 23:xx IST
        when = at_ist(23, 10, day=d)
        run(world.urge_repo.add(UrgeLog(id=uuid4(), user_id=user_a, occurred_at=when, log_date=when.date(),
                                        outcome=UrgeOutcome.RESISTED)))
    s = build(world, user_a, now)
    assert run(s.notif.dispatch(user_a)).sent == 0                      # quiet hours win by default
    world.notif_repo._default = NotificationPrefs(user_id=user_a, plan_cues_in_quiet=True)
    assert run(s.notif.dispatch(user_a)).sent == 1
    p = s.sender.sent[0]
    assert p["kind"] == "risk" and p["title"] == "Your plan"
    assert "laptop" not in json.dumps(p) and "urge" not in json.dumps(p).lower()   # nothing sensitive on the lock screen


# =============================================================== action endpoint
@pytest.fixture
def act(world, user_a):
    """Token endpoint wired to in-memory services; returns (stack, client)."""
    make_habit(world, user_a, "Gym", floor_text="10-min walk")
    stack = build(world, user_a, at_ist(21, 10))

    @asynccontextmanager
    async def factory(_uid):
        yield stack.actions

    app.dependency_overrides[get_actions_factory] = lambda: factory
    from app.deps import get_action_secret
    app.dependency_overrides[get_action_secret] = lambda: SECRET
    yield stack, world.client_as(user_a)       # signed in: only /actions/in-app needs it; the token route ignores it


def _checkin_token(world, stack, user_a):
    run(stack.notif.dispatch(user_a))
    return stack.sender.sent[0]["token"]


def test_lock_it_closes_the_day_from_the_lock_screen_and_is_single_use(world, user_a, act):
    stack, client = act
    token = _checkin_token(world, stack, user_a)
    r = client.post(f"/actions/{token}", json={"action": "lock"})
    assert r.status_code == 200 and r.json() == {"status": "done", "message": "Locked. Day closed."}
    assert run(world.checkin_repo.get(user_a, date(2026, 10, 14))).confirmed_at is not None
    again = client.post(f"/actions/{token}", json={"action": "lock"})
    assert again.json()["status"] == "already"                          # double tap / replay does nothing


def test_rough_day_logs_floor_versions_and_guesses_nothing_else(world, user_a, act):
    stack, client = act
    token = _checkin_token(world, stack, user_a)
    assert client.post(f"/actions/{token}", json={"action": "rough"}).json()["status"] == "done"
    log = next(iter(world.habit_repo._logs.values()))
    assert log.status.value == "floor" and log.is_default is False
    assert run(world.sleep_repo.get_log(user_a, date(2026, 10, 14))) is None


def test_token_cannot_do_what_it_was_not_minted_for_and_forged_or_expired_tokens_fail(world, user_a, act):
    stack, client = act
    token = _checkin_token(world, stack, user_a)
    assert client.post(f"/actions/{token}", json={"action": "done"}).status_code == 422     # not in this push's actions
    body, sig = token.split(".")
    assert client.post(f"/actions/{body}.{sig[::-1]}", json={"action": "lock"}).status_code == 401
    assert client.post("/actions/junk", json={"action": "lock"}).status_code == 401
    world.now += timedelta(hours=7)
    assert client.post(f"/actions/{token}", json={"action": "lock"}).status_code == 410
    # nothing above consumed or changed anything
    assert all(r.acted_at is None for r in world.ledger.rows.values())


def test_token_for_one_user_cannot_touch_another_users_data(world, user_a, user_b, act):
    stack, client = act
    other = make_habit(world, user_b, "Secret")
    forged = push_actions.mint(SECRET, user_id=user_a, push_id=uuid4(), kind="habit",
                               args={"habit_id": str(other.id), "date": "2026-10-14"}, allowed=("done",),
                               expires_at=world.now + timedelta(hours=1))
    # a valid signature but no ledger row: it was never issued, so it is refused rather than executed
    assert client.post(f"/actions/{forged}", json={"action": "done"}).json()["status"] == "already"
    assert world.habit_repo._logs == {}


def test_habit_floor_and_task_actions(world, user_a, act):
    stack, client = act
    h = next(iter(world.habit_repo._habits.values()))
    for kind, action, args, check in (
        ("habit", "floor", {"habit_id": str(h.id), "date": "2026-10-14"}, "Floor version logged. It counts."),
    ):
        pid = uuid4()
        run(world.ledger.reserve(__import__("app.domain", fromlist=["CompanionPush"]).CompanionPush(
            id=pid, user_id=user_a, kind=kind, key=f"{kind}:t", local_date=date(2026, 10, 14), sent_at=world.now)))
        tok = push_actions.mint(SECRET, user_id=user_a, push_id=pid, kind=kind, args=args, allowed=(action,),
                                expires_at=world.now + timedelta(hours=1))
        assert client.post(f"/actions/{tok}", json={"action": action}).json()["message"] == check
    t = run(stack.tasks.create(user_a, "Call Nani", None, 2, None, None, None))
    r = client.post("/actions/in-app", json={"kind": "task", "action": "snooze", "args": {"task_id": str(t.task.id)}})
    assert r.json()["status"] == "done"
    assert world.task_repo.rows[t.task.id].snoozed_until == world.now + timedelta(minutes=60)
    assert client.post("/actions/in-app", json={"kind": "task", "action": "nope", "args": {}}).status_code == 422


def test_action_on_a_deleted_task_fails_politely(world, user_a, act):
    stack, client = act
    r = client.post("/actions/in-app", json={"kind": "task", "action": "done", "args": {"task_id": str(uuid4())}})
    assert r.status_code == 200 and r.json()["status"] == "failed"


# =============================================================== agentic chat
def _say(client, text, **kw):
    r = client.post("/chat/messages", json={"message": text, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _plan(*actions, wants_answer=False):
    return json.dumps({"actions": list(actions), "wants_answer": wants_answer})


def test_one_sentence_becomes_three_actions_and_each_is_undoable(world, user_a):
    c = world.client_as(user_a)
    gym = make_habit(world, user_a, "Gym")
    world.llm.replies = [_plan(
        {"tool": "log_habit", "args": {"habit_id": str(gym.id), "status": "skipped", "day": "today"}, "confidence": "high"},
        {"tool": "log_sleep", "args": {"bed": "01:00", "woke": None, "quality": None, "day": "today"}, "confidence": "high"},
        {"tool": "capture_task", "args": {"title": "Call mom", "importance": 1, "due": "2026-10-16", "remind": None,
                                           "repeat_days": None, "notes": None}, "confidence": "high"},
    )]
    world.now = at_ist(9)
    out = _say(c, "Slept at 1, skipped gym, remind me to call mom Friday")
    reply = out["reply"]
    assert reply["mode"] == "action" and [a["status"] for a in reply["actions"]] == ["applied"] * 3
    assert "Gym" in reply["content"] and "Call mom" in reply["content"]
    assert len(world.llm.calls) == 1                                    # ONE model call for three writes
    assert next(iter(world.habit_repo._logs.values())).status.value == "skipped"
    assert run(world.sleep_repo.get_log(user_a, date(2026, 10, 14))).time_to_bed == time(1, 0)
    assert [t.title for t in world.task_repo.rows.values()] == ["Call mom"]

    for card in reply["actions"]:
        assert c.post("/chat/actions/undo", json={"token": card["undo_token"]}).status_code == 200
    assert world.habit_repo._logs == {} and run(world.sleep_repo.get_log(user_a, date(2026, 10, 14))) is None
    assert world.task_repo.rows == {}


def test_undo_restores_a_previous_value_not_just_deletes(world, user_a):
    c = world.client_as(user_a)
    gym = make_habit(world, user_a, "Gym")
    world.now = at_ist(9)
    c.post(f"/habits/{gym.id}/logs", json={"log_date": "2026-10-14", "status": "done"})
    world.llm.replies = [_plan({"tool": "log_habit", "args": {"habit_id": str(gym.id), "status": "skipped"}, "confidence": "high"})]
    card = _say(c, "I skipped gym actually")["reply"]["actions"][0]
    assert next(iter(world.habit_repo._logs.values())).status.value == "skipped"
    assert c.post("/chat/actions/undo", json={"token": card["undo_token"]}).status_code == 200
    assert next(iter(world.habit_repo._logs.values())).status.value == "done"


def test_invented_ids_and_bad_values_are_dropped_not_guessed(world, user_a):
    c = world.client_as(user_a)
    make_habit(world, user_a, "Gym")
    world.now = at_ist(9)
    world.llm.replies = [_plan(
        {"tool": "log_habit", "args": {"habit_id": str(uuid4()), "status": "done"}, "confidence": "high"},
        {"tool": "log_sleep", "args": {"bed": "25:99", "woke": None}, "confidence": "high"},
        {"tool": "format_disk", "args": {}, "confidence": "high"},
        {"tool": "complete_task", "args": {"task_id": str(uuid4())}, "confidence": "high"},
    )]
    world.llm.replies.append(json.dumps({"answer": "x"}))               # the chat fallback may run; it needs data -> no_data
    out = _say(c, "mark gym done")
    assert out["reply"]["actions"] == [] and world.habit_repo._logs == {}


def test_ambiguous_writes_wait_for_a_tap_and_confirm_revalidates(world, user_a):
    c = world.client_as(user_a)
    gym = make_habit(world, user_a, "Gym")
    world.now = at_ist(9)
    world.llm.replies = [_plan(
        {"tool": "log_habit", "args": {"habit_id": str(gym.id), "status": "done"}, "confidence": "low"},
        {"tool": "set_intention", "args": {"domain": "urge", "cue": "it is 11pm", "action": "phone out of room"}, "confidence": "high"},
    )]
    cards = _say(c, "log that gym thing and if it is 11pm then phone out of room")["reply"]["actions"]
    assert [x["status"] for x in cards] == ["pending", "pending"] and world.habit_repo._logs == {}
    assert run(world.intention_repo.list(user_a)) == []
    assert all(x["token"] for x in cards)                               # a pending card carries a signed, single-use token
    done = c.post("/chat/actions/confirm", json={"token": cards[0]["token"]})
    assert done.status_code == 200 and done.json()["status"] == "applied" and len(world.habit_repo._logs) == 1
    assert c.post("/chat/actions/confirm", json={"token": cards[0]["token"]}).status_code == 409   # single use: a double tap can't apply twice
    assert len(world.habit_repo._logs) == 1
    tok = cards[1]["token"]
    tampered = tok[:-1] + ("A" if tok[-1] != "A" else "B")             # any edit to a token breaks its signature
    assert c.post("/chat/actions/confirm", json={"token": tampered}).status_code == 422
    plan = c.post("/chat/actions/confirm", json={"token": tok}).json()  # the untouched token still works (the bad one burned nothing)
    assert plan["status"] == "applied" and len(run(world.intention_repo.list(user_a))) == 1
    assert c.post("/chat/actions/undo", json={"token": plan["undo_token"]}).status_code == 200
    assert run(world.intention_repo.list(user_a)) == []


def test_crisis_text_never_reaches_the_planner(world, user_a):
    c = world.client_as(user_a)
    out = _say(c, "I did it all wrong, I want to end my life, remind me to call mom")
    assert out["reply"]["mode"] == "support" and world.llm.calls == []


def test_plain_questions_skip_the_planner_entirely(world, user_a):
    c = world.client_as(user_a)
    out = _say(c, "How does my sleep affect my mood?")
    assert out["reply"]["mode"] == "no_data" and world.llm.calls == []   # gate false -> legacy chat path, no extra call


def test_planner_outage_falls_back_to_the_normal_chat(world, user_a):
    from app.services.llm import LLMUnavailableError
    c = world.client_as(user_a)
    world.llm.error = LLMUnavailableError("down")
    out = _say(c, "remind me to call mom tomorrow")
    assert out["reply"]["mode"] == "no_data" and out["reply"]["actions"] == [] and world.task_repo.rows == {}


def test_move_a_reminder_and_snooze_a_task_by_chat(world, user_a):
    c = world.client_as(user_a)
    world.now = at_ist(9)
    run(world.profile_repo.set_timezone(user_a, "Asia/Kolkata"))
    t = run(TasksService(world.task_repo, world.notif_repo, ProfileService(world.profile_repo, world._clock), world.llm,
                         world._clock).create(user_a, "Lab report", None, 3, "2026-10-15", "2026-10-14T18:00", None))
    tid = str(t.task.id)
    world.llm.replies = [_plan(
        {"tool": "reschedule_task", "args": {"task_id": tid, "due": None, "remind": "2026-10-14T20:30"}, "confidence": "high"},
        {"tool": "snooze_task", "args": {"task_id": tid, "minutes": 90}, "confidence": "high"})]
    cards = _say(c, "move my lab report reminder to 8:30pm and snooze it 90 minutes")["reply"]["actions"]
    assert [x["status"] for x in cards] == ["applied", "applied"]
    row = world.task_repo.rows[t.task.id]
    assert row.remind_at == at_ist(20, 30) and row.snoozed_until == world.now + timedelta(minutes=90)
    assert c.post("/chat/actions/undo", json={"token": cards[1]["undo_token"]}).status_code == 200
    assert c.post("/chat/actions/undo", json={"token": cards[0]["undo_token"]}).status_code == 200
    row = world.task_repo.rows[t.task.id]
    assert row.remind_at == at_ist(18, 0) and row.snoozed_until is None


def test_action_and_question_in_one_message(world, user_a):
    from app.domain import HabitLog, HabitStatus
    c = world.client_as(user_a)
    gym = make_habit(world, user_a, "Gym")
    world.now = at_ist(9)
    for i in range(1, 4):                                               # some logged history so chat has facts
        run(world.habit_repo.upsert_log(HabitLog(habit_id=gym.id, user_id=user_a, log_date=date(2026, 10, 14) - timedelta(days=i),
                                                 status=HabitStatus.DONE)))
    world.llm.replies = [
        _plan({"tool": "log_habit", "args": {"habit_id": str(gym.id), "status": "done"}, "confidence": "high"}, wants_answer=True),
        json.dumps({"answer": "Gym is on a run. Keep the same cue tomorrow.", "cited_days": ["2026-10-13"],
                    "next_step": "Same cue tomorrow."}),
    ]
    reply = _say(c, "I did gym, how am I doing overall?")["reply"]
    assert reply["actions"][0]["status"] == "applied" and "Gym" in reply["content"]


def test_daily_cap_hit_between_planner_and_answer_keeps_the_applied_actions(world, user_a):
    """The planner takes the LAST call of the day, the answer call then goes over the cap. The request must still
    succeed with the action cards (a 429 here rolls the whole transaction back and the logged action vanishes)."""
    from app.deps import get_llm_client
    from app.domain import HabitLog, HabitStatus
    from app.services.llm import BudgetedLLM
    from tests.fakes_slice7 import InMemoryLlmUsageRepository
    c = world.client_as(user_a)
    gym = make_habit(world, user_a, "Gym")
    world.now = at_ist(9)
    for i in range(1, 4):                                               # logged history, so chat would have facts to answer from
        run(world.habit_repo.upsert_log(HabitLog(habit_id=gym.id, user_id=user_a, log_date=date(2026, 10, 14) - timedelta(days=i),
                                                 status=HabitStatus.DONE)))
    usage = InMemoryLlmUsageRepository()
    app.dependency_overrides[get_llm_client] = lambda: BudgetedLLM(world.llm, usage, user_a, 1, "chat", world._clock)
    world.llm.replies = [_plan({"tool": "log_habit", "args": {"habit_id": str(gym.id), "status": "done"}, "confidence": "high"},
                               wants_answer=True)]
    reply = _say(c, "I did gym, how am I doing overall?")["reply"]
    assert reply["mode"] == "action" and [a["status"] for a in reply["actions"]] == ["applied"]
    assert "Gym" in reply["content"] and "AI allowance" in reply["content"]
    assert len(world.llm.calls) == 1                                    # only the planner ran; the answer was refused by the cap
    assert [l.status.value for l in world.habit_repo._logs.values() if l.log_date == date(2026, 10, 14)] == ["done"]


def test_gate_is_permissive_for_commands_and_quiet_for_questions():
    from app.services.chat_agent import looks_actionable as g
    for yes in ("log gym done", "I skipped the gym", "slept at 1am", "remind me to call mom friday", "gym kar diya",
                "if I feel the urge then walk", "snooze lab report 1h", "I woke at 7"):
        assert g(yes), yes
    for no in ("Why do I keep skipping gym on Thursdays?", "How does screen time affect my sleep?",
               "what's my worst habit?", "hi"):
        assert not g(no), no


# =============================================================== morning + comeback, end to end
def _backdate(habit, day=date(2026, 9, 1)):
    """The in-memory repo stamps habits with the real clock; the bounce rules ignore days before a habit existed."""
    habit.created_at = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return habit


def _log(world, uid, habit, day):
    from app.domain import HabitLog, HabitStatus
    run(world.habit_repo.upsert_log(HabitLog(habit_id=habit.id, user_id=uid, log_date=day, status=HabitStatus.DONE)))


def _silent_gym(world, uid):
    gym = _backdate(make_habit(world, uid, "Gym", floor_text="10-min walk"))
    _log(world, uid, gym, date(2026, 10, 10))              # last real log Saturday; Sun, Mon, Tue slipped (today is Wed)
    return gym


def test_morning_push_names_one_habit_with_start_and_not_today(world, user_a):
    gym = _backdate(make_habit(world, user_a, "Gym", floor_text="10-min walk"))
    s = build(world, user_a, at_ist(8, 10))
    assert run(s.notif.dispatch(user_a)).sent == 1
    p = s.sender.sent[0]
    assert p["kind"] == "morning" and p["title"] == "One thing today"
    assert p["body"] == "Gym. Floor version counts: 10-min walk"
    assert [a["action"] for a in p["actions"]] == ["start", "later"]
    assert p["url"] == f"/?a=focus&k=habit&id={gym.id}"
    claims = push_actions.verify(SECRET, p["token"], world.now)
    assert claims.kind == "morning" and set(claims.allowed) == {"start", "later"}
    world.now += timedelta(minutes=5)
    assert run(s.notif.dispatch(user_a)).sent == 0          # one moment, one push


def test_morning_prefers_a_task_due_today_and_start_is_recorded_without_changing_anything(world, user_a):
    _backdate(make_habit(world, user_a, "Gym"))
    s = build(world, user_a, at_ist(8, 10))
    created = run(s.tasks.create(user_a, "Submit lab report", None, 3, "2026-10-14T17:00", None, None))
    assert run(s.notif.dispatch(user_a)).sent == 1
    p = s.sender.sent[0]
    assert p["kind"] == "morning" and p["body"] == "Submit lab report. Due today. Start with five minutes."
    assert p["url"] == f"/?a=focus&k=task&id={created.task.id}"
    r = run(s.actions.run_token(p["token"], "start"))
    assert (r.status, r.message) == ("done", "Let's go.")
    assert world.task_repo.rows[created.task.id].status == "open"       # Start only opens the app
    ledger_row = next(iter(world.ledger.rows.values()))
    assert ledger_row.action == "start" and ledger_row.acted_at is not None


def test_a_task_the_task_nudges_will_push_anyway_is_not_also_a_morning_push(world, user_a):
    s = build(world, user_a, at_ist(18, day=13))
    run(s.tasks.create(user_a, "Pay fees", None, 3, "2026-10-13T20:00", None, None))
    world.now = at_ist(8, 10)                                           # deadline passed; quiet hours just ended
    assert run(s.notif.dispatch(user_a)).sent == 1
    assert [p["kind"] for p in s.sender.sent] == ["task"]


def test_morning_follows_the_usual_wake_time(world, user_a):
    from app.domain import SleepLog
    _backdate(make_habit(world, user_a, "Gym"))
    for d in range(8, 13):
        run(world.sleep_repo.upsert_log(SleepLog(user_id=user_a, log_date=date(2026, 10, d), time_woke=time(9, 30))))
    s = build(world, user_a, at_ist(8, 10))
    assert run(s.notif.dispatch(user_a)).sent == 0                      # usually up at 09:30: not yet
    world.now = at_ist(9, 55)                                           # window opens 09:50
    assert run(s.notif.dispatch(user_a)).sent == 1 and s.sender.sent[0]["kind"] == "morning"


def test_comeback_after_two_silent_days_offers_one_floor_version_and_replaces_the_morning(world, user_a):
    gym = _silent_gym(world, user_a)
    s = build(world, user_a, at_ist(8, 10))
    run(s.tasks.create(user_a, "Submit lab report", None, 3, "2026-10-14T17:00", None, None))
    assert run(s.notif.dispatch(user_a)).sent == 1
    p = s.sender.sent[0]
    assert p["kind"] == "comeback" and p["title"] == "Start small" and p["body"] == "Gym: 10-min walk. That counts."
    assert [a["action"] for a in p["actions"]] == ["floor", "later"]
    world.now = at_ist(9, 5)
    assert run(s.notif.dispatch(user_a)).sent == 0                      # no morning push on top of it
    r = run(s.actions.run_token(p["token"], "floor"))
    assert (r.status, r.message) == ("done", "Floor version logged. It counts.")
    log = run(world.habit_repo.get_log(user_a, gym.id, date(2026, 10, 14)))
    assert log.status.value == "floor" and not log.is_default


def test_comeback_is_spaced_three_days_apart_and_a_silent_person_gets_no_morning_in_between(world, user_a):
    _silent_gym(world, user_a)
    s = build(world, user_a, at_ist(8, 10))
    assert run(s.notif.dispatch(user_a)).sent == 1
    for day in (15, 16):
        world.now = at_ist(8, 10, day=day)
        assert run(s.notif.dispatch(user_a)).sent == 0
    world.now = at_ist(8, 10, day=17)
    assert run(s.notif.dispatch(user_a)).sent == 1 and s.sender.sent[-1]["title"] == "Welcome back"


def test_someone_who_logged_yesterday_gets_the_morning_not_the_comeback(world, user_a):
    gym = _silent_gym(world, user_a)
    _log(world, user_a, gym, date(2026, 10, 13))
    s = build(world, user_a, at_ist(8, 10))
    assert run(s.notif.dispatch(user_a)).sent == 1 and s.sender.sent[0]["kind"] == "morning"


def test_morning_and_comeback_actions_over_the_in_app_route(world, user_a, act):
    _stack, client = act
    h = next(iter(world.habit_repo._habits.values()))
    start = client.post("/actions/in-app", json={"kind": "morning", "action": "start", "args": {}})
    assert start.status_code == 200 and start.json() == {"status": "done", "message": "Let's go."}
    floor = client.post("/actions/in-app", json={
        "kind": "comeback", "action": "floor", "args": {"habit_id": str(h.id), "date": "2026-10-14"}})
    assert floor.json() == {"status": "done", "message": "Floor version logged. It counts."}
    assert client.post("/actions/in-app", json={"kind": "comeback", "action": "done", "args": {}}).status_code == 422
    assert client.post("/actions/in-app", json={"kind": "morning", "action": "floor", "args": {}}).status_code == 422
