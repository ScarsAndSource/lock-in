from __future__ import annotations

from datetime import date
from uuid import UUID

from app.dates import Clock, user_today, utc_now, validate_timezone
from app.domain import Profile
from app.repositories.profile_repository import ProfileRepository


class ProfileService:
    def __init__(self, repo: ProfileRepository, clock: Clock = utc_now):
        self._repo = repo
        self._clock = clock

    async def get(self, user_id: UUID) -> Profile:
        return await self._repo.get_or_create(user_id)

    async def set_timezone(self, user_id: UUID, tz_name: str) -> Profile:
        return await self._repo.set_timezone(user_id, validate_timezone(tz_name))

    async def today(self, user_id: UUID) -> date:
        profile = await self.get(user_id)
        return user_today(profile.timezone, self._clock)
