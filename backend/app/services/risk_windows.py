"""
Risk windows: the hours (and weekdays) when this person's urges actually cluster, found from their OWN urge log.

PURE: no DB, no clock, no network. Only timestamps go in; only counts come out. Free text (trigger, coping, note) is
never read here, so the encrypted detail never leaves the urges service.

A window is a run of 1-3 adjacent local hours that:
  * holds at least MIN_EVENTS urges on at least MIN_DISTINCT_DAYS different days, and
  * holds at least MIN_SHARE of ALL urges in the lookback (urges spread evenly over the day have no window).
It FADES: a window with no urge in the last RECENT_DAYS days is reported with recent_events == 0 and the planner
stops pushing for it (the behaviour changed; the app should stop talking about it).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

LOOKBACK_DAYS = 60
RECENT_DAYS = 21
MIN_EVENTS = 4
MIN_DISTINCT_DAYS = 3
MIN_SHARE = 0.25
MAX_RUN_HOURS = 3
MIN_HOUR_COUNT = 2            # an hour must hold this many urges to join a run
WEEKDAY_MIN_EVENTS = 8        # below this, weekdays are noise: the window applies every day
WEEKDAY_MIN_SHARE = 0.20      # a weekday joins the window when it holds this share of the window's urges
WEEKDAY_MIN_COVERAGE = 0.70   # ...and the kept weekdays must explain at least this share, else every day


@dataclass(frozen=True, slots=True)
class RiskWindow:
    start_hour: int                  # local hour the window opens
    end_hour: int                    # local hour it closes (exclusive, wraps past midnight)
    weekdays: frozenset[int]         # 0=Mon .. 6=Sun; all seven when there is no weekday pattern
    events: int
    recent_events: int

    @property
    def start(self) -> time:
        return time(self.start_hour, 0)


def _runs(counts: list[int]) -> list[list[int]]:
    """Circular runs of adjacent hours holding >= MIN_HOUR_COUNT urges (23 and 0 are neighbours)."""
    hot = [c >= MIN_HOUR_COUNT for c in counts]
    if all(hot):
        return []
    if not any(hot):
        return []
    pivot = hot.index(False)           # rotate so a gap sits at the start: no run straddles the seam
    order = [(pivot + i) % 24 for i in range(24)]
    runs: list[list[int]] = []
    cur: list[int] = []
    for h in order:
        if hot[h]:
            cur.append(h)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def _split_long(run: list[int], counts: list[int]) -> list[int]:
    """A run longer than MAX_RUN_HOURS is 'urges all evening', not one window: keep its best MAX_RUN_HOURS stretch."""
    if len(run) <= MAX_RUN_HOURS:
        return run
    best = max(range(len(run) - MAX_RUN_HOURS + 1), key=lambda i: sum(counts[h] for h in run[i:i + MAX_RUN_HOURS]))
    return run[best:best + MAX_RUN_HOURS]


def find_windows(
    events: Sequence[datetime], tz: ZoneInfo, now: datetime, *, max_windows: int = 2,
) -> list[RiskWindow]:
    since = now - timedelta(days=LOOKBACK_DAYS)
    local = [e.astimezone(tz) for e in events if since <= e <= now]
    if len(local) < MIN_EVENTS:
        return []
    counts = [0] * 24
    for e in local:
        counts[e.hour] += 1
    total = len(local)

    found: list[RiskWindow] = []
    for run in _runs(counts):
        run = _split_long(run, counts)
        hours = set(run)
        inside = [e for e in local if e.hour in hours]
        if len(inside) < MIN_EVENTS or len(inside) / total < MIN_SHARE:
            continue
        if len({e.date() for e in inside}) < MIN_DISTINCT_DAYS:
            continue
        weekdays = frozenset(range(7))
        if len(inside) >= WEEKDAY_MIN_EVENTS:
            by_day = Counter(e.weekday() for e in inside)
            kept = frozenset(d for d, c in by_day.items() if c / len(inside) >= WEEKDAY_MIN_SHARE)
            if kept and sum(by_day[d] for d in kept) / len(inside) >= WEEKDAY_MIN_COVERAGE:
                weekdays = kept
        recent_cut = now - timedelta(days=RECENT_DAYS)
        found.append(RiskWindow(
            start_hour=run[0], end_hour=(run[-1] + 1) % 24, weekdays=weekdays, events=len(inside),
            recent_events=sum(1 for e in inside if e.astimezone(tz) >= recent_cut.astimezone(tz)),
        ))
    found.sort(key=lambda w: (-w.events, w.start_hour))
    return found[:max_windows]
