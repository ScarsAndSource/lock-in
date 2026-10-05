"""
Deterministic cross-domain pattern finder -- the falsifiable half of the
"insight" pitch. Math finds the pattern and cites the exact dates; the LLM
(later slice) only NARRATES these, so it can't invent a correlation. Each
pattern carries evidence_dates (SPEC section 8).

A pattern is reported only if: >= 3 trigger days, >= 3 comparison days, the
outcome happened >= 50% of the time after the trigger, and at least 30
percentage points more often than without it. Days where the trigger or
outcome was an auto-filled guess are ignored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.services.chain_service import BAD, NONE, ChainDay

# (trigger domain, outcome domain, lag in days, trigger label, outcome label)
_PAIRS = (
    ("sleep", "habits", 0, "Bad sleep", "habits slipped the same day"),
    ("screen_time", "habits", 1, "A heavy screen day", "habits slipped the next day"),
    ("screen_time", "sleep", 1, "A heavy screen day", "bad sleep that night"),
    ("sleep", "screen_time", 0, "Bad sleep", "heavy screen time the same day"),
)


@dataclass(slots=True)
class Pattern:
    key: str
    trigger: str
    outcome: str
    lag_days: int
    trigger_days: int
    hits: int
    rate_after_trigger: float
    baseline_days: int
    baseline_rate: float
    evidence_dates: list[date]
    statement: str


def _unusable(day: ChainDay, domain: str) -> bool:
    if getattr(day, domain) == NONE:
        return True
    return bool(getattr(day, f"{domain}_defaulted", False))


def find_patterns(
    days: list[ChainDay], *, min_trigger_days: int = 3, min_baseline_days: int = 3,
    min_rate: float = 0.5, min_gap: float = 0.3,
) -> list[Pattern]:
    by_day = {d.day: d for d in days}
    found: list[Pattern] = []

    for trigger, outcome, lag, t_label, o_label in _PAIRS:
        triggered: list[tuple[date, bool]] = []
        baseline: list[tuple[date, bool]] = []
        for d in days:
            o = by_day.get(d.day + timedelta(days=lag))
            if o is None or _unusable(d, trigger) or _unusable(o, outcome):
                continue
            bucket = triggered if getattr(d, trigger) == BAD else baseline
            bucket.append((d.day, getattr(o, outcome) == BAD))

        if len(triggered) < min_trigger_days or len(baseline) < min_baseline_days:
            continue
        evidence = [dt for dt, bad in triggered if bad]
        rate = len(evidence) / len(triggered)
        base_rate = sum(1 for _, bad in baseline if bad) / len(baseline)
        if rate < min_rate or rate - base_rate < min_gap:
            continue

        found.append(Pattern(
            key=f"{trigger}->{outcome}", trigger=t_label, outcome=o_label, lag_days=lag,
            trigger_days=len(triggered), hits=len(evidence), rate_after_trigger=round(rate, 2),
            baseline_days=len(baseline), baseline_rate=round(base_rate, 2), evidence_dates=evidence,
            statement=(
                f"{t_label} → {o_label}: {len(evidence)}/{len(triggered)} times, "
                f"vs {round(base_rate * 100)}% of other days."
            ),
        ))

    found.sort(key=lambda p: p.rate_after_trigger - p.baseline_rate, reverse=True)
    return found
