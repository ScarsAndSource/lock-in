"""Batch A: three-tier habits, bounce-back protocol, tone dial."""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.domain import HabitDefinition, HabitLog, HabitStatus, TargetFrequency
from app.services.bounce_back import (
    HELD, REST, SLIP, BounceState, bounce_copy, classify_day, compute_bounce_rate, compute_bounce_state,
)
from app.services.checkins_service import CheckinsService
from app.services.consistency_service import compute_habit_consistency
from app.services.schedule import credit
from app.services.tone import resolve_tone
from app.voice_config import COACH_OVERLAY, chat_system_prompt, render_voice

USER = uuid4()
LONG_AGO = datetime(2026, 1, 1, tzinfo=timezone.utc)
EVERY_DAY = {"type": "weekdays", "days": [0, 1, 2, 3, 4, 5, 6]}


# ------------------------------------------------------------ helpers
def _habit(freq=None, created_at=LONG_AGO):
    return HabitDefinition(
        id=uuid4(), user_id=USER, name="H",
        target_frequency=freq or TargetFrequency(type="weekdays", days=(0, 1, 2, 3, 4, 5, 6)),
        created_at=created_at,
    )


def _log(habit, d, status=HabitStatus.DONE, is_default=False):
    return HabitLog(habit_id=habit.id, user_id=USER, log_date=d, status=status, is_default=is_default)


def _by(habit, logs):
    return {habit.id: {l.log_date: l for l in logs}}


def _api_habit(world, client, **extra):
    r = client.post("/habits", json={"name": "Gym", "target_frequency": EVERY_DAY, **extra})
    assert r.status_code == 201, r.text
    for h in world.habit_repo._habits.values():  # fake repo stamps real "now"; keep it before the test dates
        h.created_at = LONG_AGO
    return r.json()["id"]


def _log_api(client, hid, day, status):
    r = client.post(f"/habits/{hid}/logs", json={"log_date": day, "status": status})
    assert r.status_code == 200, r.text


# ============================================================ three-tier habits
def test_credit_table_floor_counts_for_continuity_but_less_than_target():
    assert credit(HabitStatus.STRETCH) == 1.0 and credit(HabitStatus.DONE) == 1.0
    assert credit(HabitStatus.FLOOR) == 0.75 and credit(HabitStatus.PARTIAL) == 0.5
    assert credit(HabitStatus.SKIPPED) == 0.0


def test_floor_is_not_a_miss_in_consistency_runs_and_comeback():
    h = _habit()
    logs = [
        _log(h, date(2026, 12, 25), HabitStatus.DONE), _log(h, date(2026, 12, 26), HabitStatus.SKIPPED),
        _log(h, date(2026, 12, 27), HabitStatus.FLOOR), _log(h, date(2026, 12, 28), HabitStatus.STRETCH),
    ]
    r = compute_habit_consistency(h, logs, end_date=date(2026, 12, 28), window_days=4)
    assert r.earned == 1 + 0 + 0.75 + 1 and r.consistency_pct == 68.8  # 2.75 / 4
    assert r.current_run == 2          # floor + stretch after the miss
    assert r.comeback_rate == 100.0    # the miss was followed by a floor day


