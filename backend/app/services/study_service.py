"""
Study service stub for slice 8. Full study slice is later.
RetroService._gather() calls study.summary() — this satisfies the interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(slots=True)
class StudySummary:
    total_actual: int = 0
    total_planned: int = 0
    follow_through_pct: float | None = None
    days_studied: int = 0


class StudyService:
    async def summary(self, user_id: UUID, start: date, end: date) -> StudySummary:
        return StudySummary()
