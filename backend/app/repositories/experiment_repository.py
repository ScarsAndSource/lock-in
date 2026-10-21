from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain_experiments import Experiment
from app.exceptions import ConflictError
from app.models import ExperimentORM


class ExperimentRepository(Protocol):
    async def create(self, exp: Experiment) -> Experiment: ...

    async def get(self, user_id: UUID, exp_id: UUID) -> Experiment | None: ...

    async def get_active(self, user_id: UUID) -> Experiment | None: ...

    async def list_recent(self, user_id: UUID, limit: int) -> list[Experiment]: ...

    async def close(
        self, user_id: UUID, exp_id: UUID, status: str, result: dict | None, now: datetime
    ) -> Experiment | None: ...


def _from_orm(row: ExperimentORM) -> Experiment:
    return Experiment(
        id=row.id, user_id=row.user_id, title=row.title, change=row.change_text, metric=row.metric,
        direction=row.direction, baseline_days=row.baseline_days, treatment_days=row.treatment_days,
        start_date=row.start_date, status=row.status, result=row.result,
        created_at=row.created_at, updated_at=row.updated_at,
    )


class SqlAlchemyExperimentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, exp: Experiment) -> Experiment:
        row = ExperimentORM(
            id=exp.id, user_id=exp.user_id, title=exp.title, change_text=exp.change, metric=exp.metric,
            direction=exp.direction, baseline_days=exp.baseline_days, treatment_days=exp.treatment_days,
            start_date=exp.start_date, status=exp.status, result=exp.result,
            created_at=exp.created_at, updated_at=exp.updated_at,
        )
        try:
            # Savepoint: a lost race on the one-active-run index must not poison the whole request transaction.
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError("You already have an experiment running. Finish it or drop it first.") from exc
        return _from_orm(row)

    async def get(self, user_id: UUID, exp_id: UUID) -> Experiment | None:
        stmt = select(ExperimentORM).where(ExperimentORM.id == exp_id, ExperimentORM.user_id == user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _from_orm(row) if row else None

    async def get_active(self, user_id: UUID) -> Experiment | None:
        stmt = select(ExperimentORM).where(ExperimentORM.user_id == user_id, ExperimentORM.status == "active")
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _from_orm(row) if row else None

    async def list_recent(self, user_id: UUID, limit: int) -> list[Experiment]:
        stmt = (
            select(ExperimentORM)
            .where(ExperimentORM.user_id == user_id)
            .order_by(ExperimentORM.start_date.desc(), ExperimentORM.created_at.desc())
            .limit(limit)
        )
        return [_from_orm(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def close(
        self, user_id: UUID, exp_id: UUID, status: str, result: dict | None, now: datetime
    ) -> Experiment | None:
        """Only an ACTIVE run can be closed; None means it was missing, not yours, or already closed."""
        stmt = (
            update(ExperimentORM)
            .where(ExperimentORM.id == exp_id, ExperimentORM.user_id == user_id, ExperimentORM.status == "active")
            .values(status=status, result=result, updated_at=now)
            .returning(ExperimentORM)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        await self._session.flush()
        return _from_orm(row) if row else None
