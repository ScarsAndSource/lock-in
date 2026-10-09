"""
Pure weekly-retro logic: "here's the chain that actually happened".

A SLIP is a day where habits, study, or urges went BAD. For each slip we look at
the signals that came just before it:
    sleep (same day: sleep is dated by wake-up day)
    screen_time (same day, and the day before)
    urges (the day before: a relapse the night before)
and report those that were BAD. Slips with no visible upstream signal are reported
honestly as unexplained -- never given an invented cause.
Auto-filled (defaulted) sleep/screen rows never count as evidence.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app.services.chain_service import BAD, GOOD, NONE, OK, ChainDay
from app.services.narration import fallback_next_step
from app.services.pattern_service import PAIRS

DOMAINS = ("habits", "sleep", "screen_time", "study", "urges")
SLIP_DOMAINS = ("habits", "study", "urges")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MAX_WEEKS_BACK = 26
_MAX_LINKS = 3

_SLIP_WORDS = {"habits": "habits slipped", "study": "study fell short", "urges": "a relapse"}
_CAUSE_WORDS = {"sleep": "bad sleep", "screen_time": "a heavy screen day", "urges": "a relapse"}


def weekday_label(day: date) -> str:
    return _WEEKDAYS[day.weekday()]


def week_bounds(today: date, requested_start: date | None) -> tuple[date, date]:
    """The most recent COMPLETED Mon-Sun week by default. Raises ValueError with a user-facing message."""
    this_monday = today - timedelta(days=today.weekday())
    start = requested_start or (this_monday - timedelta(days=7))
    if start.weekday() != 0:
        raise ValueError("week_start must be a Monday.")
    end = start + timedelta(days=6)
    if end >= today:
        raise ValueError("That week isn't over yet.")
    if (today - start).days > _MAX_WEEKS_BACK * 7:
        raise ValueError(f"That week is more than {_MAX_WEEKS_BACK} weeks back.")
    return start, end


def count_states(days: list[ChainDay], domain: str) -> dict[str, int]:
    counts = {GOOD: 0, OK: 0, BAD: 0, NONE: 0}
    for d in days:
        counts[getattr(d, domain, NONE)] += 1
    return counts


def _usable(day: ChainDay, domain: str) -> bool:
    return getattr(day, domain, NONE) != NONE and not getattr(day, f"{domain}_defaulted", False)


def _bad(day: ChainDay | None, domain: str) -> bool:
    return day is not None and getattr(day, domain, NONE) == BAD and _usable(day, domain)



@dataclass(slots=True)
class ChainLink:
    slip_day: date
    slips: list[str]
    upstream: list[tuple[str, date]]   # (signal domain, the day it was bad)


def trace_chains(
    days: list[ChainDay], week_start: date, week_end: date, max_links: int = _MAX_LINKS
) -> tuple[list[ChainLink], list[date]]:
    """days must include the day BEFORE week_start so Monday's upstream is visible."""
    by_day = {d.day: d for d in days}
    links: list[ChainLink] = []
    unexplained: list[date] = []

    for day in sorted(by_day):
        if not week_start <= day <= week_end:
            continue
        today = by_day[day]
        slips = [dom for dom in SLIP_DOMAINS if _bad(today, dom)]
        if not slips:
            continue
        prev = by_day.get(day - timedelta(days=1))
        upstream: list[tuple[str, date]] = []
        if _bad(today, "sleep"):
            upstream.append(("sleep", day))
        if _bad(today, "screen_time"):
            upstream.append(("screen_time", day))
        if _bad(prev, "screen_time"):
            upstream.append(("screen_time", prev.day))
        if "urges" not in slips and _bad(prev, "urges"):
            upstream.append(("urges", prev.day))
        if upstream:
            links.append(ChainLink(day, slips, upstream))
        else:
            unexplained.append(day)

    links.sort(key=lambda l: (-len(l.upstream), -len(l.slips), l.slip_day))
    return links[:max_links], unexplained


def clean_day_list(week_days: list[ChainDay]) -> list[date]:
    """Days where nothing broke: at least two domains had data and none went bad."""
    clean = []
    for d in week_days:
        known = [getattr(d, dom, NONE) for dom in DOMAINS if getattr(d, dom, NONE) != NONE]
        if len(known) >= 2 and BAD not in known:
            clean.append(d.day)
    return clean


@dataclass(slots=True)
class PatternEcho:
    key: str
    trigger_days: int
    hit_days: int
    dates: list[date]   # trigger days where the outcome followed


def echoes(days: list[ChainDay], week_start: date, week_end: date, keys: list[str]) -> list[PatternEcho]:
    """Did the user's PROVEN patterns (from /stats/patterns) show up again this week?"""
    by_day = {d.day: d for d in days}
    result: list[PatternEcho] = []
    for key in keys:
        pair = next((p for p in PAIRS if f"{p[0]}->{p[1]}" == key), None)
        if pair is None:
            continue
        trigger, outcome, lag = pair[0], pair[1], pair[2]
        trigger_days, hits = 0, []
        for day in sorted(by_day):
            if not week_start <= day <= week_end:
                continue
            d, o = by_day[day], by_day.get(day + timedelta(days=lag))
            if o is None or not _usable(d, trigger) or not _usable(o, outcome):
                continue
            if getattr(d, trigger, NONE) == BAD:
                trigger_days += 1
                if getattr(o, outcome, NONE) == BAD:
                    hits.append(day)
        if trigger_days:
            result.append(PatternEcho(key, trigger_days, len(hits), hits))
    return result


