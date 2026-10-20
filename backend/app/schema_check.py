"""
Startup guard against ORM <-> SQL drift (there's no Alembic yet). Compares every
ORM table's column names to the live database, in BOTH directions:
  - an ORM column the database lacks (migration not applied), and
  - a NOT NULL column with no default that the ORM doesn't know about (every insert would fail).
'warn' logs loudly and keeps booting; 'strict' refuses to start.
(The remaining drift -- code passing a column the ORM class doesn't define -- is caught by
tests/test_orm_parity.py, which needs no database.)
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
        orm_cols = {c.name for c in table.columns}
        for c in insp.get_columns(table.name, schema=schema):
            if c["name"] in orm_cols:
                continue
            required = (
                not c.get("nullable", True)
                and c.get("default") is None
                and not c.get("autoincrement")
                and not c.get("identity")
            )
            if required:
                problems.append(
                    f"{schema}.{table.name}.{c['name']} is NOT NULL with no default but the ORM model "
                    "doesn't define it (inserts will fail)"
                )
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
