from __future__ import annotations

import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyCheckinORM, ProfileORM
from app.models_seasons import HabitGraduationORM, LifeSnapshotORM, RecallReviewORM, RecallSetORM, SeasonORM


class SqlAlchemyJourneyRepository:
    """Persistence for seasons, exam radar, life snapshots and the graduation shelf. JourneyService owns every rule."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, row, now: datetime) -> None:
        row.updated_at = now
        await self._session.flush()

    # ---- account facts
    async def profile_created_on(self, user_id: UUID) -> date | None:
        stmt = select(ProfileORM.created_at).where(ProfileORM.user_id == user_id)
        created = (await self._session.execute(stmt)).scalar_one_or_none()
        return created.date() if created is not None else None

    async def count_confirmed(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(DailyCheckinORM).where(
            DailyCheckinORM.user_id == user_id, DailyCheckinORM.confirmed_at.is_not(None),
        )
        return int((await self._session.execute(stmt)).scalar_one())

    # ---- seasons
    async def get_open_season(self, user_id: UUID) -> SeasonORM | None:
        stmt = select(SeasonORM).where(SeasonORM.user_id == user_id, SeasonORM.closed_on.is_(None))
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_seasons(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(SeasonORM).where(SeasonORM.user_id == user_id)
        return int((await self._session.execute(stmt)).scalar_one())

    async def create_season(
        self, user_id: UUID, name: str, start: date, slots: int, focus: list[UUID], now: datetime,
    ) -> SeasonORM:
        row = SeasonORM(
            id=uuid.uuid4(), user_id=user_id, name=name, start_date=start, slots=slots,
            focus_habit_ids=list(focus), closed_on=None, created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def close_season(self, row: SeasonORM, today: date, now: datetime) -> None:
        row.closed_on = today
        await self.save(row, now)

    async def set_focus(self, row: SeasonORM, ids: list[UUID], now: datetime) -> None:
        row.focus_habit_ids = list(ids)
        await self.save(row, now)

    # ---- exam radar
    async def add_set(
        self, user_id: UUID, label: str, topics: bytes, exam: date | None, now: datetime,
    ) -> RecallSetORM:
        row = RecallSetORM(
            id=uuid.uuid4(), user_id=user_id, label=label, topics_encrypted=topics, exam_date=exam,
            archived_at=None, created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_sets(self, user_id: UUID) -> list[RecallSetORM]:
        stmt = select(RecallSetORM).where(
            RecallSetORM.user_id == user_id, RecallSetORM.archived_at.is_(None),
        ).order_by(RecallSetORM.created_at)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_set(self, user_id: UUID, set_id: UUID) -> RecallSetORM | None:
        stmt = select(RecallSetORM).where(RecallSetORM.user_id == user_id, RecallSetORM.id == set_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def archive_set(self, row: RecallSetORM, now: datetime) -> None:
        row.archived_at = now
        await self.save(row, now)

    async def add_review(self, user_id: UUID, set_id: UUID, step: int, due: date, now: datetime) -> RecallReviewORM:
        row = RecallReviewORM(
            id=uuid.uuid4(), user_id=user_id, set_id=set_id, step=step, due_date=due, done_at=None,
            created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def pending_reviews(self, user_id: UUID) -> list[tuple[RecallReviewORM, RecallSetORM]]:
        stmt = (
            select(RecallReviewORM, RecallSetORM)
            .join(RecallSetORM, RecallSetORM.id == RecallReviewORM.set_id)
            .where(
                RecallReviewORM.user_id == user_id, RecallReviewORM.done_at.is_(None),
                RecallSetORM.archived_at.is_(None),
            )
            .order_by(RecallReviewORM.due_date)
        )
        return [(r, s) for r, s in (await self._session.execute(stmt)).all()]

    async def get_review(self, user_id: UUID, review_id: UUID) -> RecallReviewORM | None:
        stmt = select(RecallReviewORM).where(RecallReviewORM.user_id == user_id, RecallReviewORM.id == review_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def delete_review(self, row: RecallReviewORM) -> None:
        await self._session.delete(row)
        await self._session.flush()

    async def done_counts(self, user_id: UUID) -> dict[UUID, int]:
        stmt = (
            select(RecallReviewORM.set_id, func.count())
            .where(RecallReviewORM.user_id == user_id, RecallReviewORM.done_at.is_not(None))
            .group_by(RecallReviewORM.set_id)
        )
        return {sid: int(n) for sid, n in (await self._session.execute(stmt)).all()}

    # ---- life snapshots
    async def list_snapshots(self, user_id: UUID) -> list[LifeSnapshotORM]:
        stmt = select(LifeSnapshotORM).where(LifeSnapshotORM.user_id == user_id).order_by(LifeSnapshotORM.taken_on).limit(60)
        return list((await self._session.execute(stmt)).scalars().all())

    async def add_snapshot(
        self, user_id: UUID, taken_on: date, scores: dict[str, int], label: bytes | None, value: float | None,
        now: datetime,
    ) -> LifeSnapshotORM:
        row = LifeSnapshotORM(
            id=uuid.uuid4(), user_id=user_id, taken_on=taken_on, custom_label_encrypted=label, custom_value=value,
            created_at=now, updated_at=now, **scores,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    # ---- graduation shelf
    async def add_graduation(
        self, user_id: UUID, habit_id: UUID, on: date, check30: date, check90: date, now: datetime,
    ) -> HabitGraduationORM:
        row = HabitGraduationORM(
            id=uuid.uuid4(), user_id=user_id, habit_id=habit_id, graduated_on=on, check30_on=check30,
            check90_on=check90, check30_result=None, check90_result=None, revived_on=None,
            created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_graduations(self, user_id: UUID) -> list[HabitGraduationORM]:
        stmt = select(HabitGraduationORM).where(HabitGraduationORM.user_id == user_id).order_by(
            HabitGraduationORM.graduated_on.desc(),
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_graduation(self, user_id: UUID, grad_id: UUID) -> HabitGraduationORM | None:
        stmt = select(HabitGraduationORM).where(HabitGraduationORM.user_id == user_id, HabitGraduationORM.id == grad_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()
    