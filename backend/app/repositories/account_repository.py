"""Whole-account export and delete (SPEC section 9, decision 4)."""
from __future__ import annotations

import base64
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import delete, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DailyCheckinORM, HabitDefinitionORM, HabitLogORM, MissionORM,
    ProfileORM, ScreenTimeLogORM, SleepLogORM, WeeklyRetroORM,
)

# (model, owner column). Delete order: children before parents.
_TABLES = [
    (HabitLogORM, "user_id"), (DailyCheckinORM, "user_id"), (SleepLogORM, "user_id"),
    (ScreenTimeLogORM, "user_id"), (MissionORM, "user_id"), (WeeklyRetroORM, "user_id"),
    (HabitDefinitionORM, "user_id"), (ProfileORM, "id"),
]



def json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


class AccountRepository(Protocol):
    async def export(self, user_id: UUID) -> dict[str, list[dict]]: ...

    async def delete_everything(self, user_id: UUID) -> dict[str, int]: ...


class SqlAlchemyAccountRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def export(self, user_id: UUID) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for model, owner_col in reversed(_TABLES):
            rows = (await self._session.execute(
                select(model).where(getattr(model, owner_col) == user_id)
            )).scalars().all()
            keys = [a.key for a in sa_inspect(model).column_attrs]
            out[model.__tablename__] = [{k: json_safe(getattr(r, k)) for k in keys} for r in rows]
        return out

    async def delete_everything(self, user_id: UUID) -> dict[str, int]:
        counts: dict[str, int] = {}
        for model, owner_col in _TABLES:
            result = await self._session.execute(delete(model).where(getattr(model, owner_col) == user_id))
            counts[model.__tablename__] = result.rowcount or 0
        return counts
