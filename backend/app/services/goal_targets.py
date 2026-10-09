"""Per-domain goal target shapes. One place defines what a goal MEANS in each domain."""
from __future__ import annotations

import json
from datetime import time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from app.exceptions import ValidationError


class _Target(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HabitGoalTarget(_Target):
    habit_id: UUID
    min_consistency_pct: float = Field(80, ge=1, le=100)
    window_days: int = Field(30, ge=7, le=90)


class ScreenGoalTarget(_Target):
    max_minutes_per_day: int = Field(ge=1, le=1440)
    min_days_within_pct: float = Field(80, ge=1, le=100)
    window_days: int = Field(14, ge=7, le=90)


class SleepGoalTarget(_Target):
    min_minutes_per_night: int = Field(ge=180, le=720)
    min_nights_pct: float = Field(80, ge=1, le=100)
    window_days: int = Field(14, ge=7, le=90)
    bedtime: time | None = None   # optional: seeds the check-in's sleep default
    wake: time | None = None


class StudyGoalTarget(_Target):
    weekly_minutes: int = Field(ge=30, le=6000)


class UrgeGoalTarget(_Target):
    min_relapse_free_days_pct: float = Field(90, ge=1, le=100)
    window_days: int = Field(30, ge=7, le=90)


TARGET_MODELS: dict[str, type[_Target]] = {
    "habit": HabitGoalTarget, "screen_time": ScreenGoalTarget, "sleep": SleepGoalTarget,
    "study": StudyGoalTarget, "urge": UrgeGoalTarget,
}


def normalize_target(domain: str, raw: dict) -> dict:
    """Validated + defaults filled + JSON-safe (UUID/time -> str). Raises app ValidationError."""
    model = TARGET_MODELS.get(domain)
    if model is None:
        raise ValidationError(f"Unknown goal domain {domain!r}.")
    try:
        parsed = model.model_validate(raw)
    except PydanticValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise ValidationError(f"Invalid {domain} goal target -- {problems}") from exc
    return json.loads(parsed.model_dump_json())
