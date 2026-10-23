"""
Companion layer, pure parts: risk windows, signed action tokens, and the companion push policy.
No DB, no network, no pytest-asyncio.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain import CompanionPush, NotificationPrefs
from app.services import companion_policy as cp
from app.services import push_actions as pa
from app.services import risk_windows as rw
from app.services.task_time import zone

UTC = timezone.utc
TZ = zone("Asia/Kolkata")
UID = uuid4()
# Tue 2026-10-13 21:10 IST
NOW = datetime(2026, 10, 13, 15, 40, tzinfo=UTC)


def ist(y, mo, d, h=0, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def prefs(**kw) -> NotificationPrefs:
    return NotificationPrefs(user_id=UID, **kw)


def habit(name="Gym", **kw) -> cp.OpenHabit:
    return cp.OpenHabit(habit_id=kw.pop("habit_id", uuid4()), name=name, **kw)


def ctx(now=NOW, **kw) -> cp.CompanionContext:
    kw.setdefault("prefs", prefs())
    return cp.CompanionContext(now=now, tz=TZ, **kw)


def row(kind, sent_at, *, acted=False, key=None, day=None) -> CompanionPush:
    local = sent_at.astimezone(TZ)
    return CompanionPush(
        id=uuid4(), user_id=UID, kind=kind, key=key or f"{kind}:{local.date().isoformat()}:{uuid4().hex[:4]}",
        local_date=day or local.date(), sent_at=sent_at, acted_at=sent_at if acted else None,
    )


# =============================================================== risk windows
def _urges(hour, days, minute=15, month=9):
    return [ist(2026, month, d, hour, minute).astimezone(UTC) for d in days]


def test_window_found_when_urges_cluster_in_one_hour():
    events = _urges(23, [1, 3, 8, 10]) + _urges(23, [2, 6], month=10) + _urges(14, [5])   # 6 at 23h, 1 stray
    out = rw.find_windows(events, TZ, NOW)
    assert len(out) == 1
    w = out[0]
    assert (w.start_hour, w.end_hour, w.events) == (23, 0, 6)           # the window closes past midnight
    assert w.recent_events >= 1 and len(w.weekdays) == 7                # < 8 events: weekdays are noise


def test_no_window_when_urges_are_spread_or_too_few():
    spread = [ist(2026, 9, 1 + i, (i * 3) % 24, 5).astimezone(UTC) for i in range(8)]
    assert rw.find_windows(spread, TZ, NOW) == []
    assert rw.find_windows(_urges(23, [1, 2, 3]), TZ, NOW) == []        # 3 < MIN_EVENTS


def test_one_bad_day_is_not_a_pattern():
    same_day = [ist(2026, 9, 5, 23, m).astimezone(UTC) for m in (0, 10, 20, 30, 40)]
    assert rw.find_windows(same_day, TZ, NOW) == []                     # 5 urges but only 1 distinct day


def test_window_fades_when_nothing_recent():
    old = _urges(23, [1, 3, 8, 10])                                      # all > 21 days before NOW (Oct 13)
    w = rw.find_windows(old, TZ, NOW)[0]
    assert w.recent_events == 0


def test_weekday_pattern_needs_enough_evidence():
    # 10 urges at 23h, all Tuesdays/Thursdays (Sep 1,8,15,22 are Tue; 3,10,17,24 Thu)
    days = [1, 8, 15, 22, 3, 10, 17, 24, 29, 24]
    w = rw.find_windows(_urges(23, days[:8]) + _urges(23, [22, 24]), TZ, NOW)[0]
    assert w.weekdays == frozenset({1, 3})


def test_runs_merge_across_midnight_and_long_runs_are_trimmed():
    events = _urges(23, [1, 3, 8, 10]) + _urges(0, [2, 4, 9, 11])        # 23h and 00h neighbours
    w = rw.find_windows(events, TZ, NOW)[0]
    assert (w.start_hour, w.end_hour, w.events) == (23, 1, 8)
    evening = sum((_urges(h, [1, 3, 8, 10]) for h in (19, 20, 21, 22, 23)), [])
    assert (rw.find_windows(evening, TZ, NOW)[0].end_hour - rw.find_windows(evening, TZ, NOW)[0].start_hour) <= 3


# =============================================================== action tokens
SECRET = pa.derive_secret("", "unit-test-key")


def _tok(**kw):
    base = dict(
        user_id=UID, push_id=uuid4(), kind="checkin", args={"date": "2026-10-13"}, allowed=("lock", "rough"),
        expires_at=NOW + timedelta(hours=6),
    )
    base.update(kw)
    return pa.mint(SECRET, **base), base


def test_token_roundtrip():
    token, b = _tok()
    c = pa.verify(SECRET, token, NOW)
    assert (c.user_id, c.push_id, c.kind, c.args, c.allowed) == (UID, b["push_id"], "checkin", b["args"], ("lock", "rough"))


def test_token_rejects_tampering_wrong_key_expiry_and_junk():
    token, _ = _tok()
    body, sig = token.split(".")
    for bad in (f"{body}x.{sig}", f"{body}.{sig[:-2]}ab", "nodot", "a.b.c", "", "é.é"):
        with pytest.raises(pa.ActionTokenError):
            pa.verify(SECRET, bad, NOW)
    with pytest.raises(pa.ActionTokenError) as e:
        pa.verify(pa.derive_secret("", "other-key"), token, NOW)
    assert e.value.code == "bad_signature"
    with pytest.raises(pa.ActionTokenError) as e:
        pa.verify(SECRET, token, NOW + timedelta(hours=7))
    assert e.value.code == "expired"


def test_explicit_secret_beats_derived_and_derived_is_stable():
    assert pa.derive_secret("abc", "k") == b"abc"
    assert pa.derive_secret("", "k") == pa.derive_secret("", "k") != pa.derive_secret("", "k2")


# =============================================================== companion policy
def test_checkin_push_fires_after_checkin_hour_and_offers_lock_and_rough():
    out = cp.plan_companion(ctx(open_habits=[habit("Gym"), habit("Reading"), habit("Water")]))
    assert len(out) == 1 and out[0].kind == "checkin"
    assert [a for a, _ in out[0].actions] == ["lock", "rough"]
    assert out[0].key == "checkin:2026-10-13" and "+1" in out[0].body


def test_checkin_silent_before_hour_when_confirmed_or_nothing_open():
    before = ist(2026, 10, 13, 16, 0).astimezone(UTC)                   # before the 18:00 habit hour and 21:00 check-in
    assert cp.plan_companion(ctx(before, open_habits=[habit()])) == []
    mid = ist(2026, 10, 13, 19, 30).astimezone(UTC)                     # habit window, but NOT a check-in yet
    assert cp.plan_companion(ctx(mid, open_habits=[habit()]))[0].kind == "habit"
    assert cp.plan_companion(ctx(open_habits=[habit()], checkin_confirmed_today=True)) == []
    assert cp.plan_companion(ctx(open_habits=[])) == []


def test_same_moment_never_pushes_twice():
    sent = row("checkin", NOW - timedelta(hours=1), key="checkin:2026-10-13")
    assert cp.plan_companion(ctx(open_habits=[habit()], ledger=[sent])) == []


def test_quiet_hours_win_even_for_own_plans_unless_opted_in():
    late = ist(2026, 10, 13, 22, 40).astimezone(UTC)                     # inside 22:00-08:00
    base = dict(bedtime=time(23, 20), sleep_cues=[cp.PlanCue("it is 11pm", "phone leaves the bed")])
    assert cp.plan_companion(ctx(late, **base)) == []
    opted = cp.plan_companion(ctx(late, prefs=prefs(plan_cues_in_quiet=True), **base))
    assert len(opted) == 1 and opted[0].kind == "winddown" and opted[0].body.startswith("If it is 11pm")
    generic = dict(bedtime=time(23, 20))                                 # no plan of their own -> strict quiet hours
    assert cp.plan_companion(ctx(late, prefs=prefs(plan_cues_in_quiet=True), **generic)) == []


def test_pause_and_master_switch_silence_everything():
    h = [habit()]
    assert cp.plan_companion(ctx(open_habits=h, paused=True)) == []
    assert cp.plan_companion(ctx(prefs=prefs(companion_enabled=False), open_habits=h)) == []
    assert cp.plan_companion(ctx(prefs=prefs(push_enabled=False), open_habits=h)) == []


def test_habit_push_uses_own_plan_then_floor_and_skips_automatic_habits():
    evening = ist(2026, 10, 13, 18, 30).astimezone(UTC)
    gym = habit("Gym", floor_text="10-min walk", consistency_pct=40.0)
    auto = habit("Water", consistency_pct=95.0, automatic=True)
    out = cp.plan_companion(ctx(evening, open_habits=[auto, gym]))
    assert out[0].kind == "habit" and out[0].title == "Gym" and "10-min walk" in out[0].body
    assert [a for a, _ in out[0].actions] == ["done", "floor"] and out[0].args["habit_id"] == str(gym.habit_id)

    plan = cp.PlanCue("I get back from class", "gym shoes on", level="full", entity_id=gym.habit_id)
    withplan = cp.plan_companion(ctx(evening, open_habits=[auto, gym], habit_cues=[plan]))
    assert withplan[0].body == "If I get back from class, then gym shoes on"
    assert cp.plan_companion(ctx(evening, open_habits=[auto])) == []     # automatic: no push at all
    light = cp.PlanCue("x", "y", level="light", entity_id=gym.habit_id)
    assert "If x" not in cp.plan_companion(ctx(evening, open_habits=[gym], habit_cues=[light]))[0].body


def test_risk_push_fires_in_lead_window_is_discreet_and_obeys_weekdays_and_fade():
    w = rw.RiskWindow(23, 0, frozenset(range(7)), events=6, recent_events=3)
    cue = [cp.PlanCue("it is 11pm", "laptop out of bed")]
    t = ist(2026, 10, 13, 22, 35).astimezone(UTC)
    out = cp.plan_companion(ctx(t, prefs=prefs(plan_cues_in_quiet=True), risk_windows=[w], urge_cues=cue))
    assert len(out) == 1 and out[0].kind == "risk" and out[0].priority == 90
    assert out[0].title == "Your plan" and "laptop" not in out[0].body and "urge" not in out[0].body.lower()
    open_text = cp.plan_companion(ctx(t, prefs=prefs(plan_cues_in_quiet=True, discreet_push=False), risk_windows=[w], urge_cues=cue))
    assert open_text[0].body == "If it is 11pm, then laptop out of bed"
    # too early / no plan / faded / wrong weekday
    early = ist(2026, 10, 13, 21, 50).astimezone(UTC)
    assert cp.plan_companion(ctx(early, risk_windows=[w], urge_cues=cue)) == []
    assert cp.plan_companion(ctx(t, prefs=prefs(plan_cues_in_quiet=True), risk_windows=[w], urge_cues=[])) == []
    faded = rw.RiskWindow(23, 0, frozenset(range(7)), events=6, recent_events=0)
    assert cp.plan_companion(ctx(t, prefs=prefs(plan_cues_in_quiet=True), risk_windows=[faded], urge_cues=cue)) == []
    monday_only = rw.RiskWindow(23, 0, frozenset({0}), events=9, recent_events=2)      # Oct 13 is a Tuesday
    assert cp.plan_companion(ctx(t, prefs=prefs(plan_cues_in_quiet=True), risk_windows=[monday_only], urge_cues=cue)) == []


def test_risk_window_just_after_midnight_fires_the_evening_before():
    w = rw.RiskWindow(0, 1, frozenset(range(7)), events=6, recent_events=2)            # opens 00:00 on the NEXT day
    t = ist(2026, 10, 13, 23, 40).astimezone(UTC)
    out = cp.plan_companion(ctx(t, prefs=prefs(plan_cues_in_quiet=True), risk_windows=[w],
                                urge_cues=[cp.PlanCue("a", "b")]))
    assert len(out) == 1 and out[0].key == "risk:2026-10-14:00"


def test_study_only_when_behind_and_nothing_today():
    t = ist(2026, 10, 14, 19, 0).astimezone(UTC)                                          # Wednesday
    behind = dict(study_weekly_target=600, study_week_minutes=100, study_today_minutes=0)
    out = cp.plan_companion(ctx(t, **behind))
    assert out[0].kind == "study" and "500 min" in out[0].body
    assert cp.plan_companion(ctx(t, study_weekly_target=600, study_week_minutes=400)) == []          # on pace
    assert cp.plan_companion(ctx(t, study_weekly_target=600, study_week_minutes=100, study_today_minutes=20)) == []
    assert cp.plan_companion(ctx(t)) == []                                                    # no study goal


def test_budget_spacing_and_one_per_run():
    h = [habit()]
    recent = row("risk", NOW - timedelta(minutes=20))
    assert cp.plan_companion(ctx(open_habits=h, ledger=[recent])) == []                       # too close to the last one
    three = [row(k, NOW - timedelta(hours=5 + i)) for i, k in enumerate(("habit", "risk", "winddown"))]
    assert cp.plan_companion(ctx(open_habits=h, ledger=three)) == []                          # 3 a day is the ceiling
    w = rw.RiskWindow(21, 22, frozenset(range(7)), 6, 3)
    both = cp.plan_companion(ctx(open_habits=h, risk_windows=[w], urge_cues=[cp.PlanCue("a", "b")],
                                 prefs=prefs()))
    assert len(both) == 1 and both[0].kind == "risk"                                           # highest priority wins


def test_ignored_pushes_back_off_then_stop_and_acting_resets():
    h = [habit()]
    old = lambda n: [row("checkin", NOW - timedelta(days=n + 1)) for n in range(n)]            # n ignored, oldest first not needed
    assert cp.plan_companion(ctx(open_habits=h, ledger=old(2)))                                # 2 ignored: still pushes
    assert cp.plan_companion(ctx(open_habits=h, ledger=old(3))) == []                          # 3 ignored: muted 3 days
    long_ago = [row("checkin", NOW - timedelta(days=4 + i)) for i in range(3)]
    assert cp.plan_companion(ctx(open_habits=h, ledger=long_ago))                              # mute expired: one probe
    six = [row("checkin", NOW - timedelta(days=1 + i)) for i in range(6)]
    assert cp.plan_companion(ctx(open_habits=h, ledger=six[:5] + [six[5]])) == []
    acted = old(3)
    acted[0].acted_at = acted[0].sent_at                                                       # newest was acted on
    assert cp.plan_companion(ctx(open_habits=h, ledger=acted))


def test_confirming_the_day_in_app_counts_as_acting_for_checkin_and_habit():
    rows = [row("checkin", NOW - timedelta(days=n + 1)) for n in range(3)]
    confirmed = frozenset(r.local_date for r in rows)
    assert cp.ignored_streak(rows, "checkin", NOW, frozenset()) == 3
    assert cp.ignored_streak(rows, "checkin", NOW, confirmed) == 0
    risk = [row("risk", NOW - timedelta(days=n + 1)) for n in range(3)]
    assert cp.ignored_streak(risk, "risk", NOW, frozenset(r.local_date for r in risk)) == 3   # risk is never "resolved"


def test_fresh_push_is_pending_not_ignored():
    rows = [row("checkin", NOW - timedelta(minutes=30))]
    assert cp.ignored_streak(rows, "checkin", NOW, frozenset()) == 0


# =============================================================== ORM / migration parity (no database needed)
def test_ledger_sql_compiles_against_postgres_and_orm_matches_migration():
    import asyncio
    import re
    from pathlib import Path

    from sqlalchemy.dialects import postgresql
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import CompanionPushORM, NotificationPrefsORM
    from app.repositories.companion_repository import SqlAlchemyCompanionRepository

    compiled: list[str] = []

    class _R:
        def scalar_one_or_none(self):
            return None

        def scalars(self):
            return self

        def all(self):
            return []

        rowcount = 0

    session = AsyncSession()

    async def fake_execute(stmt, *a, **k):
        compiled.append(str(stmt.compile(dialect=postgresql.dialect())))
        return _R()

    session.execute = fake_execute  # type: ignore[method-assign]
    repo = SqlAlchemyCompanionRepository(session)
    push = CompanionPush(id=uuid4(), user_id=UID, kind="checkin", key="checkin:2026-10-13",
                         local_date=date(2026, 10, 13), sent_at=NOW)

    async def go():
        assert await repo.reserve(push) is False
        await repo.release(UID, push.id)
        await repo.list_since(UID, NOW)
        assert await repo.mark_acted(UID, push.id, "lock", NOW) is None
        await repo.prune(UID, NOW)

    asyncio.run(go())
    assert any("ON CONFLICT" in sql and "DO NOTHING" in sql for sql in compiled)
    assert any("acted_at IS NULL" in sql for sql in compiled)

    migrations = Path(__file__).parent.parent / "migrations"
    # 016 created the ledger; 022 added dismissed_at (swiped-away pushes).
    migration = (migrations / "016_companion.sql").read_text() + (migrations / "022_habit_tokens_and_push_dismissal.sql").read_text()
    for col in CompanionPushORM.__table__.columns:
        assert re.search(rf"\b{col.name}\b", migration), col.name
    for col in ("companion_enabled", "checkin_hour", "plan_cues_in_quiet", "discreet_push"):
        assert col in NotificationPrefsORM.__table__.columns and col in migration


# =============================================================== morning + comeback
from dataclasses import replace  # noqa: E402

AM = datetime(2026, 10, 13, 2, 40, tzinfo=UTC)          # Tue 08:10 IST: ten minutes into the default morning window


def _task(title="Submit lab report", importance=3, overdue=False) -> cp.OpenTask:
    return cp.OpenTask(task_id=uuid4(), title=title, importance=importance, due_at=ist(2026, 10, 13, 17), overdue=overdue)


def _info(silent=3, floor="10-min walk", name="Gym", habit_id=None) -> cp.ComebackInfo:
    return cp.ComebackInfo(habit_id=habit_id or uuid4(), name=name, floor_text=floor, silent_days=silent, slip_streak=silent)


def test_median_wake_keeps_a_midnight_straddling_cluster_together():
    assert cp.median_wake([time(23, 50), time(0, 10), time(23, 55), time(0, 5), time(0, 0)]) == time(0, 0)
    assert cp.median_wake([time(6, 10), time(6, 20), time(6, 30), time(6, 40), time(7, 0)]) == time(6, 30)
    assert cp.median_wake([time(6, 30)] * 4) is None                      # fewer than 5 real logs
    assert cp.median_bedtime([time(23, 30), time(0, 30), time(0, 0), time(23, 45), time(0, 15)]) == time(0, 0)   # unchanged


def test_morning_opens_after_the_usual_wake_but_never_inside_quiet_hours():
    q = (time(22, 0), time(8, 0))
    assert cp.morning_start(*q, time(6, 10)) == time(8, 0)                # early riser: quiet hours end first
    assert cp.morning_start(*q, time(8, 40)) == time(9, 0)                # 20 minutes after waking
    assert cp.morning_start(*q, None) == time(8, 0)                       # no wake data: quiet_end
    assert cp.morning_start(*q, time(13, 0)) == time(12, 0)               # late riser: capped at quiet_end + 4 h
    off = (time(0, 0), time(0, 0))                                        # quiet hours switched off
    assert cp.morning_start(*off, None) == time(8, 0)
    assert cp.morning_start(*off, time(6, 0)) == time(6, 20)
    assert cp.morning_start(*off, time(2, 0)) == time(5, 0)               # never before 05:00
    assert cp.morning_start(*off, time(23, 50)) is None                   # past midnight: no morning today


def test_morning_window_is_ninety_minutes_and_ends_before_the_habit_hour():
    p = prefs()
    assert not cp.morning_window_open(AM - timedelta(minutes=11), TZ, p, None)    # 07:59
    assert cp.morning_window_open(AM - timedelta(minutes=10), TZ, p, None)        # 08:00
    assert cp.morning_window_open(AM + timedelta(minutes=80), TZ, p, None)        # 09:30
    assert not cp.morning_window_open(AM + timedelta(minutes=81), TZ, p, None)
    assert not cp.morning_window_open(AM, TZ, prefs(nudge_hour=8), None)          # the habit-nudge hour owns the day


def test_morning_possible_is_a_cheap_gate_that_never_hides_a_real_window():
    p = prefs()
    assert cp.morning_possible(AM, TZ, p)                                          # 08:10
    assert cp.morning_possible(AM + timedelta(hours=5, minutes=20), TZ, p)         # 13:30: latest a late riser's window can close
    assert not cp.morning_possible(AM + timedelta(hours=5, minutes=21), TZ, p)     # 13:31
    assert not cp.morning_possible(AM - timedelta(minutes=11), TZ, p)              # 07:59
    off = prefs(quiet_start=time(0, 0), quiet_end=time(0, 0))
    assert not cp.morning_possible(AM - timedelta(hours=3, minutes=11), TZ, off)   # 04:59
    assert cp.morning_possible(AM - timedelta(hours=3, minutes=10), TZ, off)       # 05:00
    for wake in (None, time(6, 0), time(9, 30), time(13, 0)):                      # the gate is never stricter than the window
        for minute in range(0, 24 * 60, 5):
            at = datetime(2026, 10, 13, minute // 60, minute % 60, tzinfo=TZ)
            if cp.morning_window_open(at, TZ, p, wake):
                assert cp.morning_possible(at, TZ, p)


def test_morning_picks_a_task_due_today_before_any_habit():
    low, high = _task("Buy cable", 2), _task("Submit report", 3)
    pick = cp.pick_morning([low, high], [habit("Gym", consistency_pct=10.0)], [])
    assert (pick.kind, pick.entity_id, pick.name) == ("task", high.task_id, "Submit report")
    assert pick.detail.startswith("Due today")
    assert cp.pick_morning([_task("Sort drawer", 1)], [], []) is None             # small chores never earn their own push
    assert cp.pick_morning([_task("Pay fees", 2, overdue=True)], [], []).detail.startswith("Still open")


def test_morning_falls_back_to_the_weakest_open_habit_in_their_own_words():
    strong, auto = habit("Read", consistency_pct=90.0), habit("Water", consistency_pct=99.0, automatic=True)
    weak = habit("Gym", consistency_pct=20.0, floor_text="10-min walk")
    pick = cp.pick_morning([], [strong, weak, auto], [])
    assert (pick.kind, pick.entity_id) == ("habit", weak.habit_id) and "10-min walk" in pick.detail
    cue = cp.PlanCue(cue="I put my shoes on", action="walk out the door", entity_id=weak.habit_id)
    assert cp.pick_morning([], [strong, weak], [cue]).detail == "If I put my shoes on, then walk out the door"
    faded = cp.PlanCue(cue="x", action="y", level="light", entity_id=weak.habit_id)
    assert "10-min walk" in cp.pick_morning([], [weak], [faded]).detail           # a faded plan is not quoted
    assert cp.pick_morning([], [auto], []) is None                                # automatic habits never get a push


def test_morning_push_is_one_thing_with_start_and_not_today():
    t = _task()
    out = cp.plan_companion(ctx(now=AM, morning_pick=cp.pick_morning([t], [], [])))
    assert len(out) == 1
    m = out[0]
    assert (m.kind, m.title, m.priority, m.key) == ("morning", "One thing today", 75, "morning:2026-10-13")
    assert m.body == "Submit lab report. Due today. Start with five minutes."
    assert [a for a, _ in m.actions] == ["start", "later"]
    assert m.url == f"/?a=focus&k=task&id={t.task_id}"
    assert m.args == {"k": "task", "id": str(t.task_id), "date": "2026-10-13"}


def test_morning_is_silent_outside_its_window_once_sent_and_when_a_comeback_owns_the_morning():
    pick = cp.pick_morning([_task()], [], [])
    assert cp.plan_companion(ctx(now=AM + timedelta(minutes=90), morning_pick=pick)) == []    # 09:40, window over
    assert cp.plan_companion(ctx(now=AM - timedelta(minutes=40), morning_pick=pick)) == []    # 07:30, quiet hours
    sent = [row("morning", AM - timedelta(minutes=50), key="morning:2026-10-13")]
    assert cp.plan_companion(ctx(now=AM, morning_pick=pick, ledger=sent)) == []               # already sent today
    out = cp.plan_companion(ctx(now=AM, morning_pick=pick, comeback=_info(silent=3)))
    assert [m.kind for m in out] == ["comeback"]                                                # one push, not two
    assert cp.plan_companion(ctx(now=AM, morning_pick=pick, comeback=_info(silent=20))) == []   # given up: neither


def test_comeback_offers_one_habit_floor_only():
    info = _info(silent=3)
    m = cp.plan_companion(ctx(now=AM, comeback=info))[0]
    assert (m.kind, m.title, m.priority, m.key) == ("comeback", "Start small", 78, "comeback:2026-10-13")
    assert m.body == "Gym: 10-min walk. That counts."
    assert list(m.actions) == [("floor", "Floor version"), ("later", "Not today")]
    assert m.args == {"habit_id": str(info.habit_id), "date": "2026-10-13"} and m.url == f"/?a=comeback&id={info.habit_id}"
    long = cp.plan_companion(ctx(now=AM, comeback=_info(silent=5, floor=None)))[0]
    assert (long.title, long.body) == ("Welcome back", "Gym. Just the floor version counts today.")


def test_comeback_needs_two_silent_days_lets_go_at_fourteen_and_needs_a_habit_to_offer():
    for silent in (0, 1, 14, 30):
        assert cp.plan_companion(ctx(now=AM, comeback=_info(silent=silent))) == []
    nothing_today = cp.ComebackInfo(habit_id=None, name="", floor_text=None, silent_days=3, slip_streak=3)
    pick = cp.pick_morning([_task()], [], [])
    assert cp.plan_companion(ctx(now=AM, morning_pick=pick, comeback=nothing_today)) == []     # silent: not even a morning


def test_comeback_spaces_itself_three_days_apart_and_stops_after_three_unanswered():
    info = _info(silent=6)
    assert cp.plan_companion(ctx(now=AM, comeback=info, ledger=[row("comeback", AM - timedelta(days=2))])) == []
    three = [row("comeback", AM - timedelta(days=3, minutes=1))]
    assert [m.kind for m in cp.plan_companion(ctx(now=AM, comeback=info, ledger=three))] == ["comeback"]
    unanswered = [row("comeback", AM - timedelta(days=d, minutes=1)) for d in (3, 6, 9)]
    assert cp.plan_companion(ctx(now=AM, comeback=info, ledger=unanswered)) == []              # never escalate: let go
    mixed = [row("comeback", AM - timedelta(days=3, minutes=1), acted=True)] + unanswered[1:]
    assert [m.kind for m in cp.plan_companion(ctx(now=AM, comeback=info, ledger=mixed))] == ["comeback"]


def test_not_today_counts_as_ignored_for_morning_and_comeback_only():
    def declined(kind, days):
        return [replace(row(kind, AM - timedelta(days=d)), acted_at=AM - timedelta(days=d), action="later") for d in days]
    three = declined("morning", (1, 2, 3))
    assert cp.ignored_streak(three, "morning", AM, frozenset()) == 3 and cp.is_muted(three, "morning", AM, frozenset())
    assert cp.ignored_streak(declined("study", (1, 2, 3)), "study", AM, frozenset()) == 0     # old kinds unchanged
    tapped = [replace(three[0], action="start")] + three[1:]
    assert cp.ignored_streak(tapped, "morning", AM, frozenset()) == 0                         # "Start" resets the count


def test_new_kinds_are_registered_everywhere_the_old_ones_are():
    for kind in ("morning", "comeback"):
        assert kind in cp.COMPANION_KINDS and kind in cp.PRIORITY and kind in cp.TTL_MINUTES
        assert kind in cp.RESOLVABLE_KINDS and kind in cp.DECLINABLE_KINDS
        assert kind not in cp.PLAN_CUE_KINDS                                                  # quiet hours always win
