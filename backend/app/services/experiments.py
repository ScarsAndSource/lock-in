"""
N-of-1 experiment maths. Pure: no database, no clock, no LLM, and the same inputs always give the same verdict.

The question is "did this metric move when I made the change, by more than my own day-to-day noise?", answered with
a two-sided permutation test on the difference of means (exact for tiny samples, a seeded Monte Carlo otherwise).
Small n is the normal case here, so the verdict is deliberately conservative and honest:

  * fewer than MIN_BASELINE baseline days or MIN_TREATMENT test days  -> "not_enough_data", never a guess
  * "helped" / "hurt" need BOTH p <= ALPHA and a shift of at least the metric's min_effect
  * "not_followed" if the person says they barely kept to the change
  * caveats are attached when the baseline was already trending the same way, or the sample is small

Auto-filled (defaulted) sleep / screen / habit days never count: a guess must not become evidence.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from itertools import combinations
from math import comb, sqrt
from statistics import fmean, variance
from typing import Iterable

from app.domain_experiments import METRICS, MetricSpec, Point, Verdict
from app.services.chain_service import ChainDay

MIN_BASELINE = 5
MIN_TREATMENT = 4
ALPHA = 0.10            # small samples: this is "worth acting on", not "publishable"
EXACT_LIMIT = 20_000    # enumerate every relabelling up to this many, Monte Carlo above it
MC_ROUNDS = 5_000
SMALL_SAMPLE = 16


def metric_value(day: ChainDay, metric: str) -> float | None:
    """One number for one day, or None when that day has no real reading for the metric."""
    if metric == "sleep_hours":
        if day.sleep_defaulted or day.sleep_minutes is None:
            return None
        return day.sleep_minutes / 60.0
    if metric == "screen_minutes":
        if day.screen_time_defaulted or day.screen_minutes is None:
            return None
        return float(day.screen_minutes)
    if metric == "mood":
        return float(day.mood_valence) if day.mood_valence is not None else None
    if metric == "habit_ratio":
        if day.habits_defaulted or day.habit_ratio is None:
            return None
        return max(0.0, min(100.0, day.habit_ratio * 100.0))
    if metric == "task_rate":
        if day.tasks_due <= 0:
            return None
        return max(0.0, min(100.0, day.tasks_done / day.tasks_due * 100.0))
    raise ValueError(f"unknown metric {metric!r}")


def build_points(days: Iterable[ChainDay], metric: str, baseline_start: date, start: date, end: date) -> list[Point]:
    out: list[Point] = []
    for d in days:
        if baseline_start <= d.day < start:
            phase = "baseline"
        elif start <= d.day <= end:
            phase = "test"
        else:
            continue
        out.append(Point(day=d.day, value=metric_value(d, metric), phase=phase))
    out.sort(key=lambda p: p.day)
    return out


def values(points: Iterable[Point], phase: str) -> list[float]:
    return [p.value for p in points if p.phase == phase and p.value is not None]


def progress(start: date, treatment_days: int, today: date) -> tuple[str, int, int]:
    """(phase, day_number, days_left). waiting = starts later, complete = the test window is over."""
    end = start + timedelta(days=treatment_days - 1)
    if today < start:
        return "waiting", 0, treatment_days
    if today <= end:
        return "running", (today - start).days + 1, (end - today).days
    return "complete", treatment_days, 0


def fmt_value(spec: MetricSpec, v: float) -> str:
    if spec.key == "sleep_hours":
        return f"{v:.1f}h"
    if spec.key == "screen_minutes":
        return f"{round(v)} min"
    if spec.key == "mood":
        return f"{v:.1f}/5"
    return f"{round(v)}%"


def _perm_p(baseline: list[float], treatment: list[float], seed: int) -> float:
    pooled = baseline + treatment
    n, n_t = len(pooled), len(treatment)
    n_b = n - n_t
    total = sum(pooled)
    observed = abs(fmean(treatment) - fmean(baseline))
    eps = 1e-9

    if comb(n, n_t) <= EXACT_LIMIT:
        hits = count = 0
        for idx in combinations(range(n), n_t):
            s = sum(pooled[i] for i in idx)
            count += 1
            if abs(s / n_t - (total - s) / n_b) >= observed - eps:
                hits += 1
        return hits / count

    rng = random.Random(seed)
    hits = 0
    for _ in range(MC_ROUNDS):
        s = sum(pooled[i] for i in rng.sample(range(n), n_t))
        if abs(s / n_t - (total - s) / n_b) >= observed - eps:
            hits += 1
    return (hits + 1) / (MC_ROUNDS + 1)


def _pooled_sd(a: list[float], b: list[float]) -> float:
    dof = len(a) + len(b) - 2
    if dof <= 0:
        return 0.0
    return sqrt(((len(a) - 1) * variance(a) + (len(b) - 1) * variance(b)) / dof)


def _trend_caveat(baseline: list[float], delta: float) -> str | None:
    """The baseline was already drifting the same way as the shift -> part of the shift may just be that drift."""
    if len(baseline) < 6:
        return None
    h = len(baseline) // 2
    trend = fmean(baseline[-h:]) - fmean(baseline[:h])
    if trend * delta > 0 and abs(trend) >= 0.5 * abs(delta):
        return "Your baseline was already moving the same way, so part of this may be a trend rather than the change."
    return None


def evaluate(
    metric: str,
    direction: str,
    baseline: list[float],
    treatment: list[float],
    *,
    adherence: str | None = None,
    seed: int = 0,
) -> Verdict:
    spec = METRICS[metric]
    nb, nt = len(baseline), len(treatment)

    if adherence == "barely":
        return Verdict(
            "not_followed",
            "You barely kept to it, so these numbers say nothing about the change itself. Try again when it's doable.",
            nb, nt, None, None, None, None, None,
        )

    if nb < MIN_BASELINE or nt < MIN_TREATMENT:
        return Verdict(
            "not_enough_data",
            f"Not enough days to judge yet: {nb}/{MIN_BASELINE} baseline and {nt}/{MIN_TREATMENT} test days "
            f"have a real {spec.label.lower()} reading.",
            nb, nt, None, None, None, None, None,
        )

    bm, tm = fmean(baseline), fmean(treatment)
    delta = tm - bm
    p = _perm_p(baseline, treatment, seed)
    sd = _pooled_sd(baseline, treatment)
    effect = delta / sd if sd > 1e-9 else None

    improved = (delta > 0) == (direction == "higher")
    meaningful = abs(delta) >= spec.min_effect
    significant = p <= ALPHA
    if significant and meaningful:
        kind = "helped" if improved else "hurt"
    else:
        kind = "no_clear_effect"

    a, b = fmt_value(spec, tm), fmt_value(spec, bm)
    tail = f"(p={p:.2f}; {nt} test days vs {nb} baseline days)"
    label = spec.label.lower()
    if kind == "helped":
        sentence = f"It helped: {label} averaged {a} on test days vs {b} before {tail}."
    elif kind == "hurt":
        sentence = f"It went the wrong way: {label} averaged {a} on test days vs {b} before {tail}."
    elif significant:
        sentence = f"A measurable but tiny shift: {label} averaged {a} vs {b}, too small to matter {tail}."
    else:
        sentence = f"No clear effect: {label} averaged {a} vs {b}, a gap that shows up by chance this often {tail}."

    caveats: list[str] = []
    trend = _trend_caveat(baseline, delta)
    if trend:
        caveats.append(trend)
    if nb + nt < SMALL_SAMPLE:
        caveats.append("Small sample, so treat this as a hint, not a ruling.")
    if adherence == "partly":
        caveats.append("You said you only partly kept to it.")

    return Verdict(
        kind, sentence, nb, nt,
        round(bm, 3), round(tm, 3), round(delta, 3), round(p, 4),
        round(effect, 2) if effect is not None else None,
        tuple(caveats),
    )
