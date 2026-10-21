"""
Inference chips: when the person hasn't logged a night, say what the phone already knows and ask ONE yes/no question
("~6.5h, right?") instead of an empty form.

Evidence, strongest first, for the night that ENDS on `day` (sleep logs are keyed by the wake date):
  1. a real (non-default) half-log: a bedtime or wake time from an ingest automation or the person's own entry
  2. the night gap in the events spine: the longest stretch with no app activity between 18:00 the evening before and
     14:00 on `day`. The last open before it ~ bedtime, the first open after it ~ wake. Only trusted when the gap is
     clearly the night (>= 4h, far longer than any other gap) and starts/ends at believable clock times.
  3. the person's own typical bed / wake (rhythm), for ONE missing end only, and flagged low confidence.

It never invents a night out of nothing: both ends from the typical day is `compute_sleep_default`'s job, not a chip.
A full real log means there is nothing to ask. A proxy that contradicts a logged end by more than 90 minutes is dropped.
Pure functions below; InferenceService is the async shell.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.dates import Clock, utc_now
from app.repositories.companion_repository import CompanionRepository
from app.repositories.send_time_repository import SendTimeRepository
from app.repositories.sleep_repository import SleepRepository
from app.services.profile_service import ProfileService
from app.services.rhythm import DAY, Rhythm, build_rhythm
from app.services.task_time import zone

WINDOW_START_HOUR = 18          # evening before `day`
WINDOW_END_HOUR = 14            # on `day`
MIN_GAP = timedelta(hours=4)
MAX_GAP = timedelta(hours=14)
CLEAR_RATIO = 0.6               # the next-longest gap must be <= 60% of the night gap
BED_LAG = timedelta(minutes=10)   # people put the phone down a little before lights out
WAKE_LAG = timedelta(minutes=10)  # ...and pick it up a little after waking
MIN_SLEEP, MAX_SLEEP = 180, 840
CONTRADICTION_MIN = 90
MAX_AGE_DAYS = 2
RHYTHM_LOOKBACK_DAYS = 60
OPEN_KINDS = ("app_open", "push_opened")


@dataclass(frozen=True, slots=True)
class NightProxy:
    bed: int    # minute of local day
    wake: int


@dataclass(frozen=True, slots=True)
class Inference:
    day: date
    kind: str                     # "sleep"
    bed: int
    wake: int
    duration_minutes: int
    confidence: str               # low | medium | high
    basis: tuple[str, ...]
    prompt: str


def _m(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def circ_diff(a: int, b: int) -> int:
    d = abs(a - b) % DAY
    return min(d, DAY - d)


def fmt_hours(minutes: int) -> str:
    return f"{round(minutes / 30) / 2:g}h"


def hhmm(minute: int) -> str:
    minute %= DAY
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _believable_bed(minute: int) -> bool:
    return minute >= 20 * 60 or minute <= 5 * 60


def _believable_wake(minute: int) -> bool:
    return 3 * 60 <= minute <= 12 * 60


def night_proxy(day: date, opens_local: Sequence[datetime], tz: ZoneInfo) -> NightProxy | None:
    start = datetime.combine(day - timedelta(days=1), time(WINDOW_START_HOUR), tzinfo=tz)
    end = datetime.combine(day, time(WINDOW_END_HOUR), tzinfo=tz)
    ts = sorted(t for t in opens_local if start <= t <= end)
    if len(ts) < 2:
        return None
    gaps = sorted(((b - a, a, b) for a, b in zip(ts, ts[1:])), key=lambda g: g[0], reverse=True)
    longest, a, b = gaps[0]
    if not MIN_GAP <= longest <= MAX_GAP:
        return None
    if len(gaps) > 1 and gaps[1][0] > CLEAR_RATIO * longest:
        return None
    bed_dt, wake_dt = a + BED_LAG, b - WAKE_LAG
    minutes = (wake_dt - bed_dt).total_seconds() / 60
    if not MIN_SLEEP <= minutes <= MAX_SLEEP:
        return None
    if not (_believable_bed(_m(bed_dt)) and _believable_wake(_m(wake_dt))):
        return None
    return NightProxy(_m(bed_dt), _m(wake_dt))


def reconcile(proxy: NightProxy | None, logged_bed: int | None, logged_wake: int | None) -> NightProxy | None:
    """A proxy that disagrees with something the person actually logged is not trusted."""
    if proxy is None:
        return None
    if logged_bed is not None and circ_diff(proxy.bed, logged_bed) > CONTRADICTION_MIN:
        return None
    if logged_wake is not None and circ_diff(proxy.wake, logged_wake) > CONTRADICTION_MIN:
        return None
    return proxy


def needs_rhythm(logged_bed: int | None, logged_wake: int | None, proxy: NightProxy | None) -> bool:
    has_bed = logged_bed is not None or proxy is not None
    has_wake = logged_wake is not None or proxy is not None
    return not (has_bed and has_wake)


def infer_night(
    day: date, logged_bed: int | None, logged_wake: int | None, proxy: NightProxy | None, rhythm: Rhythm | None,
) -> Inference | None:
    if logged_bed is not None and logged_wake is not None:
        return None   # a full real log: nothing to ask

    if logged_bed is not None:
        bed, bed_src = logged_bed, "logged_bed"
    elif proxy is not None:
        bed, bed_src = proxy.bed, "last_open"
    elif rhythm is not None and rhythm.bed is not None:
        bed, bed_src = rhythm.bed, "rhythm_bed"
    else:
        return None

    if logged_wake is not None:
        wake, wake_src = logged_wake, "logged_wake"
    elif proxy is not None:
        wake, wake_src = proxy.wake, "first_open"
    elif rhythm is not None and rhythm.wake is not None:
        wake, wake_src = rhythm.wake, "rhythm_wake"
    else:
        return None

    if bed_src.startswith("rhythm") and wake_src.startswith("rhythm"):
        return None   # that is just "same as usual", not evidence

    duration = (wake - bed) % DAY
    if not MIN_SLEEP <= duration <= MAX_SLEEP:
        return None

    if bed_src.startswith("rhythm") or wake_src.startswith("rhythm"):
        confidence = "low"
    elif bed_src == "logged_bed" or wake_src == "logged_wake":
        confidence = "high"
    else:
        confidence = "medium"
    return Inference(
        day=day, kind="sleep", bed=bed, wake=wake, duration_minutes=duration, confidence=confidence,
        basis=(bed_src, wake_src), prompt=f"~{fmt_hours(duration)}, right?",
    )


class InferenceService:
    def __init__(
        self, sleep_repo: SleepRepository, events: SendTimeRepository, companion_repo: CompanionRepository,
        profiles: ProfileService, clock: Clock = utc_now,
    ):
        self._sleep, self._events, self._companion, self._profiles, self._clock = sleep_repo, events, companion_repo, profiles, clock

    async def infer_sleep(self, user_id: UUID, day: date) -> Inference | None:
        """The frozen contract. None = nothing worth asking."""
        now = self._clock()
        tz = zone((await self._profiles.get(user_id)).timezone)
        today = now.astimezone(tz).date()
        if not today - timedelta(days=MAX_AGE_DAYS) <= day <= today:
            return None

        existing = await self._sleep.get_log(user_id, day)
        real = existing if existing is not None and not existing.is_default else None
        logged_bed = real.time_to_bed.hour * 60 + real.time_to_bed.minute if real and real.time_to_bed else None
        logged_wake = real.time_woke.hour * 60 + real.time_woke.minute if real and real.time_woke else None
        if logged_bed is not None and logged_wake is not None:
            return None

        start = datetime.combine(day - timedelta(days=1), time(WINDOW_START_HOUR), tzinfo=tz)
        end = min(datetime.combine(day, time(WINDOW_END_HOUR), tzinfo=tz), now)
        opens = [t.astimezone(tz) for t in await self._events.event_times(user_id, OPEN_KINDS, start, end)]
        proxy = reconcile(night_proxy(day, opens, tz), logged_bed, logged_wake)
        if logged_bed is None and logged_wake is None and proxy is None:
            return None

        rhythm = None
        if needs_rhythm(logged_bed, logged_wake, proxy):
            rhythm = build_rhythm(await self._companion.observations(user_id, tz, now, RHYTHM_LOOKBACK_DAYS))
        return infer_night(day, logged_bed, logged_wake, proxy, rhythm)
