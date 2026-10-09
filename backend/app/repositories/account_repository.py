"""
Whole-account export and delete (SPEC section 9, decision 4).

Coverage is DERIVED from the ORM metadata, never hand-listed:
  - every table in Base.metadata (except Supabase's auth.*) is exported and deleted
  - the owner column is `user_id`, or `id` for profiles
  - a table with no recognised owner column raises at import -> app won't boot
  - deliberate exceptions go in _EXEMPT_TABLES, each with a comment saying why
"""
from __future__ import annotations

import base64
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import Table, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base

_EXEMPT_TABLES: frozenset[str] = frozenset()


def _owner_column(table: Table) -> str:
    if "user_id" in table.c:
        return "user_id"
    if table.name == "profiles":
        return "id"
    raise RuntimeError(
        f"Table {table.name!r} has no 'user_id' column, so account export/delete can't scope it to a user. "
        "Add user_id, or add the table to _EXEMPT_TABLES with a written reason."
    )


def owned_tables() -> list[tuple[Table, str]]:
    """(table, owner column), PARENTS FIRST. Reverse it for deletes (children first)."""
    return [
        (t, _owner_column(t))
        for t in Base.metadata.sorted_tables
        if t.schema != "auth" and t.name not in _EXEMPT_TABLES
    ]


owned_tables()  # tripwire: fails at import if any table can't be scoped


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
        for table, owner in owned_tables():
            result = await self._session.execute(select(table).where(table.c[owner] == user_id))
            out[table.name] = [{k: json_safe(v) for k, v in row.items()} for row in result.mappings().all()]
        return out

    async def delete_everything(self, user_id: UUID) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table, owner in reversed(owned_tables()):
            result = await self._session.execute(delete(table).where(table.c[owner] == user_id))
            counts[table.name] = result.rowcount or 0
        return counts
