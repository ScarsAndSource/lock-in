"""
Async DB engine and session. One important operational note: Supabase's
connection pooler (pgbouncer, transaction mode) does not support prepared
statements, so asyncpg's statement cache must be disabled when connecting
through it — this is easy to miss and shows up as intermittent, confusing
errors under load rather than a clean failure at startup, which is exactly
the kind of silent failure mode this project is trying not to ship.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
