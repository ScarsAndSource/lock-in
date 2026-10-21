"""
N-of-1 experiments: plain data only (no I/O). The maths lives in services/experiments.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

Metric = Literal["sleep_hours", "screen_minutes", "mood", "habit_ratio", "task_rate"]
Direction = Literal["higher", "lower"]
Adherence = Literal["mostly", "partly", "barely"]


@dataclass(frozen=True, slots=True)
class MetricSpec:
    key: str
    label: str
    unit: str
    better: str          # the direction most people mean by "better" for this metric
    min_effect: float    # smallest average shift that is worth caring about, in the metric's own units
    decimals: int


# Ratios are expressed as percentages (0-100) so one threshold style fits all of them.
METRICS: dict[str, MetricSpec] = {
    "sleep_hours": MetricSpec("sleep_hours", "Sleep", "h", "higher", 0.5, 1),
    "screen_minutes": MetricSpec("screen_minutes", "Screen time", "min", "lower", 20.0, 0),
    "mood": MetricSpec("mood", "Mood", "/5", "higher", 0.5, 1),
    "habit_ratio": MetricSpec("habit_ratio", "Habit completion", "%", "higher", 10.0, 0),
    "task_rate": MetricSpec("task_rate", "Tasks done", "%", "higher", 10.0, 0),
}


@dataclass(slots=True)
class Experiment:
    id: UUID
    user_id: UUID
    title: str
    change: str
    metric: str
    direction: str
    baseline_days: int
    treatment_days: int
    start_date: date
    status: str                      # active | done | abandoned
    result: dict | None
    created_at: datetime
    updated_at: datetime

    @property
    def baseline_start(self) -> date:
        return self.start_date - timedelta(days=self.baseline_days)

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=self.treatment_days - 1)


@dataclass(frozen=True, slots=True)
class Point:
    day: date
    value: float | None
    phase: str                       # baseline | test


@dataclass(frozen=True, slots=True)
class Verdict:
    kind: str                        # helped | hurt | no_clear_effect | not_enough_data | not_followed
    sentence: str
    n_baseline: int
    n_treatment: int
    baseline_mean: float | None
    treatment_mean: float | None
    delta: float | None
    p_value: float | None
    effect_size: float | None
    caveats: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "sentence": self.sentence,
            "n_baseline": self.n_baseline, "n_treatment": self.n_treatment,
            "baseline_mean": self.baseline_mean, "treatment_mean": self.treatment_mean,
            "delta": self.delta, "p_value": self.p_value, "effect_size": self.effect_size,
            "caveats": list(self.caveats),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Verdict":
        return cls(
            kind=str(d.get("kind", "not_enough_data")),
            sentence=str(d.get("sentence", "")),
            n_baseline=int(d.get("n_baseline", 0)),
            n_treatment=int(d.get("n_treatment", 0)),
            baseline_mean=d.get("baseline_mean"),
            treatment_mean=d.get("treatment_mean"),
            delta=d.get("delta"),
            p_value=d.get("p_value"),
            effect_size=d.get("effect_size"),
            caveats=tuple(d.get("caveats", []) or []),
        )


@dataclass(slots=True)
class ExperimentView:
    experiment: Experiment
    phase: str                       # waiting | running | complete
    day_number: int
    days_left: int
    points: list[Point] = field(default_factory=list)
    verdict: Verdict | None = None
    provisional: bool = False
