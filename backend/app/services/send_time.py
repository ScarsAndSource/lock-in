"""
Adaptive send time: WHEN the companion speaks, learned from what the person actually does with it.

The learned rhythm (rhythm.moment_times) gives a sensible starting hour for each moment. This module lets the person's
own responses move it, one local hour at a time, without ever becoming a slot machine:

  * Each candidate hour keeps two counts from the last 90 days: acted (opened the app within ACT_WINDOW of the push)
    and ignored. A Beta(prior + acted, prior + ignored) belief per hour, one draw each, highest draw wins (Thompson sampling).
    The learned hour carries a head start (Beta(2, 1)) and untried hours a mild handicap (Beta(1, 2)), so the app
    doesn't wander off a good time on thin data; trying other hours blindly is the explore floor's job, below.
  * Cold start: until there are MIN_OBSERVATIONS settled sends in the candidate hours, the learned hour is used as is.
  * Explore floor: EXPLORE_RATE of days pick a candidate uniformly, so an hour that was unlucky early is never buried.
  * Candidates stay inside the same sane band as the learned time (morning 06:30-10:30, evening 19:00-22:30),
    within +-SPAN_HOURS of it, and never inside the person's quiet hours.
  * STABLE WITHIN A DAY: the random stream is seeded by (user, local date, kind) and outcomes only settle for days that
    are already over, so every 5-minute cron run on a given day lands on the same hour.

Pure functions (choose_send_hour, candidate_hours, adapt_moment_times, was_acted) are unit-tested without a database.
SendTimeService is the thin async shell the tick job calls.
"""
from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from app.dates import Clock, utc_now
from app.repositories.companion_repository import CompanionRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.send_time_repository import Outcome, SendTimeRepository
from app.services.profile_service import ProfileService
from app.services.rhythm import DAY, EVENING_CLAMP, MORNING_CLAMP, build_rhythm, in_quiet, moment_times
from app.services.task_time import zone

KINDS = ("morning", "evening")
BANDS = {"morning": MORNING_CLAMP, "evening": EVENING_CLAMP}

SPAN_HOURS = 2
MIN_OBSERVATIONS = 6
EXPLORE_RATE = 0.10
PRIOR_LEARNED = (2.0, 1.0)
PRIOR_OTHER = (1.0, 2.0)   # untried hours start a little pessimistic; blind exploration is the explore floor's job
STATS_LOOKBACK_DAYS = 90
SETTLE_LOOKBACK_DAYS = 7
ACT_WINDOW = timedelta(minutes=60)
RHYTHM_LOOKBACK_DAYS = 60
OPEN_KINDS = ("app_open", "push_opened")


@dataclass(frozen=True, slots=True)
class HourStats:
    acted: int = 0
    ignored: int = 0

    @property
    def n(self) -> int:
        return self.acted + self.ignored


@dataclass(frozen=True, slots=True)
class HourChoice:
    hour: int
    explored: bool
    reason: str   # cold_start | explore | thompson


def day_rng(user_id: UUID, day: date, kind: str) -> random.Random:
    """Deterministic per (user, local day, kind): str seeds are hashed with SHA-512, stable across processes."""
    return random.Random(f"send-time:{user_id}:{day.isoformat()}:{kind}")


def candidate_hours(kind: str, base_minute: int, quiet_start: int, quiet_end: int) -> list[int]:
    lo, hi = BANDS[kind]
    base_hour = (base_minute % DAY) // 60
    hours = [
        h for h in range(base_hour - SPAN_HOURS, base_hour + SPAN_HOURS + 1)
        if lo // 60 <= h <= hi // 60 and not in_quiet(h * 60 + 15, quiet_start, quiet_end)
    ]
    if base_hour not in hours:   # the learned time is already quiet-adjusted; it is always a legal choice
        hours = sorted([*hours, base_hour])
    return hours


