"""
Missions = the "best version of you in a given time frame" container.
A mission is a dated window (7-365 days) split into three phases
(foundation / build / peak) with checkpoints at 25/50/75/100%. When the window
ends it closes itself as COMPLETED -- no shame state, the data is the record.
One active mission per user (also enforced by a partial unique index).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import Mission, MissionStatus
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories.mission_repository import MissionRepository
from app.services.consistency_service import HabitConsistency
from app.services.profile_service import ProfileService
from app.services.stats_service import StatsService

_PHASES = ("foundation", "build", "peak")
_CHECKPOINTS = (25, 50, 75, 100)
_MAX_BACKDATE_DAYS = 7
_MAX_FUTURE_START_DAYS = 30


@dataclass(slots=True)
class Checkpoint:
    label: str
    day: int
    on_date: date


@dataclass(slots=True)
class MissionProgress:
    state: str  # upcoming | running | finished
    day_number: int
    days_total: int
    days_left: int
    elapsed_pct: float
    phase: str | None
    next_checkpoint: Checkpoint | None


def mission_progress(mission: Mission, today: date) -> MissionProgress:
    total = (mission.end_date - mission.start_date).days + 1
    if today < mission.start_date:
        state, day_number, days_left = "upcoming", 0, total
    elif today > mission.end_date:
        state, day_number, days_left = "finished", total, 0
    else:
        state = "running"
        day_number = (today - mission.start_date).days + 1
        days_left = (mission.end_date - today).days

    phase = None if day_number == 0 else _PHASES[min(2, (day_number - 1) * 3 // total)]

    next_checkpoint = None
    for pct in _CHECKPOINTS:
        day = math.ceil(total * pct / 100)
        if day > day_number:
            next_checkpoint = Checkpoint(f"{pct}%", day, mission.start_date + timedelta(days=day - 1))
            break

    return MissionProgress(
        state=state, day_number=day_number, days_total=total, days_left=days_left,
        elapsed_pct=round(100.0 * day_number / total, 1), phase=phase, next_checkpoint=next_checkpoint,
    )


class MissionsService:
    def __init__(self, repo: MissionRepository, stats: StatsService, profiles: ProfileService, clock: Clock = utc_now):
        self._repo = repo
        self._stats = stats
        self._profiles = profiles
        self._clock = clock

    async def _active_or_expire(self, user_id: UUID, today: date) -> Mission | None:
        active = await self._repo.get_active(user_id)
        if active is not None and today > active.end_date:
            await self._repo.set_status(user_id, active.id, MissionStatus.COMPLETED, self._clock())
            return None
        return active

    async def create(self, user_id: UUID, title: str, duration_days: int, start_date: date | None) -> Mission:
        title = title.strip()
        if not title:
            raise ValidationError("Mission title can't be blank.")
        today = await self._profiles.today(user_id)
        start = start_date or today
        if start < today - timedelta(days=_MAX_BACKDATE_DAYS) or start > today + timedelta(days=_MAX_FUTURE_START_DAYS):
            raise ValidationError(
                f"Start date must be within {_MAX_BACKDATE_DAYS} days back or {_MAX_FUTURE_START_DAYS} days ahead."
            )
        if await self._active_or_expire(user_id, today) is not None:
            raise ConflictError("You already have an active mission. End it before starting another.")
        mission = Mission(
            id=uuid4(), user_id=user_id, title=title, start_date=start,
            end_date=start + timedelta(days=duration_days - 1),
            status=MissionStatus.ACTIVE, created_at=self._clock(),
        )
        return await self._repo.create(mission)

    async def get_active_detail(
        self, user_id: UUID
    ) -> tuple[Mission, MissionProgress, float | None, list[HabitConsistency]]:
        today = await self._profiles.today(user_id)
        mission = await self._active_or_expire(user_id, today)
        if mission is None:
            raise NotFoundError("No active mission.")
        progress = mission_progress(mission, today)

        pct, items = None, []
        if progress.state != "upcoming":
            eval_end = min(today, mission.end_date)
            window = (eval_end - mission.start_date).days + 1
            _, items, pct = await self._stats.consistency(user_id, eval_end, window)
        return mission, progress, pct, items

    async def list(self, user_id: UUID) -> list[Mission]:
        await self._active_or_expire(user_id, await self._profiles.today(user_id))
        return await self._repo.list(user_id)

    async def end(self, user_id: UUID, mission_id: UUID, completed: bool) -> Mission:
        mission = await self._repo.get(user_id, mission_id)
        if mission is None:
            raise NotFoundError(f"No mission {mission_id} for this user.")
        if mission.status != MissionStatus.ACTIVE:
            raise ConflictError("This mission has already ended.")
        status = MissionStatus.COMPLETED if completed else MissionStatus.ENDED_EARLY
        updated = await self._repo.set_status(user_id, mission_id, status, self._clock())
        assert updated is not None
        return updated
