"""
Slice 11 -- AI tasks, reminders, nudges. Self-contained: in-memory fakes, no DB, no network, no pytest-asyncio
(async code is driven with asyncio.run so this file works under any asyncio mode).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.domain import NotificationPrefs, PushSubscription, Task
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.services import nudge_policy as policy
from app.services.llm import LLMUnavailableError
from app.services.notifications_service import NotificationsService
from app.services.push import PushOutcome, validate_endpoint
from app.services.task_parser import fallback_parse, parse_capture, validate
from app.services.task_time import parse_local, zone
from app.services.tasks_service import TasksService

UTC = timezone.utc
TZ = zone("Asia/Kolkata")
UID = uuid4()
# 2026-10-12 12:00 IST (06:30 UTC)
NOW = datetime(2026, 10, 12, 6, 30, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


def task(**kw) -> Task:
    base = dict(id=uuid4(), user_id=UID, title="Call Nani", created_at=NOW - timedelta(days=1))
    base.update(kw)
    return Task(**base)


def prefs(**kw) -> NotificationPrefs:
    return NotificationPrefs(user_id=UID, **kw)


def local(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


# =============================================================== policy
def test_nothing_before_trigger_and_backlog_never_pushed():
    due_later = task(importance=3, due_at=NOW + timedelta(hours=3))
    backlog = task(importance=3)
    assert policy.plan_pushes([due_later, backlog], NOW, prefs(), TZ) == []
    assert policy.classify(backlog, NOW, prefs(), TZ) == "backlog"
    assert policy.classify(due_later, NOW, prefs(), TZ) == "upcoming"


def test_due_task_pushes_once_then_backs_off_then_goes_stale():
    t = task(importance=2, due_at=NOW - timedelta(minutes=5))
    first = policy.plan_pushes([t], NOW, prefs(), TZ)
    assert len(first) == 1 and first[0].body == "Due now" and not first[0].digest

    # simulate the nudge having been delivered
    t.nudge_count, t.last_nudged_at = 1, NOW
    assert policy.plan_pushes([t], NOW + timedelta(hours=1), prefs(), TZ) == []          # backing off
    assert policy.min_gap(t) == timedelta(hours=12)                                       # 6h * 2**1
    again = policy.plan_pushes([t], NOW + timedelta(hours=21), prefs(), TZ)    # 09:00 IST next day, past the 12h gap
    assert again and again[0].body.startswith("Still open")

    # after the max nudges it stops pushing, and only goes "stale" after one more full gap with no action
    t.nudge_count, t.last_nudged_at = policy.MAX_NUDGES[2], NOW
    assert policy.classify(t, NOW + timedelta(hours=1), prefs(), TZ) == "due"
    later = NOW + policy.min_gap(t) + timedelta(minutes=1)
    assert policy.classify(t, later, prefs(), TZ) == "stale"
    assert policy.plan_pushes([t], later, prefs(), TZ) == []


def test_quiet_hours_wrap_midnight_and_block_pushes():
    assert policy.in_quiet_hours(time(23, 0), time(22, 0), time(8, 0))
    assert policy.in_quiet_hours(time(7, 59), time(22, 0), time(8, 0))
    assert not policy.in_quiet_hours(time(8, 0), time(22, 0), time(8, 0))
    assert not policy.in_quiet_hours(time(12, 0), time(9, 0), time(9, 0))               # equal = no quiet hours
    t = task(importance=3, due_at=NOW - timedelta(hours=2))
    night = datetime(2026, 10, 12, 17, 30, tzinfo=UTC)                                    # 23:00 IST
    assert policy.plan_pushes([t], night, prefs(), TZ) == []
    assert policy.plan_pushes([t], NOW, prefs(), TZ)                                      # 12:00 IST is fine


def test_small_things_ride_one_digest_at_the_nudge_hour():
    chores = [task(title=n, importance=1, due_at=NOW - timedelta(hours=1)) for n in ("Call Nani", "Laundry", "Water plants")]
    assert policy.plan_pushes(chores, NOW, prefs(nudge_hour=18), TZ) == []                # 12:00 IST < 18:00
    evening = datetime(2026, 10, 12, 13, 0, tzinfo=UTC)                                   # 18:30 IST
    out = policy.plan_pushes(chores, evening, prefs(nudge_hour=18), TZ)
    assert len(out) == 1 and out[0].digest and out[0].title == "3 small things"
    assert "Laundry" in out[0].body and len(out[0].task_ids) == 3


def test_exact_reminder_on_a_small_thing_fires_on_its_own_then_joins_digest():
    t = task(title="Water plants", importance=1, remind_at=NOW - timedelta(minutes=1))
    out = policy.plan_pushes([t], NOW, prefs(nudge_hour=18), TZ)
    assert len(out) == 1 and not out[0].digest and out[0].body == "Reminder"
    t.nudge_count, t.last_nudged_at = 1, NOW - timedelta(hours=30)
    assert policy.plan_pushes([t], NOW, prefs(nudge_hour=18), TZ) == []                   # follow-ups wait for the digest hour


def test_pause_silences_everything_except_first_fire_of_an_exact_reminder():
    nudge = task(importance=3, due_at=NOW - timedelta(hours=2))
    reminder = task(title="Pills", importance=2, remind_at=NOW - timedelta(minutes=1))
    out = policy.plan_pushes([nudge, reminder], NOW, prefs(), TZ, paused=True)
    assert [m.title for m in out] == ["Pills"]


def test_too_many_singles_overflow_into_one_digest():
    ts = [task(title=f"T{i}", importance=3, due_at=NOW - timedelta(hours=1)) for i in range(5)]
    out = policy.plan_pushes(ts, NOW, prefs(), TZ)
    assert len([m for m in out if not m.digest]) == policy.MAX_SINGLES_PER_RUN
    digest = [m for m in out if m.digest]
    assert len(digest) == 1 and digest[0].title == "2 things open"


def test_date_only_due_triggers_at_the_nudge_hour_local():
    due, has_time = parse_local("2026-10-12", TZ)
    t = task(importance=2, due_at=due, due_has_time=has_time)
    assert policy.trigger_at(t, prefs(nudge_hour=18), TZ) == local(2026, 10, 12, 18)
    assert policy.classify(t, NOW, prefs(nudge_hour=18), TZ) == "upcoming"               # 12:00 IST
    assert policy.classify(t, datetime(2026, 10, 12, 13, 0, tzinfo=UTC), prefs(nudge_hour=18), TZ) == "due"


# =============================================================== parser
def _payload(*items) -> str:
    return json.dumps({"tasks": list(items)})


def test_validate_keeps_good_tasks_and_nulls_bad_fields():
    raw = _payload(
        {"title": "Call Nani.", "importance": 1, "due": None, "remind": None, "repeat_days": 3, "notes": None},
        {"title": "Submit report", "importance": 9, "due": "2026-10-16", "remind": "2026-10-16T09:00", "repeat_days": 0},
        {"title": "Bad date", "due": "2026-13-45", "remind": "2020-01-01T10:00"},
        {"title": "call nani"},                                   # duplicate of the first (case-insensitive)
        {"title": "   "}, {"nope": 1}, "junk",
    )
    out = validate(raw, NOW, TZ)
    assert [p.title for p in out] == ["Call Nani", "Submit report", "Bad date"]
    nani, report, bad = out
    assert nani.importance == 1 and nani.repeat_days == 3
    assert report.importance == 3 and report.repeat_days is None                          # clamped / rejected
    assert report.due_at == local(2026, 10, 16, 23, 59) and report.due_has_time is False
    assert report.remind_at == local(2026, 10, 16, 9, 0)
    assert bad.due_at is None and bad.remind_at is None                                   # nulled, never guessed


def test_validate_rejects_unusable_shapes_and_accepts_empty():
    assert validate("not json", NOW, TZ) is None
    assert validate(json.dumps(["a"]), NOW, TZ) is None
    assert validate(json.dumps({"tasks": "x"}), NOW, TZ) is None
    assert validate(json.dumps({"tasks": []}), NOW, TZ) == []


def test_validate_caps_task_count_and_strips_markup():
    raw = _payload(*({"title": f"<b>Task {i}</b>"} for i in range(40)))
    out = validate(raw, NOW, TZ)
    assert len(out) == 12 and out[0].title == "bTask 0/b"                                 # angle brackets removed


def test_date_only_remind_is_not_a_ping():
    out = validate(_payload({"title": "X", "remind": "2026-10-20"}), NOW, TZ)
    assert out[0].remind_at is None


class FakeLLM:
    model = "fake"

    def __init__(self, *replies, error: Exception | None = None):
        self.replies, self.error, self.calls = list(replies), error, 0

    async def complete(self, messages, *, max_tokens=512, temperature=0.3):
        self.calls += 1
        if self.error:
            raise self.error
        return self.replies.pop(0)


def test_parse_capture_retries_once_then_gives_up_and_falls_back_on_outage():
    llm = FakeLLM("garbage", "still garbage")
    assert run(parse_capture(llm, "x", NOW, TZ, "Asia/Kolkata")) is None and llm.calls == 2
    down = FakeLLM(error=LLMUnavailableError("down"))
    assert run(parse_capture(down, "x", NOW, TZ, "Asia/Kolkata")) is None and down.calls == 1
    good = FakeLLM("garbage", _payload({"title": "A"}))
    assert [p.title for p in run(parse_capture(good, "x", NOW, TZ, "Asia/Kolkata"))] == ["A"]


def test_fallback_keeps_the_persons_words_only():
    out = fallback_parse("call nani; wash clothes\n\n give laundry  \ncall nani")
    assert [p.title for p in out] == ["call nani", "wash clothes", "give laundry"]
    assert all(p.due_at is None and p.importance == 2 for p in out)


# =============================================================== fakes for services
class FakeTaskRepo:
    def __init__(self):
        self.rows: dict[UUID, Task] = {}

    async def create(self, t):
        self.rows[t.id] = replace(t)
        return t

    async def get(self, user_id, task_id):
        t = self.rows.get(task_id)
        return replace(t) if t and t.user_id == user_id else None

    async def list(self, user_id, status=None, limit=500):
        return [replace(t) for t in self.rows.values() if t.user_id == user_id and (status is None or t.status == status)]

    async def count_open(self, user_id):
        return len(await self.list(user_id, "open"))

    async def save(self, t, now):
        if t.id not in self.rows:
            return None
        self.rows[t.id] = replace(t)
        return replace(t)

    async def delete(self, user_id, task_id):
        t = self.rows.get(task_id)
        if t and t.user_id == user_id:
            del self.rows[task_id]
            return True
        return False


class FakeNotifRepo:
    def __init__(self, p: NotificationPrefs | None = None):
        self.prefs = p or NotificationPrefs(user_id=UID)
        self.subs: list[PushSubscription] = []
        self.conflict = False

    async def get_prefs(self, user_id):
        return replace(self.prefs)

    async def save_prefs(self, p, now):
        self.prefs = replace(p)
        return p

    async def list_subscriptions(self, user_id):
        return [replace(s) for s in self.subs]

    async def upsert_subscription(self, sub):
        if self.conflict:
            raise ConflictError("other account")
        self.subs = [s for s in self.subs if s.endpoint != sub.endpoint] + [sub]
        return sub

    async def delete_subscription(self, user_id, endpoint):
        n = len(self.subs)
        self.subs = [s for s in self.subs if s.endpoint != endpoint]
        return len(self.subs) < n

    async def delete_subscription_by_id(self, user_id, sub_id):
        self.subs = [s for s in self.subs if s.id != sub_id]

    async def set_fail_count(self, user_id, sub_id, fail_count):
        for s in self.subs:
            if s.id == sub_id:
                s.fail_count = fail_count


class FakeProfiles:
    def __init__(self, tz="Asia/Kolkata"):
        self.tz = tz

    async def get(self, user_id):
        return SimpleNamespace(timezone=self.tz)


class FakePauses:
    def __init__(self, active=False):
        self.active = active

    async def list_overlapping(self, user_id, start, end, global_only=False):
        return [object()] if self.active else []


class FakeSender:
    configured = True

    def __init__(self, outcome=PushOutcome.OK):
        self.outcome, self.sent = outcome, []

    async def send(self, sub, payload):
        self.sent.append((sub.endpoint, payload))
        return self.outcome


def make_tasks(llm=None, p=None, now=NOW):
    repo, notif = FakeTaskRepo(), FakeNotifRepo(p)
    svc = TasksService(repo, notif, FakeProfiles(), llm or FakeLLM(error=LLMUnavailableError("off")), lambda: now)
    return svc, repo, notif


# =============================================================== tasks service
def test_capture_creates_ai_tasks_with_cadence_default_and_skips_duplicates():
    llm = FakeLLM(_payload(
        {"title": "Call Nani", "importance": 1, "repeat_days": 3},
        {"title": "Laundry", "importance": 1},
        {"title": "Lab report", "importance": 3, "due": "2026-10-16T17:00"},
    ))
    svc, repo, _ = make_tasks(llm)
    res = run(svc.capture(UID, "call nani every few days, laundry, lab report friday 5pm"))
    assert res.mode == "parsed" and [v.task.title for v in res.tasks] == ["Call Nani", "Laundry", "Lab report"]
    nani = res.tasks[0].task
    # created at 12:00 IST, before the 18:00 nudge hour -> first due is today (date only)
    assert nani.due_has_time is False and nani.due_at == local(2026, 10, 12, 23, 59) and nani.repeat_days == 3
    assert res.tasks[1].state == "backlog" and res.tasks[2].due_local == "2026-10-16T17:00"
    assert all(v.task.ai_parsed for v in res.tasks)

    again = FakeLLM(_payload({"title": "call nani"}, {"title": "New thing"}))
    svc2 = TasksService(repo, FakeNotifRepo(), FakeProfiles(), again, lambda: NOW)
    res2 = run(svc2.capture(UID, "call nani and new thing"))
    assert res2.skipped_duplicates == 1 and [v.task.title for v in res2.tasks] == ["New thing"]


def test_capture_after_nudge_hour_starts_cadence_tomorrow():
    evening = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)   # 19:30 IST
    svc, _, _ = make_tasks(FakeLLM(_payload({"title": "Laundry", "importance": 1, "repeat_days": 4})), now=evening)
    t = run(svc.capture(UID, "laundry every 4 days")).tasks[0].task
    assert t.due_at == local(2026, 10, 13, 23, 59)


def test_capture_falls_back_honestly_when_model_is_down():
    svc, repo, _ = make_tasks()
    res = run(svc.capture(UID, "call nani; wash clothes"))
    assert res.mode == "fallback" and len(res.tasks) == 2 and not any(v.task.ai_parsed for v in res.tasks)
    assert len(repo.rows) == 2


def test_capture_crisis_text_stores_nothing_and_never_calls_the_model():
    llm = FakeLLM(_payload({"title": "x"}))
    svc, repo, _ = make_tasks(llm)
    res = run(svc.capture(UID, "i want to kill myself"))
    assert res.mode == "support" and res.support and not repo.rows and llm.calls == 0


def test_capture_blank_is_rejected():
    svc, _, _ = make_tasks()
    with pytest.raises(ValidationError):
        run(svc.capture(UID, "   <>  "))


def test_task_created_already_due_is_not_pushed_the_same_minute():
    svc, repo, _ = make_tasks(FakeLLM(_payload({"title": "Call dentist", "importance": 3, "due": "2026-10-12T09:00"})))
    t = run(svc.capture(UID, "call dentist today 9am")).tasks[0].task
    assert t.last_nudged_at == NOW
    assert policy.plan_pushes([t], NOW + timedelta(minutes=5), prefs(), TZ) == []


def test_complete_one_off_closes_and_is_idempotent():
    svc, repo, _ = make_tasks()
    v = run(svc.create(UID, "Pay bill", None, 3, "2026-10-14", None, None))
    done = run(svc.complete(UID, v.task.id))
    assert done.task.status == "done" and done.task.done_count == 1 and done.task.completed_at == NOW
    again = run(svc.complete(UID, v.task.id))
    assert again.task.done_count == 1


def test_complete_cadence_task_comes_due_again_counted_from_completion():
    svc, repo, _ = make_tasks()
    v = run(svc.create(UID, "Call Nani", None, 1, "2026-10-09", None, 3))   # was due 3 days ago
    t = repo.rows[v.task.id]
    t.nudge_count, t.last_nudged_at = 2, NOW - timedelta(hours=5)
    done = run(svc.complete(UID, v.task.id)).task
    assert done.status == "open" and done.done_count == 1 and done.last_done_at == NOW
    assert done.due_at == local(2026, 10, 15, 23, 59) and done.due_has_time is False   # +3 days from TODAY, not from the old due
    assert done.nudge_count == 0 and done.last_nudged_at is None


def test_reschedule_resets_backoff_and_reminder_must_be_future():
    svc, repo, _ = make_tasks()
    v = run(svc.create(UID, "Submit form", None, 3, "2026-10-10T10:00", None, None))
    repo.rows[v.task.id].nudge_count = 3
    out = run(svc.update(UID, v.task.id, {"due": "2026-10-20T10:00"}))
    assert out.task.nudge_count == 0 and out.state == "upcoming"
    with pytest.raises(ValidationError):
        run(svc.update(UID, v.task.id, {"remind": "2026-10-01T10:00"}))
    with pytest.raises(ValidationError):
        run(svc.update(UID, v.task.id, {"remind": "2026-10-20"}))                       # date only is not a ping
    cleared = run(svc.update(UID, v.task.id, {"due": None}))
    assert cleared.due_local is None and cleared.state == "backlog"


def test_snooze_hides_then_returns_and_validates_range():
    svc, repo, _ = make_tasks()
    v = run(svc.create(UID, "Email prof", None, 2, "2026-10-12T09:00", None, None))
    s = run(svc.snooze(UID, v.task.id, 60))
    assert s.state == "snoozed"
    with pytest.raises(ValidationError):
        run(svc.snooze(UID, v.task.id, 1))
    with pytest.raises(NotFoundError):
        run(svc.snooze(UID, uuid4(), 30))


def test_user_isolation_on_get_update_delete():
    svc, repo, _ = make_tasks()
    v = run(svc.create(UID, "Mine", None, 2, None, None, None))
    other = uuid4()
    for call in (lambda: svc.complete(other, v.task.id), lambda: svc.delete(other, v.task.id),
                 lambda: svc.update(other, v.task.id, {"title": "x"})):
        with pytest.raises(NotFoundError):
            run(call())


def test_focus_sections():
    svc, repo, _ = make_tasks()
    run(svc.create(UID, "Overdue big", None, 3, "2026-10-10T10:00", None, None))
    run(svc.create(UID, "Chore due", None, 1, "2026-10-11", None, None))
    run(svc.create(UID, "Later today", None, 2, "2026-10-12T20:00", None, None))
    run(svc.create(UID, "Someday", None, 2, None, None, None))
    f = run(svc.focus(UID))
    assert [v.task.title for v in f.now] == ["Overdue big"]
    assert [v.task.title for v in f.small] == ["Chore due"]
    assert [v.task.title for v in f.later_today] == ["Later today"]
    assert f.backlog_count == 1 and f.hidden_now == 0


# =============================================================== dispatch
def make_dispatch(*, tasks: list[Task], sender=None, p=None, paused=False, now=NOW):
    trepo, nrepo = FakeTaskRepo(), FakeNotifRepo(p)
    for t in tasks:
        trepo.rows[t.id] = replace(t)
    nrepo.subs = [PushSubscription(id=uuid4(), user_id=UID, endpoint="https://fcm.googleapis.com/fcm/send/abc123456789",
                                   p256dh="p" * 30, auth="a" * 12, created_at=NOW)]
    sender = sender or FakeSender()
    svc = NotificationsService(nrepo, trepo, FakePauses(paused), FakeProfiles(), sender,
                               ["fcm.googleapis.com"], lambda: now)
    return svc, trepo, nrepo, sender


def test_dispatch_sends_marks_tasks_and_counts_toward_the_daily_cap():
    t = task(importance=3, due_at=NOW - timedelta(minutes=10))
    svc, trepo, nrepo, sender = make_dispatch(tasks=[t])
    assert run(svc.dispatch(UID)).sent == 1
    saved = trepo.rows[t.id]
    assert saved.nudge_count == 1 and saved.last_nudged_at == NOW
    assert nrepo.prefs.pushes_sent == 1 and nrepo.prefs.pushes_sent_day == date(2026, 10, 12)
    assert sender.sent[0][1]["title"] == "Call Nani" and sender.sent[0][1]["body"] == "Due now"
    assert run(svc.dispatch(UID)).sent == 0                      # backing off: second run does nothing


def test_dispatch_respects_daily_cap_and_resets_on_a_new_day():
    ts = [task(title=f"T{i}", importance=3, due_at=NOW - timedelta(hours=1)) for i in range(3)]
    svc, trepo, nrepo, sender = make_dispatch(
        tasks=ts, p=NotificationPrefs(user_id=UID, max_per_day=2, pushes_sent_day=date(2026, 10, 12), pushes_sent=2),
    )
    res = run(svc.dispatch(UID))
    assert res.sent == 0 and res.reason == "daily cap reached" and not sender.sent
    nrepo.prefs.pushes_sent_day = date(2026, 10, 11)             # yesterday's count must not carry over
    assert run(svc.dispatch(UID)).sent == 2 and nrepo.prefs.pushes_sent == 2


def test_failed_send_does_not_advance_the_task_and_counts_a_failure():
    t = task(importance=3, due_at=NOW - timedelta(minutes=10))
    svc, trepo, nrepo, sender = make_dispatch(tasks=[t], sender=FakeSender(PushOutcome.FAILED))
    assert run(svc.dispatch(UID)).sent == 0
    assert trepo.rows[t.id].nudge_count == 0 and nrepo.subs[0].fail_count == 1


def test_gone_subscription_is_deleted():
    t = task(importance=3, due_at=NOW - timedelta(minutes=10))
    svc, trepo, nrepo, sender = make_dispatch(tasks=[t], sender=FakeSender(PushOutcome.GONE))
    run(svc.dispatch(UID))
    assert nrepo.subs == [] and trepo.rows[t.id].nudge_count == 0


def test_dispatch_skips_when_disabled_unconfigured_or_paused():
    t = task(importance=3, due_at=NOW - timedelta(minutes=10))
    svc, *_ = make_dispatch(tasks=[t], p=NotificationPrefs(user_id=UID, push_enabled=False))
    assert run(svc.dispatch(UID)).reason == "push disabled by user"
    off = FakeSender()
    off.configured = False
    svc, *_ = make_dispatch(tasks=[t], sender=off)
    assert run(svc.dispatch(UID)).reason == "push not configured"
    svc, _, _, sender = make_dispatch(tasks=[t], paused=True)
    assert run(svc.dispatch(UID)).sent == 0 and not sender.sent


# =============================================================== prefs + subscriptions
def test_prefs_validation_nudge_hour_cannot_sit_inside_quiet_hours():
    svc, *_ = make_dispatch(tasks=[])
    with pytest.raises(ValidationError):
        run(svc.update_prefs(UID, {"nudge_hour": 23}))                 # default quiet 22:00-08:00
    ok = run(svc.update_prefs(UID, {"nudge_hour": 20, "max_per_day": 6}))
    assert ok.nudge_hour == 20 and ok.max_per_day == 6


def test_subscribe_validates_endpoint_host_and_device_limit():
    svc, _, nrepo, _ = make_dispatch(tasks=[])
    good = "https://fcm.googleapis.com/fcm/send/xyz-123456789"
    run(svc.subscribe(UID, good, "p" * 30, "a" * 12, "UA"))
    assert any(s.endpoint == good for s in nrepo.subs)
    for bad in ("http://fcm.googleapis.com/x/yyyyyyyyyyyy", "https://evil.example.com/x/yyyyyyyyyyyy",
                "https://fcm.googleapis.com.evil.com/x/yyyyyy", "https://169.254.169.254/latest/meta-data",
                "https://user:pw@fcm.googleapis.com/x/yyyyyyyy", "https://fcm.googleapis.com:8443/x/yyyyyyyy"):
        with pytest.raises(ValidationError):
            run(svc.subscribe(UID, bad, "p" * 30, "a" * 12, None))


def test_validate_endpoint_accepts_known_push_services():
    suffixes = ["fcm.googleapis.com", "push.services.mozilla.com", "push.apple.com", "notify.windows.com"]
    for ok in ("https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/abc",
               "https://web.push.apple.com/QAbc", "https://wns2-par02p.notify.windows.com/w/?token=abc"):
        assert validate_endpoint(ok, suffixes) == ok


def test_send_test_requires_a_device():
    svc, _, nrepo, _ = make_dispatch(tasks=[])
    nrepo.subs = []
    with pytest.raises(ValidationError):
        run(svc.send_test(UID))