def build_summary(
    *, week_start: date, week_end: date, days8: list[ChainDay], prev_days: list[ChainDay],
    habit_now: list, habit_prev: list, overall_now: float | None, overall_prev: float | None,
    pattern_keys: list[str], study_now, study_prev, urge_now, urge_prev_rate: float | None,
    mission: dict | None, label: Callable[[str], str],
) -> dict:
    """The stored summary AND the facts the model sees. JSON-safe, user text only via `label`."""
    week_days = [d for d in days8 if week_start <= d.day <= week_end]
    links, unexplained = trace_chains(days8, week_start, week_end)
    clean = clean_day_list(week_days)

    domains = {}
    for dom in DOMAINS:
        now, prev = count_states(week_days, dom), count_states(prev_days, dom)
        domains[dom] = {**now, "prev_bad": prev[BAD], "prev_known": prev[GOOD] + prev[OK] + prev[BAD]}

    prev_by_id = {h.habit_id: h for h in habit_prev}
    changes = []
    for h in habit_now:
        p = prev_by_id.get(h.habit_id)
        if h.consistency_pct is None or p is None or p.consistency_pct is None or p.logged_days < 3:
            continue  # no honest comparison without last week's data
        changes.append({
            "name": label(h.habit_name), "consistency_pct": h.consistency_pct,
            "prev_pct": p.consistency_pct, "delta_pct": round(h.consistency_pct - p.consistency_pct, 1),
        })
    changes.sort(key=lambda c: abs(c["delta_pct"]), reverse=True)

    def stamp(day: date) -> dict:
        return {"date": day.isoformat(), "weekday": weekday_label(day)}

    return {
        "week": {"start": week_start.isoformat(), "end": week_end.isoformat(), "days": 7},
        "days": [
            {**stamp(d.day), "habits": d.habits, "sleep": d.sleep, "screen_time": d.screen_time,
             "study": getattr(d, "study", NONE), "urges": getattr(d, "urges", NONE)}
            for d in week_days
        ],
        "domains": domains,
        "habit_overall_pct": overall_now,
        "habit_overall_prev_pct": overall_prev,
        "habit_changes": changes[:5],
        "chains": [
            {"slip_date": l.slip_day.isoformat(), "weekday": weekday_label(l.slip_day), "slips": l.slips,
             "caused_by": [{"signal": sig, **stamp(day)} for sig, day in l.upstream]}
            for l in links
        ],
        "unexplained_slips": [stamp(d) for d in unexplained],
        "clean_days": [stamp(d) for d in clean],
        "clean_day_count": len(clean),
        "pattern_echoes": [
            {"key": e.key, "trigger_days": e.trigger_days, "hit_days": e.hit_days,
             "dates": [d.isoformat() for d in e.dates]}
            for e in echoes(days8, week_start, week_end, pattern_keys)
        ],
        "study": {
            "actual_minutes": study_now.total_actual, "planned_minutes": study_now.total_planned,
            "follow_through_pct": study_now.follow_through_pct, "days_studied": study_now.days_studied,
            "prev_actual_minutes": study_prev.total_actual,
        },
        "urges": {
            "total": urge_now.total, "resisted": urge_now.resisted, "relapsed": urge_now.relapsed,
            "resist_rate_pct": urge_now.resist_rate_pct, "prev_resist_rate_pct": urge_prev_rate,
            "relapse_free_days_pct": urge_now.relapse_free_days_pct,
        },
        "mission": mission,
    }


def _cause_phrase(item: dict) -> str:
    return f"{_CAUSE_WORDS[item['signal']]} ({item['weekday']})"


def fallback_narrative(summary: dict) -> tuple[str, str, list[str]]:
    """(narrative, next_step, cited_days) built from structure alone, for when the model can't be trusted."""
    if summary["chains"]:
        c = summary["chains"][0]
        slips = " and ".join(_SLIP_WORDS[s] for s in c["slips"])
        causes = " and ".join(_cause_phrase(u) for u in c["caused_by"])
        step = fallback_next_step(f"{c['caused_by'][0]['signal']}->{c['slips'][0]}")
        days = [c["slip_date"], *[u["date"] for u in c["caused_by"]]]
        return f"{c['weekday']}: {slips}, after {causes}.", step, list(dict.fromkeys(days))

    if summary["unexplained_slips"]:
        n = len(summary["unexplained_slips"])
        return (
            f"{n} slip day{'s' if n != 1 else ''} this week had no visible cause in your logs.",
            "Log sleep and screen time every day next week so the cause shows up.",
            [u["date"] for u in summary["unexplained_slips"][:3]],
        )

    if summary["clean_days"]:
        n = summary["clean_day_count"]
        return (
            f"Nothing broke this week: {n} clean day{'s' if n != 1 else ''}.",
            "Run next week the same way and keep logging so the pattern stays visible.",
            [c["date"] for c in summary["clean_days"][:3]],
        )

    return (
        "There isn't enough logged this week to trace a chain.",
        "Log every day next week, even rough numbers.",
        [],
    )
