"""
Insights: deterministic patterns (pattern_service) -> stored insights -> user rates them.

refresh() order of business:
  1. soft gate: 3+ insights older than 7 days still unrated -> 'rate_previous_first'
  2. find proven patterns over the last 30 days (math, with evidence dates)
  3. skip any pattern already issued in the last 7 days
  4. store up to 3 new ones (narrated=False; Groq narration plugs in at slice 7)
The model never invents a pattern: it can only narrate what step 2 found.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import PatternInsight
from app.exceptions import NotFoundError, ValidationError
from app.services.narration import fallback_next_step
from app.services.stats_service import StatsService
from app.voice_config import VOICE_VERSION

_STALE_AFTER = timedelta(days=7)
_MAX_STALE_UNRATED = 3
_REGEN_AFTER_DAYS = 7
_MAX_NEW_PER_REFRESH = 3
_PATTERN_WINDOW_DAYS = 30
VALID_FEEDBACK = ("accurate", "not_quite", "unsure")


@dataclass
class RefreshResult:
    created: list[PatternInsight] = field(default_factory=list)
    skipped_reason: str | None = None


class InsightStore(Protocol):
    async def add(self, insight: PatternInsight) -> PatternInsight | None: ...
    async def list_unrated(self, user_id: UUID) -> list[PatternInsight]: ...
    async def list_all(self, user_id: UUID, limit: int) -> list[PatternInsight]: ...
    async def set_feedback(self, user_id: UUID, insight_id: UUID, feedback: str) -> PatternInsight | None: ...


class InsightRepository:
    """In-memory store -- TESTS ONLY. Production wiring (deps.py) passes SqlAlchemyInsightRepository."""

    def __init__(self):
        self._insights: dict[UUID, PatternInsight] = {}

    async def add(self, insight: PatternInsight) -> PatternInsight | None:
        for i in self._insights.values():
            if (i.user_id, i.pattern_key, i.generated_on) == (insight.user_id, insight.pattern_key, insight.generated_on):
                return None
        self._insights[insight.id] = insight
        return insight

    async def list_unrated(self, user_id: UUID) -> list[PatternInsight]:
        rows = [i for i in self._insights.values() if i.user_id == user_id and i.user_feedback is None]
        return sorted(rows, key=lambda i: i.generated_at, reverse=True)

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
    def __init__(self, repo: InsightStore | None = None, stats: StatsService | None = None, clock: Clock = utc_now):
        self._repo = repo or InsightRepository()
        self._stats = stats
        self._clock = clock

    async def list(self, user_id: UUID, limit: int = 20, unrated_only: bool = False) -> list[PatternInsight]:
        if unrated_only:
            return (await self._repo.list_unrated(user_id))[:limit]
        return await self._repo.list_all(user_id, limit)

    async def refresh(self, user_id: UUID) -> RefreshResult:
        now = self._clock()
        history = await self._repo.list_all(user_id, 100)
        stale_unrated = [i for i in history if i.user_feedback is None and now - i.generated_at > _STALE_AFTER]
        if len(stale_unrated) >= _MAX_STALE_UNRATED:
            return RefreshResult([], "rate_previous_first")
        if self._stats is None:
            return RefreshResult([], "no_patterns")

        today, patterns = await self._stats.patterns(user_id, None, _PATTERN_WINDOW_DAYS)
        if not patterns:
            return RefreshResult([], "no_patterns")

        recent_keys = {i.pattern_key for i in history if (today - i.generated_on).days < _REGEN_AFTER_DAYS}
        created: list[PatternInsight] = []
        for p in patterns:
            if len(created) >= _MAX_NEW_PER_REFRESH:
                break
            if p.key in recent_keys:
                continue
            saved = await self._repo.add(PatternInsight(
                id=uuid4(), user_id=user_id, generated_at=now, generated_on=today, pattern_key=p.key,
                insight_text=p.statement[:800], next_step=fallback_next_step(p.key),
                source_domains=p.key.split("->"),
                evidence_refs={
                    "dates": [d.isoformat() for d in p.evidence_dates], "trigger_days": p.trigger_days,
                    "hits": p.hits, "rate_after_trigger": p.rate_after_trigger,
                    "baseline_rate": p.baseline_rate, "lag_days": p.lag_days,
                },
                narrated=False, voice_version=VOICE_VERSION, model=None,
            ))
            if saved is not None:
                created.append(saved)
        return RefreshResult(created, None if created else "no_new_patterns")

    async def set_feedback(self, user_id: UUID, insight_id: UUID, feedback: str) -> PatternInsight:
        if feedback not in VALID_FEEDBACK:
            raise ValidationError(f"feedback must be one of {VALID_FEEDBACK}.")
        updated = await self._repo.set_feedback(user_id, insight_id, feedback)
        if updated is None:
            raise NotFoundError("No insight found for this user.")
        return updated
