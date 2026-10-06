"""
Urges service stub for slice 8. Full urges/relapse slice is later.
RetroService._gather() calls urges.summary() — this satisfies the interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(slots=True)
class UrgeSummary:
    total: int = 0
    resisted: int = 0
    relapsed: int = 0
    resist_rate_pct: float | None = None
    relapse_free_days_pct: float | None = None


class UrgesService:
    async def summary(
        self, user_id: UUID, end_date: date, window_days: int
    ) -> tuple[date, UrgeSummary, float | None]:
        return end_date, UrgeSummary(), None
