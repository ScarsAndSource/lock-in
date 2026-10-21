"""Pure-function tests for Agent C: adaptive send time and sleep inference. No DB, no network."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.inference import NightProxy, circ_diff, fmt_hours, infer_night, needs_rhythm, night_proxy, reconcile
from app.services.rhythm import Rhythm
from app.services.send_time import (
    EXPLORE_RATE, HourStats, adapt_moment_times, candidate_hours, choose_send_hour, day_rng, was_acted,
)

TZ = ZoneInfo("Asia/Kolkata")
NO_QUIET = (0, 0)
QUIET = (23 * 60, 7 * 60)


def rhythm(bed=None, wake=None) -> Rhythm:
    return Rhythm(wake=wake, bed=bed, checkin=None, first_open=None, windows=(), samples=30, confidence="medium")


# ------------------------------------------------------------------ send time
def test_candidates_stay_in_band_and_out_of_quiet():
    hours = candidate_hours("morning", 8 * 60, *QUIET)
    assert hours == [7, 8, 9, 10]            # 06:xx is inside the quiet window and below the morning band
    assert all(6 <= h <= 10 for h in hours)
    assert candidate_hours("evening", 20 * 60 + 30, *NO_QUIET) == [19, 20, 21, 22]


def test_learned_hour_is_always_a_candidate():
    assert 7 in candidate_hours("morning", 7 * 60 + 15, 7 * 60 - 60, 7 * 60 + 60)   # quiet-adjusted base survives


def test_cold_start_uses_learned_hour():
    stats = {9: HourStats(acted=2, ignored=1)}   # 3 < MIN_OBSERVATIONS
    choice = choose_send_hour("morning", 8 * 60, *NO_QUIET, stats, random.Random(1))
    assert (choice.hour, choice.reason, choice.explored) == (8, "cold_start", False)


def test_thompson_moves_toward_the_hour_that_gets_acted_on():
    stats = {8: HourStats(acted=1, ignored=14), 9: HourStats(acted=14, ignored=1)}
    picks = [
        choose_send_hour("morning", 8 * 60, *NO_QUIET, stats, random.Random(i)).hour for i in range(400)
    ]
    assert picks.count(9) / len(picks) > 0.7


def test_explore_floor_never_buries_an_hour():
    stats = {8: HourStats(acted=30, ignored=0), 9: HourStats(acted=0, ignored=30)}
    picks = {choose_send_hour("morning", 8 * 60, *NO_QUIET, stats, random.Random(i)).hour for i in range(600)}
    assert {6, 7, 9, 10} & picks, "exploration must still reach the unlucky hours"
    assert EXPLORE_RATE > 0


def test_choice_is_stable_within_a_day_and_varies_across_days():
    uid, stats = uuid4(), {8: HourStats(6, 6), 9: HourStats(6, 6)}
    day = date(2026, 10, 22)
    same = {choose_send_hour("morning", 480, *NO_QUIET, stats, day_rng(uid, day, "morning")).hour for _ in range(20)}
    assert len(same) == 1
    other_days = {
        choose_send_hour("morning", 480, *NO_QUIET, stats, day_rng(uid, day + timedelta(days=i), "morning")).hour
        for i in range(30)
    }
    assert len(other_days) > 1


def test_adapt_moment_times_keeps_minute_and_respects_quiet():
    out = adapt_moment_times({"morning": 8 * 60 + 15, "evening": 20 * 60 + 30}, {"morning": 9, "evening": 20}, *QUIET)
    assert out == {"morning": 9 * 60 + 15, "evening": 20 * 60 + 30}
    blocked = adapt_moment_times({"morning": 8 * 60 + 15, "evening": 20 * 60}, {"morning": 6, "evening": 20}, *QUIET)
    assert blocked["morning"] == 8 * 60 + 15     # 06:15 is quiet: the learned time stands


def test_was_acted_window():
    sent = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
    assert was_acted(sent, [sent + timedelta(minutes=20)])
    assert not was_acted(sent, [sent + timedelta(minutes=90)])
    assert not was_acted(sent, [sent - timedelta(minutes=5)])


# ------------------------------------------------------------------ inference
DAY = date(2026, 10, 22)


def at(d: date, h: int, m: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ)


def evening_opens(*extra: datetime) -> list[datetime]:
    prev = DAY - timedelta(days=1)
    return [at(prev, 19), at(prev, 21, 10), at(prev, 23, 40), *extra]


def test_night_proxy_from_the_longest_clear_gap():
    opens = [*evening_opens(), at(DAY, 6, 50), at(DAY, 7, 5), at(DAY, 9, 0)]
    proxy = night_proxy(DAY, opens, TZ)
    assert proxy == NightProxy(bed=23 * 60 + 50, wake=6 * 60 + 40)
    inf = infer_night(DAY, None, None, proxy, None)
    assert inf is not None and inf.confidence == "medium"
    assert inf.duration_minutes == 410 and inf.prompt == "~7h, right?"     # 6h50 rounds to the nearest half hour


def test_no_proxy_when_the_gap_is_not_clearly_the_night():
    prev = DAY - timedelta(days=1)
    opens = [at(prev, 19), at(prev, 20, 30), at(prev, 21, 0), at(prev, 22, 30), at(DAY, 3, 0), at(DAY, 6, 30)]
    assert night_proxy(DAY, opens, TZ) is None                                # 22:30-03:00 vs 03:00-06:30: not clear
    assert night_proxy(DAY, [at(DAY, 7, 0)], TZ) is None                      # one open says nothing
    daytime = [at(DAY, 7, 0), at(DAY, 12, 30)]
    assert night_proxy(DAY, daytime, TZ) is None                              # a 5.5h daytime gap is not a night


def test_logged_end_beats_proxy_and_raises_confidence():
    proxy = NightProxy(bed=23 * 60 + 50, wake=6 * 60 + 40)
    inf = infer_night(DAY, 23 * 60, None, reconcile(proxy, 23 * 60, None), None)
    assert inf is not None and inf.confidence == "high" and inf.basis == ("logged_bed", "first_open")
    assert infer_night(DAY, 23 * 60, 7 * 60, proxy, None) is None            # full real log: nothing to ask


def test_contradicting_proxy_is_dropped_then_rhythm_fills_one_end_at_low_confidence():
    proxy = NightProxy(bed=2 * 60, wake=9 * 60)
    assert reconcile(proxy, 23 * 60, None) is None
    assert needs_rhythm(23 * 60, None, None)
    inf = infer_night(DAY, 23 * 60, None, None, rhythm(wake=7 * 60))
    assert inf is not None and inf.confidence == "low" and inf.basis == ("logged_bed", "rhythm_wake")
    assert inf.duration_minutes == 480


def test_never_both_ends_from_rhythm_and_never_implausible_sleep():
    assert infer_night(DAY, None, None, None, rhythm(bed=23 * 60, wake=7 * 60)) is None
    assert infer_night(DAY, 7 * 60, None, None, rhythm(wake=8 * 60)) is None      # 1h of sleep is not a night
    assert circ_diff(23 * 60 + 30, 30) == 60 and fmt_hours(390) == "6.5h"