def choose_send_hour(
    kind: str, base_minute: int, quiet_start: int, quiet_end: int,
    stats: Mapping[int, HourStats], rng: random.Random,
) -> HourChoice:
    cands = candidate_hours(kind, base_minute, quiet_start, quiet_end)
    base_hour = (base_minute % DAY) // 60
    if sum(stats.get(h, HourStats()).n for h in cands) < MIN_OBSERVATIONS:
        return HourChoice(base_hour, False, "cold_start")
    if rng.random() < EXPLORE_RATE:
        return HourChoice(rng.choice(cands), True, "explore")
    best, best_draw = base_hour, -1.0
    for h in cands:
        s = stats.get(h, HourStats())
        a0, b0 = PRIOR_LEARNED if h == base_hour else PRIOR_OTHER
        draw = rng.betavariate(a0 + s.acted, b0 + s.ignored)
        closer = abs(h - base_hour) < abs(best - base_hour)
        if draw > best_draw or (draw == best_draw and closer):
            best, best_draw = h, draw
    return HourChoice(best, False, "thompson")


def adapt_moment_times(
    times: Mapping[str, int], hours: Mapping[str, int], quiet_start: int, quiet_end: int,
) -> dict[str, int]:
    """Move each moment to its chosen hour, keeping the learned minute-within-hour; never into quiet hours."""
    out = dict(times)
    for kind, hour in hours.items():
        base = times[kind]
        if base // 60 == hour:
            continue
        moved = hour * 60 + base % 60
        if not in_quiet(moved, quiet_start, quiet_end):
            out[kind] = moved
    return out


def was_acted(sent_at: datetime, event_times: Sequence[datetime], window: timedelta = ACT_WINDOW) -> bool:
    """Acted = any app open / push open within the window after the send."""
    return any(sent_at <= ts <= sent_at + window for ts in event_times)


def _minute(t) -> int:
    return t.hour * 60 + t.minute


class SendTimeService:
    def __init__(
        self, repo: SendTimeRepository, companion_repo: CompanionRepository, notif_repo: NotificationRepository,
        profiles: ProfileService, clock: Clock = utc_now,
    ):
        self._repo, self._companion, self._notif, self._profiles, self._clock = repo, companion_repo, notif_repo, profiles, clock

    async def hours_for(
        self, user_id: UUID, times: Mapping[str, int], quiet_start: int, quiet_end: int, today: date,
    ) -> dict[str, int]:
        """What the tick job calls: one aggregate query, given the learned times it already has."""
        raw = await self._repo.hour_stats(user_id, today - timedelta(days=STATS_LOOKBACK_DAYS))
        return {
            k: choose_send_hour(
                k, times[k], quiet_start, quiet_end,
                {h: HourStats(a, i) for h, (a, i) in raw.get(k, {}).items()}, day_rng(user_id, today, k),
            ).hour
            for k in KINDS
        }

    async def best_send_hour(self, user_id: UUID, kind: str) -> int:
        """The frozen contract: the local hour this moment should go out today."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        now = self._clock()
        tz = zone((await self._profiles.get(user_id)).timezone)
        prefs = await self._notif.get_prefs(user_id)
        qs, qe = _minute(prefs.quiet_start), _minute(prefs.quiet_end)
        rhythm = build_rhythm(await self._companion.observations(user_id, tz, now, RHYTHM_LOOKBACK_DAYS))
        today = now.astimezone(tz).date()
        return (await self.hours_for(user_id, moment_times(rhythm, qs, qe), qs, qe, today))[kind]

    async def settle(self, user_id: UUID) -> int:
        """Turn yesterday-and-earlier sent moments into outcomes. Run once per user before the tick."""
        now = self._clock()
        tz = zone((await self._profiles.get(user_id)).timezone)
        today = now.astimezone(tz).date()
        pending = await self._repo.unsettled(user_id, today - timedelta(days=SETTLE_LOOKBACK_DAYS), today)
        if not pending:
            return 0
        events = await self._repo.event_times(
            user_id, OPEN_KINDS, min(p.sent_at for p in pending), max(p.sent_at for p in pending) + ACT_WINDOW,
        )
        await self._repo.record(user_id, [
            Outcome(p.kind, p.moment_date, p.sent_at.astimezone(tz).hour, was_acted(p.sent_at, events))
            for p in pending
        ], now)
        return len(pending)
