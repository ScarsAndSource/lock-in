"""
Insights service stub for slice 8. Full insights slice is later.
RetroService calls: refresh(), list().
The "rate first" gate (rate_previous_first) is wired here so the retro feedback
loop works even before the full insights pipeline is built.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.domain import PatternInsight

_STALE_AFTER = timedelta(days=7)
_MAX_STALE_UNRATED = 3


@dataclass
class RefreshResult:
    created: list[PatternInsight] = field(default_factory=list)
    skipped_reason: str | None = None


class InsightRepository:
    """Minimal in-memory store for the stub — real repo in insights slice."""
    def __init__(self):
        self._insights: dict[UUID, PatternInsight] = {}

    async def list_unrated(self, user_id: UUID) -> list[PatternInsight]:
        return [i for i in self._insights.values() if i.user_id == user_id and i.user_feedback is None]

    async def list_all(self, user_id: UUID, limit: int) -> list[PatternInsight]:
        rows = [i for i in self._insights.values() if i.user_id == user_id]
        return sorted(rows, key=lambda i: i.generated_at, reverse=True)[:limit]

    async def set_feedback(self, user_id: UUID, insight_id: UUID, feedback: str) -> PatternInsight | None:
        i = self._insights.get(insight_id)
        if i is None or i.user_id != user_id:
            return None
        i.user_feedback = feedback
        return i


class InsightsService:
    """Stub: no pattern detection or LLM narration yet. Gate logic is real."""

    def __init__(self, repo: InsightRepository | None = None, *args, **kwargs):
        self._repo = repo or InsightRepository()

    async def list(self, user_id: UUID, limit: int = 20, unrated_only: bool = False) -> list[PatternInsight]:
        if unrated_only:
            return (await self._repo.list_unrated(user_id))[:limit]
        return await self._repo.list_all(user_id, limit)

    async def refresh(self, user_id: UUID) -> RefreshResult:
        now = datetime.now(timezone.utc)
        history = await self._repo.list_all(user_id, 100)
        stale_unrated = [i for i in history if i.user_feedback is None and now - i.generated_at > _STALE_AFTER]
        if len(stale_unrated) >= _MAX_STALE_UNRATED:
            return RefreshResult([], "rate_previous_first")
        # No pattern detection yet; real implementation in the insights slice.
        return RefreshResult([], "no_patterns")

    async def set_feedback(self, user_id: UUID, insight_id: UUID, feedback: str) -> PatternInsight | None:
        return await self._repo.set_feedback(user_id, insight_id, feedback)
