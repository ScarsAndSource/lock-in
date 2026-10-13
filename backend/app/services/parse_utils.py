"""Tiny helpers shared by the two model-output parsers (voice check-in, screenshot screen time). Pure."""
from __future__ import annotations

import json
import re

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def load_json_object(raw: str) -> dict | None:
    """The first {...} object in a model reply (tolerates code fences and chatter around it), else None."""
    text = _FENCE.sub("", raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def as_int(value, lo: int, hi: int) -> int | None:
    """A whole number in [lo, hi] from an int, an integral float or a digit string; anything else is None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        value = int(value) if value.is_integer() else None
    elif isinstance(value, str):
        value = int(value) if value.strip().isdigit() else None
    if not isinstance(value, int):
        return None
    return value if lo <= value <= hi else None
