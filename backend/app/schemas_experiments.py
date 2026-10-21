from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MetricKey = Literal["sleep_hours", "screen_minutes", "mood", "habit_ratio", "task_rate"]


class ExperimentStartIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=120)
    change: str = Field(min_length=1, max_length=200)
    metric: MetricKey
    direction: Literal["higher", "lower"] | None = None
    baseline_days: int = Field(14, ge=7, le=30)
    treatment_days: int = Field(7, ge=5, le=21)
    start: Literal["today", "tomorrow"] = "today"


class ExperimentFinishIn(BaseModel):
    adherence: Literal["mostly", "partly", "barely"]


class MetricOut(BaseModel):
    key: MetricKey
    label: str
    unit: str
    better: Literal["higher", "lower"]
    usable_days: int


class PointOut(BaseModel):
    day: date
    value: float | None
    phase: Literal["baseline", "test"]


class VerdictOut(BaseModel):
    kind: Literal["helped", "hurt", "no_clear_effect", "not_enough_data", "not_followed"]
    sentence: str
    n_baseline: int
    n_treatment: int
    baseline_mean: float | None = None
    treatment_mean: float | None = None
    delta: float | None = None
    p_value: float | None = None
    effect_size: float | None = None
    caveats: list[str] = []


class ExperimentOut(BaseModel):
    id: str
    title: str
    change: str
    metric: MetricKey
    metric_label: str
    unit: str
    direction: Literal["higher", "lower"]
    status: Literal["active", "done", "abandoned"]
    start_date: date
    end_date: date
    baseline_days: int
    treatment_days: int
    phase: Literal["waiting", "running", "complete"]
    day_number: int
    days_left: int
    provisional: bool
    verdict: VerdictOut | None = None
    points: list[PointOut] = []
