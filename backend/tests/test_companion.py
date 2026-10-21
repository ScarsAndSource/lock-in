"""
Phase 2 -- the companion spine. Self-contained: pure functions plus in-memory fakes, no DB, no network, no
pytest-asyncio (async code is driven with asyncio.run so this file works under any asyncio mode).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.domain import NotificationPrefs, PushSubscription
from app.domain_companion import Observations
from app.exceptions import ValidationError
from app.services import companion_voice as voice
from app.services import rhythm as rh
from app.services.companion_service import CompanionNow, CompanionService
from app.services.moments_service import MomentsService
from app.services.next_action import (
    HabitFacts, NextInput, TaskFacts, candidates, pick_next,
)
from app.services.nudge_policy import PushMessage
from app.services.rhythm import Rhythm, RiskWindow, build_rhythm, circular_mean, moment_times, risk_windows, window_near

UID = uuid4()
UTC = timezone.utc


def run(coro):
    return asyncio.run(coro)


def at(h: int, m: int = 0) -> int:
    return h * 60 + m


NO_RHYTHM = Rhythm(None, None, None, None, (), 0, "low")


def habit(name="Gym", status=None, is_default=False, scheduled=True, floor=None, hid="h1") -> HabitFacts:
    return HabitFacts(hid, name, status, is_default, scheduled, floor)


def inp(**kw) -> NextInput:
    base = dict(
        habits=(), tasks=(), confirmed=False, bounce=False, local_minute=at(10), rhythm=NO_RHYTHM, tone="direct",
        plan=None, seed=7,
    )
    base.update(kw)
    return NextInput(**base)


# ------------------------------------------------------------------ circular mean
def test_circular_mean_wraps_midnight():
    # 23:50, 00:10, 00:00, 23:55 -> around midnight, not around noon
    got = circular_mean([at(23, 50), at(0, 10), at(0, 0), at(23, 55)])
    assert got is not None and (got >= at(23, 30) or got <= at(0, 30))


def test_circular_mean_needs_enough_consistent_data():
    assert circular_mean([at(7), at(7, 10), at(7, 5)]) is None                    # too few
    assert circular_mean([at(0), at(6), at(12), at(18), at(3), at(9)]) is None    # spread evenly: no rhythm
    assert circular_mean([at(7), at(7, 20), at(6, 50), at(7, 10)]) == pytest.approx(at(7, 5), abs=10)


# ------------------------------------------------------------------ risk windows
def test_risk_windows_empty_until_enough_urges():
    assert risk_windows([(at(23), True)] * 4) == ()


def test_risk_window_found_where_urges_cluster():
    urges = [(at(23, 10), False), (at(23, 40), True), (at(23, 20), False), (at(23, 50), False), (at(10), False),
             (at(23, 30), True)]
    windows = risk_windows(urges)
    assert len(windows) == 1
    w = windows[0]
    assert w.start <= at(23, 30) < (w.end if w.end > w.start else w.end + rh.DAY)
    assert 0 < w.weight <= 1


def test_risk_window_can_cross_midnight():
    urges = [(at(23, 40), True), (at(0, 10), True), (at(23, 50), False), (at(0, 20), False), (at(0, 0), False)]
    (w,) = risk_windows(urges)
    assert w.end < w.start   # wraps past midnight


def test_urges_spread_all_day_are_not_a_window():
    assert risk_windows([(h * 60, False) for h in range(0, 24, 2) for _ in range(1)] * 1) == ()


def test_window_near_covers_lead_and_inside():
    r = Rhythm(None, None, None, None, (RiskWindow(at(23), at(1), 0.8),), 10, "low")
    assert window_near(r, at(22, 40)) is not None      # within 30 min before
    assert window_near(r, at(23, 30)) is not None      # inside
    assert window_near(r, at(0, 30)) is not None       # inside, past midnight
    assert window_near(r, at(15)) is None


# ------------------------------------------------------------------ moment times
def test_moment_times_default_and_learned():
    d = moment_times(NO_RHYTHM, at(22), at(7))
    assert d == {"morning": at(8), "evening": at(20, 30)}
    learned = Rhythm(at(6, 30), None, at(22), None, (), 30, "medium")
    t = moment_times(learned, at(23), at(5))
    assert t["morning"] == at(7, 15) and t["evening"] == at(21, 30)


def test_moment_times_respect_quiet_hours():
    r = Rhythm(at(6, 30), None, at(22), None, (), 30, "medium")
    t = moment_times(r, at(21), at(8))     # quiet 21:00-08:00 swallows both
    assert t["morning"] == at(8, 15)
    assert t["evening"] == at(20)


def test_build_rhythm_confidence_grows_with_samples():
    small = build_rhythm(Observations(checkin_minutes=(at(22),) * 4))
    assert small.checkin == at(22) and small.confidence == "low"
    big = build_rhythm(Observations(checkin_minutes=(at(22),) * 70))
    assert big.confidence == "high"


# ------------------------------------------------------------------ next action
def test_floor_beats_everything_on_a_bounce_day():
    a = pick_next(inp(
        bounce=True, habits=(habit(status="floor", is_default=True, floor="10 min walk"),),
        tasks=(TaskFacts("t1", "Submit form", 3, "Due now"),),
    ))
    assert a.kind == "floor" and a.target.status == "floor" and "10 min walk" in (a.detail or "")


def test_deadline_beats_habit_and_then_habit_beats_plain_task():
    tasks = (TaskFacts("t1", "Submit form", 3, "Due now"), TaskFacts("t2", "Email Dr. Rao", 2, "Overdue"))
    assert pick_next(inp(tasks=tasks, habits=(habit(),), confirmed=True)).kind == "deadline"
    only_two = (TaskFacts("t2", "Email Dr. Rao", 2, "Overdue"),)
    assert pick_next(inp(tasks=only_two, habits=(habit(),), confirmed=True)).kind == "habit"


def test_close_takes_over_only_after_the_usual_checkin_time():
    before = pick_next(inp(local_minute=at(14)))
    assert before.kind == "checkin"
    r = Rhythm(None, None, at(22), None, (), 30, "medium")   # evening_at = 21:30
    assert pick_next(inp(local_minute=at(21, 29), rhythm=r)).kind == "checkin"
    assert pick_next(inp(local_minute=at(21, 30), rhythm=r)).kind == "close"


def test_guard_shows_the_persons_own_plan():
    r = Rhythm(None, None, None, None, (RiskWindow(at(23), at(1), 0.9),), 12, "low")
    a = pick_next(inp(rhythm=r, local_minute=at(22, 45), confirmed=True, plan="Phone goes on the charger in the hall"))
    assert a.kind == "guard" and a.detail == "Phone goes on the charger in the hall" and a.target.type == "urge"
    assert "11:00 PM" in (a.why or "")


def test_not_now_hides_exactly_that_key_and_exhaustion_is_all_clear():
    base = dict(confirmed=True, habits=(habit(),), tasks=(TaskFacts("t2", "Email", 2, None),))
    first = pick_next(inp(**base))
    assert first.kind == "habit"
    second = pick_next(inp(skipped=frozenset({first.key}), **base))
    assert second.kind == "task"
    done = pick_next(inp(skipped=frozenset({first.key, second.key}), **base))
    assert done.kind == "clear" and done.title == "Locked in." and done.cta is None


def test_unscheduled_and_proposed_habits_are_not_open():
    a = pick_next(inp(confirmed=True, habits=(habit(scheduled=False), habit(status="done", is_default=True, hid="h2"))))
    assert a.kind == "clear"


def test_candidates_are_ordered_by_score():
    c = candidates(inp(tasks=(TaskFacts("t1", "x", 3, None),), habits=(habit(),), local_minute=at(23)))
    scores = [s for s, _ in c]
    assert scores == sorted(scores, reverse=True)


# ------------------------------------------------------------------ voice
def test_voice_is_stable_within_a_day_and_varies_across_days():
    assert voice.card_voice("floor", "coach", 5) == voice.card_voice("floor", "coach", 5)
    lines = {voice.card_voice("floor", "direct", s) for s in range(3)}
    assert len(lines) == 3


def test_every_kind_has_both_tones_and_no_guilt_words():
    banned = ("lazy", "failed", "disappoint", "should have", "again?")
    for kind, tones in voice._CARD.items():
        assert set(tones) == {"direct", "coach"}
        for lines in tones.values():
            assert len(lines) == 3
            assert not any(b in line.lower() for line in lines for b in banned), kind


def test_moment_copy_and_clock_text():
    title, body = voice.moment_copy("evening", "coach", 1, "close", "Close today")
    assert title == "Close today" and body
    long_title = "x" * 200
    t, _ = voice.moment_copy("morning", "direct", 0, "task", long_title)
    assert len(t) == voice.TITLE_CHARS
    assert voice.clock_text(at(0, 5)) == "12:05 AM" and voice.clock_text(at(13, 30)) == "1:30 PM"


# ------------------------------------------------------------------ service: events
class FakeCompanionRepo:
    def __init__(self):
        self.events: list[tuple[str, str | None]] = []
        self.moments: dict[tuple[date, str], str] = {}

    async def add_event(self, user_id, kind, ref, now):
        self.events.append((kind, ref))

    async def observations(self, user_id, tz, now, days):
        return Observations()

    async def moments_today(self, user_id, day):
        return {m for (d, m) in self.moments if d == day}

    async def mark_moment(self, user_id, day, moment, outcome, now):
        if (day, moment) in self.moments:
            return False
        self.moments[(day, moment)] = outcome
        return True


def test_record_event_validates_kind_and_trims_ref():
    repo = FakeCompanionRepo()
    svc = CompanionService(repo, None, None, None, None)  # type: ignore[arg-type]
    run(svc.record_event(UID, "nba_shown", "  habit:abc  "))
    run(svc.record_event(UID, "app_open", None))
    assert repo.events == [("nba_shown", "habit:abc"), ("app_open", None)]
    with pytest.raises(ValidationError):
        run(svc.record_event(UID, "keystrokes", None))


# ------------------------------------------------------------------ service: moments tick
@dataclass
class FakeSender:
    configured: bool = True


class FakeNotifRepo:
    def __init__(self, prefs: NotificationPrefs, subs: int = 1):
        self.prefs, self.subs, self.saved = prefs, subs, 0

    async def get_prefs(self, user_id):
        return self.prefs

    async def list_subscriptions(self, user_id):
        return [object()] * self.subs

    async def save_prefs(self, prefs, now):
        self.prefs = prefs
        self.saved += 1
        return prefs


class FakeNotifications:
    def __init__(self, delivers=True):
        self.sent: list[PushMessage] = []
        self._ok = delivers

    async def deliver_text(self, user_id, msg):
        if self._ok:
            self.sent.append(msg)
        return self._ok


class FakeCompanion:
    def __init__(self, kind="habit", confirmed=False, minute=at(8, 10), rhythm=NO_RHYTHM):
        self._data = CompanionNow(
            action=pick_next(inp(habits=(habit(),) if kind == "habit" else (), confirmed=True)) if kind == "habit"
            else pick_next(inp(confirmed=True)),
            rhythm=rhythm, local_minute=minute, tone="direct", habits_done=0, habits_total=1, confirmed=confirmed,
            seed=7, today=date(2026, 10, 21),
        )

    async def now(self, user_id, skipped=()):
        return self._data


class FakePauses:
    def __init__(self, paused=False):
        self.paused = paused

    async def list_overlapping(self, *a, **k):
        return [object()] if self.paused else []


class FakeProfiles:
    async def get(self, user_id):
        return SimpleNamespace(timezone="Asia/Kolkata")


def prefs(**kw) -> NotificationPrefs:
    base = dict(user_id=UID, push_enabled=True, quiet_start=time(22), quiet_end=time(7), nudge_hour=18,
                max_per_day=4, pushes_sent_day=None, pushes_sent=0)
    base.update(kw)
    return NotificationPrefs(**base)


def ist(h: int, m: int = 0) -> datetime:
    """2026-10-21 h:m in IST as a UTC datetime."""
    return datetime(2026, 10, 21, tzinfo=UTC) + timedelta(minutes=h * 60 + m - 330)


def make(now: datetime, *, comp=None, pr=None, notif=None, paused=False, sender=None, repo=None, subs=1):
    repo = repo or FakeCompanionRepo()
    notif = notif or FakeNotifications()
    nrepo = FakeNotifRepo(pr or prefs(), subs)
    svc = MomentsService(
        repo, comp or FakeCompanion(), notif, nrepo, FakePauses(paused), FakeProfiles(), sender or FakeSender(),
        lambda: now,
    )
    return svc, repo, notif, nrepo


def test_morning_moment_sends_once_and_counts_toward_the_shared_budget():
    svc, repo, notif, nrepo = make(ist(8, 10))
    first = run(svc.tick(UID))
    assert first.sent and first.moment == "morning"
    assert notif.sent[0].tag == "moment-morning" and notif.sent[0].url == "/"
    assert nrepo.prefs.pushes_sent == 1 and nrepo.prefs.pushes_sent_day == date(2026, 10, 21)
    again = run(svc.tick(UID))                       # five minutes later: the same moment never repeats
    assert not again.sent and len(notif.sent) == 1


def test_nothing_concrete_means_silence_and_is_recorded():
    svc, repo, notif, _ = make(ist(8, 10), comp=FakeCompanion(kind="none"))
    r = run(svc.tick(UID))
    assert not r.sent and r.reason == "nothing to say" and notif.sent == []
    assert repo.moments[(date(2026, 10, 21), "morning")] == "skipped"


def test_evening_moment_deep_links_to_checkin_and_stays_quiet_when_day_is_closed():
    svc, _, notif, _ = make(ist(20, 40), comp=FakeCompanion(minute=at(20, 40)))
    r = run(svc.tick(UID))
    assert r.sent and r.moment == "evening" and notif.sent[0].url == "/?shortcut=checkin"
    svc2, _, notif2, _ = make(ist(20, 40), comp=FakeCompanion(minute=at(20, 40), confirmed=True))
    r2 = run(svc2.tick(UID))
    assert not r2.sent and notif2.sent == []


def test_a_late_cron_run_cannot_fire_a_stale_moment():
    svc, _, notif, _ = make(ist(15, 0), comp=FakeCompanion(minute=at(15)))
    r = run(svc.tick(UID))
    assert not r.sent and r.reason == "no moment due" and notif.sent == []


@pytest.mark.parametrize("kw,reason", [
    (dict(pr=prefs(push_enabled=False)), "push disabled by user"),
    (dict(pr=prefs(max_per_day=2, pushes_sent=2, pushes_sent_day=date(2026, 10, 21))), "daily cap reached"),
    (dict(paused=True), "paused"),
    (dict(sender=FakeSender(configured=False)), "push not configured"),
    (dict(subs=0), "no subscriptions"),
])
def test_guards_stop_the_companion(kw, reason):
    svc, _, notif, _ = make(ist(8, 10), **kw)
    r = run(svc.tick(UID))
    assert not r.sent and r.reason == reason and notif.sent == []


def test_quiet_hours_win():
    svc, _, notif, _ = make(ist(23, 0), comp=FakeCompanion(minute=at(23)))
    r = run(svc.tick(UID))
    assert not r.sent and r.reason == "quiet hours" and notif.sent == []


def test_yesterdays_counter_resets_but_a_full_budget_today_does_not():
    stale = prefs(pushes_sent=4, pushes_sent_day=date(2026, 10, 20))
    svc, _, notif, nrepo = make(ist(8, 10), pr=stale)
    assert run(svc.tick(UID)).sent and nrepo.prefs.pushes_sent == 1


def test_failed_delivery_is_not_recorded_so_the_next_run_retries():
    svc, repo, _, nrepo = make(ist(8, 10), notif=FakeNotifications(delivers=False))
    r = run(svc.tick(UID))
    assert not r.sent and r.reason == "not delivered"
    assert repo.moments == {} and nrepo.saved == 0


# ------------------------------------------------------------------ HTTP layer (router + schemas, service stubbed)
def test_companion_routes_serialise_and_validate(world, user_a):
    from app.deps import get_companion_service
    from app.main import app

    class Stub:
        def __init__(self):
            self.events, self.skipped = [], None

        async def now(self, user_id, skipped=()):
            self.skipped = list(skipped)
            r = Rhythm(at(6, 30), at(23), at(22), at(7), (RiskWindow(at(23), at(1), 0.8),), 40, "medium")
            action = pick_next(inp(habits=(habit(floor="10 min"),), confirmed=False, rhythm=r, local_minute=at(10)))
            return CompanionNow(action, r, at(10), "coach", 1, 3, False, 7, date(2026, 10, 21))

        async def record_event(self, user_id, kind, ref):
            self.events.append((kind, ref))

    stub = Stub()
    app.dependency_overrides[get_companion_service] = lambda: stub
    client = world.client_as(user_a)

    res = client.get("/companion/now", params=[("skip", "habit:h0"), ("skip", "task:t9")])
    assert res.status_code == 200
    body = res.json()
    assert stub.skipped == ["habit:h0", "task:t9"]
    assert body["next_action"]["kind"] == "habit" and body["next_action"]["target"] == {
        "type": "habit", "habit_id": "h1", "status": "done", "task_id": None,
    }
    assert body["rhythm"]["wake"] == at(6, 30) and body["rhythm"]["windows"] == [
        {"start": at(23), "end": at(1), "weight": 0.8},
    ]
    assert body["tone"] == "coach" and body["habits_total"] == 3 and body["confirmed"] is False

    ok = client.post("/companion/events", json={"kind": "nba_shown", "ref": "habit:h1"})
    assert ok.status_code == 204 and stub.events == [("nba_shown", "habit:h1")]
    assert client.post("/companion/events", json={"kind": "keystrokes"}).status_code == 422
    assert client.post("/companion/events", json={"kind": "app_open", "ref": "x" * 81}).status_code == 422


# ------------------------------------------------------------------ SQL: compiles against the real dialect
def test_companion_repository_statements_compile_against_postgres():
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.ext.asyncio import AsyncSession
    from zoneinfo import ZoneInfo

    from app.models import CompanionMomentORM, EventORM
    from app.repositories.companion_repository import SqlAlchemyCompanionRepository, prune_events

    compiled: list[str] = []

    class Result:
        rowcount = 1

        def all(self):
            return []

        def scalars(self):
            return self

    session = AsyncSession()

    async def fake_execute(stmt, *a, **k):
        compiled.append(str(stmt.compile(dialect=postgresql.dialect())))
        return Result()

    async def fake_flush(*a, **k):
        return None

    session.execute = fake_execute  # type: ignore[method-assign]
    session.flush = fake_flush      # type: ignore[method-assign]
    added: list[object] = []
    session.add = added.append      # type: ignore[method-assign]

    repo = SqlAlchemyCompanionRepository(session)
    now = datetime(2026, 10, 21, 6, 0, tzinfo=UTC)
    obs = run(repo.observations(UID, ZoneInfo("Asia/Kolkata"), now, 60))
    assert obs == Observations()
    assert run(repo.mark_moment(UID, date(2026, 10, 21), "morning", "sent", now)) is True
    assert run(repo.moments_today(UID, date(2026, 10, 21))) == set()
    run(repo.add_event(UID, "app_open", None, now))
    run(prune_events(session, now))
    joined = "\n".join(compiled)
    assert "ON CONFLICT (user_id, moment_date, moment) DO NOTHING" in joined
    assert "sleep_logs.is_default IS false" in joined
    assert len(added) == 1 and isinstance(added[0], EventORM)
    assert {c.name for c in EventORM.__table__.columns} == {"id", "user_id", "ts", "kind", "ref", "meta"}
    assert {c.name for c in CompanionMomentORM.__table__.columns} == {
        "user_id", "moment_date", "moment", "outcome", "created_at",
    }
