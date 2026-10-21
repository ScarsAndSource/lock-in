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

    migration = (Path(__file__).parent.parent / "migrations" / "016_companion.sql").read_text()
    for col in CompanionPushORM.__table__.columns:
        assert re.search(rf"\b{col.name}\b", migration), col.name
    for col in ("companion_enabled", "checkin_hour", "plan_cues_in_quiet", "discreet_push"):
        assert col in NotificationPrefsORM.__table__.columns and col in migration
