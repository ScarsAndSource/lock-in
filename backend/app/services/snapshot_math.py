"""Monthly life snapshot maths. PURE. Not a diagnosis: a low wellbeing score routes to support, never to coaching."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

METRICS = ("wellbeing", "sleep", "focus", "becoming", "automatic")
WINDOWS = (30, 60, 90)
TOLERANCE_DAYS = 10
DUE_EVERY_DAYS = 30
LOW_WELLBEING = 3
BIG_DROP = 3


@dataclass(frozen=True, slots=True)
class Snap:
    taken_on: date
    scores: dict[str, int]
    custom_label: str | None = None
    custom_value: float | None = None


def is_due(last_taken_on: date | None, today: date) -> bool:
    return last_taken_on is None or (today - last_taken_on).days >= DUE_EVERY_DAYS


def needs_support(wellbeing: int, previous: int | None) -> bool:
    return wellbeing <= LOW_WELLBEING or (previous is not None and previous - wellbeing >= BIG_DROP)


def deltas(snaps: list[Snap]) -> list[dict]:
    """Change since the first snapshot at ~30/60/90 days. A window with no snapshot near it is None, never a guess."""
    if len(snaps) < 2:
        return [{"days": w, "snapshot_on": None, "metrics": None, "custom": None} for w in WINDOWS]
    ordered = sorted(snaps, key=lambda s: s.taken_on)
    base = ordered[0]
    out: list[dict] = []
    for w in WINDOWS:
        target = base.taken_on + timedelta(days=w)
        near = [s for s in ordered[1:] if abs((s.taken_on - target).days) <= TOLERANCE_DAYS]
        if not near:
            out.append({"days": w, "snapshot_on": None, "metrics": None, "custom": None})
            continue
        snap = min(near, key=lambda s: abs((s.taken_on - target).days))
        custom = None
        if (
            base.custom_label and snap.custom_label and base.custom_value is not None
            and snap.custom_value is not None and base.custom_label.strip().lower() == snap.custom_label.strip().lower()
        ):
            custom = {"label": snap.custom_label, "from": base.custom_value, "to": snap.custom_value,
                      "change": round(snap.custom_value - base.custom_value, 2)}
        out.append({
            "days": w, "snapshot_on": snap.taken_on,
            "metrics": {m: snap.scores[m] - base.scores[m] for m in METRICS}, "custom": custom,
        })
    return out