"""
Startup guard against ORM <-> SQL drift (there's no Alembic yet). Compares every
ORM table's column names to the live database. 'warn' logs loudly and keeps
booting; 'strict' refuses to start.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Base

logger = logging.getLogger("lockin.schema")


def _diff(sync_conn) -> list[str]:
    insp = inspect(sync_conn)
    problems: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.schema == "auth":  # Supabase-owned stub, never ours to check
            continue
        schema = table.schema or "public"
        if not insp.has_table(table.name, schema=schema):
            problems.append(f"missing table {schema}.{table.name} (run the migrations)")
            continue
        db_cols = {c["name"] for c in insp.get_columns(table.name, schema=schema)}
        for col in sorted({c.name for c in table.columns} - db_cols):
            problems.append(f"{schema}.{table.name} is missing column {col!r} (migration not applied?)")
    return problems


async def check_schema(engine: AsyncEngine, mode: str) -> list[str]:
    if mode == "off":
        return []
    try:
        async with engine.connect() as conn:
            problems = await conn.run_sync(_diff)
    except Exception as exc:  # noqa: BLE001 -- reported, never silent
        message = f"schema check could not run: {exc!r}"
        if mode == "strict":
            raise RuntimeError(message) from exc
        logger.error(message)
        return [message]
    for p in problems:
        logger.error("SCHEMA DRIFT: %s", p)
    if problems and mode == "strict":
        raise RuntimeError("Schema drift detected: " + "; ".join(problems))
    return problems
