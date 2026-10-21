from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class InferenceOut(BaseModel):
    day: date
    kind: Literal["sleep"]
    time_to_bed: str   # HH:MM local, ready to send to POST /sleep unchanged
    time_woke: str
    duration_minutes: int
    confidence: Literal["low", "medium", "high"]
    basis: list[str]
    prompt: str