def test_habit_api_floor_and_stretch_text_roundtrip_and_clear(world, user_a):
    c = world.client_as(user_a)
    r = c.post("/habits", json={
        "name": "Gym", "target_frequency": EVERY_DAY, "floor_text": "  10 min walk ", "stretch_text": "full hour",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["floor_text"] == "10 min walk" and body["stretch_text"] == "full hour"
    hid = body["id"]

    # touching only floor_text leaves stretch_text alone; null clears
    r = c.patch(f"/habits/{hid}", json={"floor_text": None})
    assert r.status_code == 200
    assert r.json()["floor_text"] is None and r.json()["stretch_text"] == "full hour"
    assert c.patch(f"/habits/{hid}", json={"stretch_text": "   "}).json()["stretch_text"] is None
    assert c.patch(f"/habits/{hid}", json={}).status_code == 422
    assert c.post("/habits", json={
        "name": "X", "target_frequency": EVERY_DAY, "floor_text": "x" * 121,
    }).status_code == 422
    listed = c.get("/habits").json()
    assert listed[0]["floor_text"] is None and listed[0]["stretch_text"] is None


def test_habit_api_accepts_floor_and_stretch_log_statuses(world, user_a):
    c = world.client_as(user_a)
    hid = _api_habit(world, c)
    for status in ("floor", "stretch", "partial"):
        r = c.post(f"/habits/{hid}/logs", json={"log_date": "2026-12-30", "status": status})
        assert r.status_code == 200 and r.json()["status"] == status
    assert c.post(f"/habits/{hid}/logs", json={"log_date": "2026-12-30", "status": "nope"}).status_code == 422


def test_checkin_entries_carry_the_tier_text(world, user_a):
    c = world.client_as(user_a)
    _api_habit(world, c, floor_text="10 min walk", stretch_text="full hour")
    e = c.get("/checkins/2026-12-31/defaults").json()["entries"][0]
    assert e["floor_text"] == "10 min walk" and e["stretch_text"] == "full hour"


# ============================================================ bounce-back: pure engine
def test_classify_day_states():
    h = _habit()
    d = date(2026, 12, 30)
    assert classify_day([h], _by(h, [_log(h, d)]), d) == HELD
    assert classify_day([h], _by(h, [_log(h, d, HabitStatus.FLOOR)]), d) == HELD      # floor counts as held
    assert classify_day([h], _by(h, [_log(h, d, HabitStatus.PARTIAL)]), d) == HELD    # 0.5 is the threshold
    assert classify_day([h], _by(h, [_log(h, d, HabitStatus.SKIPPED)]), d) == SLIP
    assert classify_day([h], {}, d) == SLIP                                           # absent day is a slip


def test_classify_day_rest_cases():
    wk = _habit(TargetFrequency(type="weekdays", days=(0,)))          # Mondays only
    assert classify_day([wk], {}, date(2026, 12, 30)) == REST         # a Wednesday: nothing owed
    flexible = _habit(TargetFrequency(type="n_per_week", count=3))
    assert classify_day([flexible], {}, date(2026, 12, 30)) == REST   # unlogged flexible habit is never "owed"
    assert classify_day([flexible], _by(flexible, [_log(flexible, date(2026, 12, 30), HabitStatus.SKIPPED)]),
                        date(2026, 12, 30)) == SLIP
    new = _habit(created_at=datetime(2026, 12, 31, 9, tzinfo=timezone.utc))
    assert classify_day([new], {}, date(2026, 12, 30)) == REST        # created after that day
    d = date(2026, 12, 30)
    h = _habit()
    assert classify_day([h], {}, d, paused_global=frozenset({d})) == REST
    assert classify_day([h], {}, d, paused_by_habit={h.id: frozenset({d})}) == REST
    assert classify_day([h], _by(h, [_log(h, d)]), d, paused_global=frozenset({d})) == HELD  # real log still counts


def test_bounce_state_inactive_for_new_users_and_after_a_held_day():
    h = _habit()
    today = date(2026, 12, 31)
    assert compute_bounce_state([h], [], today) == BounceState(active=False)
    assert compute_bounce_state([], [_log(h, date(2026, 12, 20))], today).active is False
    assert compute_bounce_state([h], [_log(h, date(2026, 12, 30))], today).active is False


def test_bounce_state_single_slip_and_absence_streak():
    h = _habit()
    today = date(2026, 12, 31)
    one = compute_bounce_state([h], [_log(h, date(2026, 12, 29)), _log(h, date(2026, 12, 30), HabitStatus.SKIPPED)], today)
    assert one.active and one.slip_streak == 1 and one.last_slip_date == date(2026, 12, 30)

    away = compute_bounce_state([h], [_log(h, date(2026, 12, 27))], today)  # silent Dec 28, 29, 30
    assert away.active and away.slip_streak == 3 and away.last_slip_date == date(2026, 12, 30)


def test_bounce_state_skips_rest_days_and_caps_the_streak():
    weekdays = _habit(TargetFrequency(type="weekdays", days=(0, 1, 2, 3, 4)))
    monday = date(2026, 12, 28)
    fri = date(2026, 12, 25)
    slipped = compute_bounce_state(
        [weekdays], [_log(weekdays, date(2026, 12, 23)), _log(weekdays, fri, HabitStatus.SKIPPED)], monday)
    assert slipped.active and slipped.last_slip_date == fri          # Sat/Sun are rest, Friday was the last owed day
    held = compute_bounce_state([weekdays], [_log(weekdays, fri, HabitStatus.FLOOR)], monday)
    assert held.active is False

    h = _habit()
    long_gone = compute_bounce_state([h], [_log(h, date(2026, 11, 1))], date(2026, 12, 31))
    assert long_gone.active and long_gone.slip_streak == 7           # capped, not 14+


def test_bounce_rate_counts_slips_that_had_48h_to_resolve():
    d = date(2026, 12, 20)
    states = {
        d: SLIP, d + timedelta(1): HELD,                        # slip -> held next day: returned
        d + timedelta(2): SLIP, d + timedelta(3): REST, d + timedelta(4): SLIP,   # slip, rest, slip: not returned
        d + timedelta(5): SLIP, d + timedelta(6): HELD,         # judged only if 2 days fit before `end`
    }
    rate = compute_bounce_rate(states, end=d + timedelta(6))
    # judged: d (ok), d+2 (d+3 rest, d+4 slip -> no), d+4 (d+5 slip, d+6 held -> yes); d+5 and d+6 too young
    assert (rate.slip_days, rate.returned, rate.rate_pct) == (3, 2, 66.7)
    assert compute_bounce_rate({}, date(2026, 12, 31)).rate_pct is None


def test_bounce_copy_and_tone_resolution():
    assert bounce_copy(BounceState(active=False), "direct") is None
    one, many = BounceState(True, 1), BounceState(True, 3)
    assert bounce_copy(one, "direct")[0] == "Floor day" and bounce_copy(many, "direct")[0] == "Floor day, again"
    assert bounce_copy(one, "coach")[0] == "Easy day today" and bounce_copy(many, "coach")[0] == "Start small"
    assert resolve_tone("direct", 5) == "direct" and resolve_tone("coach", 0) == "coach"
    assert resolve_tone("auto", 1) == "direct" and resolve_tone("auto", 2) == "coach"
    assert resolve_tone("garbage", 9) == "direct"


def test_coach_overlay_only_when_asked_and_direct_prompt_is_unchanged():
    assert COACH_OVERLAY not in render_voice() and COACH_OVERLAY not in chat_system_prompt()
    assert COACH_OVERLAY in render_voice("coach") and chat_system_prompt("coach").startswith(render_voice("coach"))


# ============================================================ bounce-back: through the API
def test_check_in_after_a_slip_is_a_floor_day(world, user_a):
    c = world.client_as(user_a)
    hid = _api_habit(world, c)
    _log_api(c, hid, "2026-12-29", "done")
    _log_api(c, hid, "2026-12-30", "skipped")
    view = c.get("/checkins/2026-12-31/defaults").json()
    assert view["entries"][0]["status"] == "floor"
    assert view["entries"][0]["reason"].startswith("Bounce-back day")
    assert view["entries"][0]["is_low_confidence"] is False
    b = view["bounce"]
    assert b["active"] is True and b["slip_streak"] == 1 and b["tone"] == "direct" and b["title"] == "Floor day"

    confirmed = c.post("/checkins/2026-12-31/confirm", json={}).json()   # accept the proposal untouched
    assert confirmed["entries"][0]["status"] == "floor" and confirmed["entries"][0]["is_default"] is True

    # a real tap still wins over the lowered proposal
    c.post("/checkins/2026-12-31/confirm", json={"overrides": [{"habit_id": hid, "status": "stretch"}]})
    assert c.get("/checkins/2026-12-31/defaults").json()["entries"][0]["status"] == "stretch"


def test_a_three_day_absence_is_a_gentler_coach_floor_day(world, user_a):
    c = world.client_as(user_a)
    hid = _api_habit(world, c)
    _log_api(c, hid, "2026-12-27", "done")
    b = c.get("/checkins/2026-12-31/defaults").json()["bounce"]
    assert b["slip_streak"] == 3 and b["tone"] == "coach" and b["title"] == "Start small"


def test_no_bounce_for_new_users_or_after_a_held_day(world, user_a):
    c = world.client_as(user_a)
    hid = _api_habit(world, c)
    fresh = c.get("/checkins/2026-12-31/defaults").json()
    assert fresh["bounce"]["active"] is False and fresh["bounce"]["title"] is None
    assert fresh["entries"][0]["status"] == "done"

    _log_api(c, hid, "2026-12-30", "floor")  # a floor day is a held day
    held = c.get("/checkins/2026-12-31/defaults").json()
    assert held["bounce"]["active"] is False and held["entries"][0]["status"] == "done"


def test_bounce_does_not_touch_a_usual_skip_or_an_existing_log(world, user_a):
    c = world.client_as(user_a)
    hid = _api_habit(world, c)
    _log_api(c, hid, "2026-12-30", "skipped")
    _log_api(c, hid, "2026-12-31", "done")  # already logged today
    e = c.get("/checkins/2026-12-31/defaults").json()["entries"][0]
    assert e["status"] == "done" and e["reason"] == "Already logged for this date."


def test_bounce_switch_off_keeps_the_old_proposals(world, user_a):
    c = world.client_as(user_a)
    hid = _api_habit(world, c)
    _log_api(c, hid, "2026-12-30", "skipped")
    service = CheckinsService(
        world.habit_repo, world.checkin_repo, world.encryptor, world.sleep_repo, world.screen_time_repo,
        lambda: world.now, bounce_enabled=False,
    )
    view = asyncio.run(service.get_view(user_a, date(2026, 12, 31)))
    assert view.bounce.active is False and view.entries[0].status == HabitStatus.DONE


def test_bounce_back_rate_endpoint(world, user_a):
    c = world.client_as(user_a)
    hid = _api_habit(world, c)
    for i in range(14):
        day = date(2026, 12, 18) + timedelta(days=i)
        _log_api(c, hid, day.isoformat(), "skipped" if i == 0 else "done")
    r = c.get("/stats/bounce-back", params={"window_days": 14})
    assert r.status_code == 200
    body = r.json()
    assert body["end_date"] == "2026-12-31" and body["window_days"] == 14
    assert (body["slip_days"], body["returned_within_48h"], body["rate_pct"]) == (1, 1, 100.0)

    empty = world.client_as(uuid4()).get("/stats/bounce-back").json()
    assert empty["slip_days"] == 0 and empty["rate_pct"] is None
    assert c.get("/stats/bounce-back", params={"window_days": 3}).status_code == 422


# ============================================================ tone dial
def test_tone_dial_through_the_profile_api(world, user_a):
    c = world.client_as(user_a)
    assert c.get("/me").json()["tone_preference"] == "auto"
    r = c.patch("/me", json={"tone_preference": "coach"})
    assert r.status_code == 200 and r.json()["tone_preference"] == "coach"
    r = c.patch("/me", json={"timezone": "Asia/Kolkata"})  # timezone alone must still work and keep the tone
    assert r.status_code == 200 and r.json()["timezone"] == "Asia/Kolkata" and r.json()["tone_preference"] == "coach"
    assert c.patch("/me", json={"tone_preference": "loud"}).status_code == 422
    assert c.patch("/me", json={}).status_code == 422


def _seed_chat(world, c, last_two):
    hid = _api_habit(world, c)
    _log_api(c, hid, "2026-12-28", "done")
    _log_api(c, hid, "2026-12-29", last_two[0])
    _log_api(c, hid, "2026-12-30", last_two[1])


def _chat_system_prompt(world, c):
    world.llm.replies = [json.dumps({"answer": "x", "next_step": "y", "cited_days": ["2026-12-30"]})]
    assert c.post("/chat/messages", json={"message": "how is it going?"}).status_code == 200
    return world.llm.calls[0][0][0]["content"]


def test_chat_goes_coach_in_auto_after_two_slipped_days(world, user_a):
    c = world.client_as(user_a)
    _seed_chat(world, c, ("skipped", "skipped"))
    assert _chat_system_prompt(world, c) == chat_system_prompt("coach")


def test_chat_stays_direct_in_auto_after_a_single_slip_or_a_good_stretch(world, user_a):
    c = world.client_as(user_a)
    _seed_chat(world, c, ("done", "skipped"))
    assert _chat_system_prompt(world, c) == chat_system_prompt("direct")


def test_chat_respects_a_fixed_tone_choice(world, user_a):
    c = world.client_as(user_a)
    _seed_chat(world, c, ("skipped", "skipped"))
    c.patch("/me", json={"tone_preference": "direct"})
    assert _chat_system_prompt(world, c) == chat_system_prompt("direct")
    world.llm.calls.clear()
    c.patch("/me", json={"tone_preference": "coach"})
    assert _chat_system_prompt(world, c) == chat_system_prompt("coach")
