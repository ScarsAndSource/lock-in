"""
The shape of a person's day, learned from their own logs. PURE: no DB, no clock, no network.

Three ideas:
  * Times of day live on a circle (23:50 and 00:10 are 20 minutes apart), so every "typical time" is a circular
    mean, and a person whose times are all over the place simply has no rhythm yet (None), never a made-up one.
  * Risk windows are where the person's OWN urge logs cluster (a relapse counts double). Smoothed over half-hour
    buckets so one unlucky night doesn't make a window.
  * The companion speaks at moments derived from the day shape (a little after waking, a little before the usual
    check-in), nudged out of the person's quiet hours. Never a fixed hour for everybody.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.domain_companion import Observations

DAY = 1440
BUCKET = 30
BUCKETS = DAY // BUCKET

MIN_SAMPLES = 4          # fewer observations than this: no typical time
MIN_DISPERSION = 0.3     # mean resultant length below this: times are spread too evenly to call a rhythm
MIN_URGES = 5
MIN_PEAK = 2.0           # smoothed weight a bucket needs before it can anchor a window
HOT_RATIO = 0.5          # a bucket joins a window when it holds at least half the peak

MORNING_FROM_WAKE = 45
MORNING_CLAMP = (6 * 60 + 30, 10 * 60 + 30)
EVENING_BEFORE_CHECKIN = 30
EVENING_CLAMP = (19 * 60, 22 * 60 + 30)
EVENING_DEFAULT = 20 * 60 + 30
MORNING_DEFAULT = 8 * 60


@dataclass(frozen=True, slots=True)
class RiskWindow:
    start: int       # minute of local day
    end: int         # exclusive; smaller than start when the window crosses midnight
    weight: float    # share of all the urge weight that falls inside this window, 0..1


@dataclass(frozen=True, slots=True)
class Rhythm:
    wake: int | None
    bed: int | None
    checkin: int | None
    first_open: int | None
    windows: tuple[RiskWindow, ...]
    samples: int
    confidence: str  # low | medium | high


def circular_mean(minutes: tuple[int, ...] | list[int]) -> int | None:
    """Mean minute-of-day on a 24h circle, or None when there isn't enough (or consistent enough) data."""
    if len(minutes) < MIN_SAMPLES:
        return None
    sx = sum(math.cos(2 * math.pi * (m % DAY) / DAY) for m in minutes)
    sy = sum(math.sin(2 * math.pi * (m % DAY) / DAY) for m in minutes)
    if math.hypot(sx, sy) / len(minutes) < MIN_DISPERSION:
        return None
    angle = math.atan2(sy, sx) % (2 * math.pi)
    return round(angle / (2 * math.pi) * DAY) % DAY


def risk_windows(urges: tuple[tuple[int, bool], ...] | list[tuple[int, bool]]) -> tuple[RiskWindow, ...]:
    """Up to two windows where urges cluster. Empty until there are enough logs to say anything honest."""
    if len(urges) < MIN_URGES:
        return ()
    raw = [0.0] * BUCKETS
    for minute, relapsed in urges:
        raw[(minute % DAY) // BUCKET] += 2.0 if relapsed else 1.0
    smooth = [
        0.25 * raw[(i - 1) % BUCKETS] + 0.5 * raw[i] + 0.25 * raw[(i + 1) % BUCKETS] for i in range(BUCKETS)
    ]
    peak = max(smooth)
    if peak < MIN_PEAK:
        return ()
    floor = max(HOT_RATIO * peak, 1.0)
    hot = [s >= floor for s in smooth]
    if all(hot):
        return ()  # busy all day is not a window
    total = sum(smooth)
    start_at = next(i for i in range(BUCKETS) if not hot[i])   # begin the scan on a cold bucket so no run is split
    windows: list[RiskWindow] = []
    run: list[int] = []
    for step in range(1, BUCKETS + 1):
        i = (start_at + step) % BUCKETS
        if hot[i]:
            run.append(i)
        elif run:
            windows.append(_window(run, smooth, total))
            run = []
    if run:
        windows.append(_window(run, smooth, total))
    windows.sort(key=lambda w: -w.weight)
    return tuple(windows[:2])


def _window(run: list[int], smooth: list[float], total: float) -> RiskWindow:
    return RiskWindow(
        start=run[0] * BUCKET,
        end=((run[-1] + 1) * BUCKET) % DAY,
        weight=round(sum(smooth[i] for i in run) / total, 3),
    )


def window_near(rhythm: Rhythm, minute: int, lead: int = 30) -> RiskWindow | None:
    """The strongest risk window that is open now or opens within `lead` minutes, if any."""
    best: RiskWindow | None = None
    for w in rhythm.windows:
        length = (w.end - w.start) % DAY or BUCKET
        offset = (minute - (w.start - lead)) % DAY
        if offset <= length + lead and (best is None or w.weight > best.weight):
            best = w
    return best


def build_rhythm(obs: Observations) -> Rhythm:
    samples = (
        len(obs.wake_minutes) + len(obs.bed_minutes) + len(obs.checkin_minutes)
        + len(obs.first_open_minutes) + len(obs.urges)
    )
    return Rhythm(
        wake=circular_mean(obs.wake_minutes),
        bed=circular_mean(obs.bed_minutes),
        checkin=circular_mean(obs.checkin_minutes),
        first_open=circular_mean(obs.first_open_minutes),
        windows=risk_windows(obs.urges),
        samples=samples,
        confidence="high" if samples >= 60 else "medium" if samples >= 20 else "low",
    )


def in_quiet(minute: int, quiet_start: int, quiet_end: int) -> bool:
    """Minutes since midnight. start == end means no quiet hours; handles windows that wrap midnight."""
    if quiet_start == quiet_end:
        return False
    if quiet_start < quiet_end:
        return quiet_start <= minute < quiet_end
    return minute >= quiet_start or minute < quiet_end


def morning_at(rhythm: Rhythm) -> int:
    """A little after waking (or the usual first app open), kept inside a sane morning band."""
    if rhythm.wake is not None:
        base = rhythm.wake + MORNING_FROM_WAKE
    else:
        base = rhythm.first_open if rhythm.first_open is not None else MORNING_DEFAULT
    return min(max(base, MORNING_CLAMP[0]), MORNING_CLAMP[1])


def evening_at(rhythm: Rhythm) -> int:
    """A little before the usual check-in time, kept inside a sane evening band. Also when "close today" takes over."""
    base = rhythm.checkin - EVENING_BEFORE_CHECKIN if rhythm.checkin is not None else EVENING_DEFAULT
    return min(max(base, EVENING_CLAMP[0]), EVENING_CLAMP[1])


def moment_times(rhythm: Rhythm, quiet_start: int, quiet_end: int) -> dict[str, int]:
    """When the companion speaks, moved out of the person's quiet hours."""
    morning, evening = morning_at(rhythm), evening_at(rhythm)
    if in_quiet(morning, quiet_start, quiet_end):
        morning = (quiet_end + 15) % DAY
    if in_quiet(evening, quiet_start, quiet_end):
        evening = (quiet_start - 60) % DAY
    return {"morning": morning, "evening": evening}
