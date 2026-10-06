from datetime import date, timedelta

import pytest

from app.services.chain_service import ChainDay
from app.services.retro_engine import (
    clean_day_list, count_states, echoes, fallback_narrative, trace_chains, week_bounds,
)

D = lambda day: date(2026, 12, day)  # noqa: E731


def _day(d, sleep_defaulted=False, **states):
    base = {"habits": "none", "sleep": "none", "screen_time": "none", **states}
    return ChainDay(
        day=d, habits=base["habits"], sleep=base["sleep"], screen_time=base["screen_time"],
        habit_ratio=None, sleep_minutes=None, screen_minutes=None,
        sleep_defaulted=sleep_defaulted, screen_time_defaulted=False,
    )


def _week(overrides: dict[int, dict]):
    """D(20) lead-in through D(27)."""
    return [_day(D(n), **overrides.get(n, {})) for n in range(20, 28)]


def test_week_bounds_default_is_the_last_completed_monday_to_sunday():
    # Dec 31, 2026 is a Thursday → last completed week is 21–27
    assert week_bounds(date(2026, 12, 31), None) == (D(21), D(27))
    # Dec 28 is the Monday right after the week ends → still 21–27
    assert week_bounds(date(2026, 12, 28), None) == (D(21), D(27))


@pytest.mark.parametrize("requested", [date(2026, 12, 28), date(2026, 12, 22), date(2026, 1, 5)])
def test_week_bounds_rejects_unfinished_non_monday_and_ancient_weeks(requested):
    with pytest.raises(ValueError):
        week_bounds(date(2026, 12, 31), requested)


def test_chains_trace_slips_back_to_signals_and_rank_by_upstream_count():
    days = _week({
        22: {"screen_time": "bad"},
        23: {"habits": "bad", "sleep": "bad"},
        25: {"habits": "bad"},                      # no upstream → unexplained
        26: {"habits": "bad", "sleep": "bad"},
    })
    links, unexplained = trace_chains(days, D(21), D(27))
    # Wed (23) has sleep same-day + screen from Tue (22) = 2 upstream signals → ranked first
    assert [l.slip_day for l in links] == [D(23), D(26)]
    assert links[0].upstream == [("sleep", D(23)), ("screen_time", D(22))]
    assert links[1].slips == ["habits"] and links[1].upstream == [("sleep", D(26))]
    assert unexplained == [D(25)]


def test_auto_filled_sleep_is_never_upstream_evidence():
    days = _week({27: {"habits": "bad", "sleep": "bad"}})
    days[-1] = _day(D(27), sleep_defaulted=True, habits="bad", sleep="bad")
    links, unexplained = trace_chains(days, D(21), D(27))
    assert links == [] and unexplained == [D(27)]


def test_mondays_upstream_can_come_from_previous_sunday_lead_in():
    days = _week({20: {"screen_time": "bad"}, 21: {"habits": "bad"}})
    links, _ = trace_chains(days, D(21), D(27))
    assert links[0].upstream == [("screen_time", D(20))]


def test_clean_days_need_two_known_domains_and_no_bad_one():
    days = [
        _day(D(21), habits="good", sleep="good"),
        _day(D(22), habits="good"),               # only one domain → not clean
        _day(D(23), habits="good", sleep="bad"),  # bad domain → not clean
        _day(D(24), habits="ok", sleep="good"),
    ]
    assert clean_day_list(days) == [D(21), D(24)]
    assert count_states(days, "habits") == {"good": 3, "ok": 1, "bad": 0, "none": 0}


def test_proven_patterns_replayed_against_single_week():
    days = _week({
        21: {"sleep": "bad", "habits": "bad"},
        22: {"sleep": "bad", "habits": "bad"},
        23: {"sleep": "bad", "habits": "good"},
        24: {"sleep": "good", "habits": "good"},
    })
    result = echoes(days, D(21), D(27), ["sleep->habits", "not->apair"])
    assert len(result) == 1
    e = result[0]
    assert (e.key, e.trigger_days, e.hit_days, e.dates) == ("sleep->habits", 3, 2, [D(21), D(22)])


def test_fallback_narrative_chain_case():
    summary = {
        "chains": [{
            "slip_date": "2026-12-23", "weekday": "Wed", "slips": ["habits"],
            "caused_by": [
                {"signal": "sleep", "date": "2026-12-23", "weekday": "Wed"},
                {"signal": "screen_time", "date": "2026-12-22", "weekday": "Tue"},
            ],
        }],
        "unexplained_slips": [], "clean_days": [], "clean_day_count": 0,
    }
    text, step, days = fallback_narrative(summary)
    assert text == "Wed: habits slipped, after bad sleep (Wed) and a heavy screen day (Tue)."
    assert step.startswith("Tonight: phone charging outside")
    assert days == ["2026-12-23", "2026-12-22"]


def test_fallback_narrative_unexplained_case():
    summary = {
        "chains": [],
        "unexplained_slips": [{"date": "2026-12-25", "weekday": "Fri"}],
        "clean_days": [], "clean_day_count": 0,
    }
    text, _, _ = fallback_narrative(summary)
    assert text == "1 slip day this week had no visible cause in your logs."


def test_fallback_narrative_clean_week_case():
    summary = {
        "chains": [], "unexplained_slips": [],
        "clean_days": [{"date": "2026-12-24", "weekday": "Thu"}], "clean_day_count": 1,
    }
    text, _, _ = fallback_narrative(summary)
    assert text == "Nothing broke this week: 1 clean day."


def test_fallback_narrative_empty_week():
    summary = {"chains": [], "unexplained_slips": [], "clean_days": [], "clean_day_count": 0}
    text, step, cited = fallback_narrative(summary)
    assert "isn't enough logged" in text
    assert cited == []
