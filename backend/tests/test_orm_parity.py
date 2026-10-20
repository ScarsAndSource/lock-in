"""
No-database guards for the bugs the in-memory fakes can't see: a repository passing a column its ORM class
doesn't define. Both of these used to 500 on a real Postgres (LlmUsageORM.updated_at, PauseORM.updated_at).
"""
import asyncio
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import Pause
from app.models import LlmUsageORM, PauseORM
from app.repositories.llm_usage_repository import SqlAlchemyLlmUsageRepository
from app.repositories.pause_repository import SqlAlchemyPauseRepository


class _Result:
    def scalar_one(self):
        return 1


def _recording_session():
    session = AsyncSession()
    compiled: list[str] = []
    added: list[object] = []

    async def fake_execute(stmt, *args, **kwargs):
        # Compiling against the real PostgreSQL dialect is what raised "Unconsumed column names".
        compiled.append(str(stmt.compile(dialect=postgresql.dialect())))
        return _Result()

    async def fake_flush(*args, **kwargs):
        return None

    session.execute = fake_execute  # type: ignore[method-assign]
    session.flush = fake_flush  # type: ignore[method-assign]
    session.add = added.append  # type: ignore[method-assign]
    return session, compiled, added


def test_models_define_updated_at():
    assert "updated_at" in LlmUsageORM.__table__.columns
    assert "updated_at" in PauseORM.__table__.columns


def test_llm_usage_consume_compiles_against_postgres():
    session, compiled, _ = _recording_session()
    total = asyncio.run(SqlAlchemyLlmUsageRepository(session).consume(uuid4(), date(2026, 10, 20), "chat"))
    assert total == 1
    assert any("INSERT INTO llm_usage" in sql and "updated_at" in sql for sql in compiled)


def test_pause_create_builds_a_valid_orm_row():
    session, _, added = _recording_session()
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    pause = Pause(
        id=uuid4(), user_id=uuid4(), start_date=date(2026, 10, 20), end_date=date(2026, 10, 22),
        created_at=now, habit_id=None,
    )
    asyncio.run(SqlAlchemyPauseRepository(session).create(pause))
    assert len(added) == 1 and added[0].updated_at == now
