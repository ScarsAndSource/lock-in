from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import PatternInsight
from app.models import PatternInsightORM

_UNRATED_CAP = 500


def _to_domain(row: PatternInsightORM) -> PatternInsight:
    return PatternInsight(
        id=row.id, user_id=row.user_id, generated_at=row.generated_at, generated_on=row.generated_on,
        pattern_key=row.pattern_key, insight_text=row.insight_text, next_step=row.next_step,
        source_domains=list(row.source_domains or []), evidence_refs=row.evidence_refs or {},
        narrated=row.narrated, voice_version=row.voice_version, model=row.model,
        user_feedback=row.user_feedback,
    )


class SqlAlchemyInsightRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, insight: PatternInsight) -> PatternInsight | None:
        """None if (user, pattern, day) already exists -- a double refresh can't duplicate."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            pg_insert(PatternInsightORM)
            .values(
                id=insight.id, user_id=insight.user_id, generated_at=insight.generated_at,
                generated_on=insight.generated_on, pattern_key=insight.pattern_key,
                insight_text=insight.insight_text, next_step=insight.next_step,
                source_domains=insight.source_domains, evidence_refs=insight.evidence_refs,
                narrated=insight.narrated, voice_version=insight.voice_version, model=insight.model,
                user_feedback=None, created_at=now, updated_at=now,
            )
            .on_conflict_do_nothing(constraint="pattern_insights_user_key_day")
            .returning(PatternInsightORM.id)
        )
        if result.scalar_one_or_none() is None:
            return None
        return insight

    async def list_unrated(self, user_id: UUID) -> list[PatternInsight]:
        stmt = (
            select(PatternInsightORM)
            .where(PatternInsightORM.user_id == user_id, PatternInsightORM.user_feedback.is_(None))
            .order_by(PatternInsightORM.generated_at.desc()).limit(_UNRATED_CAP)
        )
        return [_to_domain(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def list_all(self, user_id: UUID, limit: int) -> list[PatternInsight]:
        stmt = (
            select(PatternInsightORM).where(PatternInsightORM.user_id == user_id)
            .order_by(PatternInsightORM.generated_at.desc()).limit(limit)
        )
        return [_to_domain(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def set_feedback(self, user_id: UUID, insight_id: UUID, feedback: str) -> PatternInsight | None:
        stmt = select(PatternInsightORM).where(
            PatternInsightORM.id == insight_id, PatternInsightORM.user_id == user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        row.user_feedback = feedback
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return _to_domain(row)
