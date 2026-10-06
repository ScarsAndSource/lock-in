"""
Narration helpers: structured LLM output parsing and validation.
Stub for slice 8. The full narration pipeline (tone gate, jailbreak checks, etc.) is a later slice.

narrate_structured() calls the LLM with the given messages, parses JSON, and validates the shape.
Falls back to None (caller uses deterministic text) if the LLM errors or validation fails twice.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from app.services.llm import LLMClient, LLMError

# ---- tone gate (minimal): reject observations that sound prescriptive or invented.
_BANNED_PHRASES = re.compile(
    r"\b(you should|you must|you need to|you always|you never|you're lazy|try harder|give up)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class NarrationResult:
    observation: str
    next_step: str
    cited_days: list[str]


def _validate(raw: str, facts_json: str, *, require_dates: bool, max_observation: int) -> NarrationResult | None:
    """Parse and validate the LLM JSON response. Returns None on any failure."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract the first JSON object from the string
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return None

    obs = data.get("observation", "")
    step = data.get("next_step", "")
    cited = data.get("cited_days", [])

    if not isinstance(obs, str) or not isinstance(step, str) or not isinstance(cited, list):
        return None
    if not obs.strip() or not step.strip():
        return None
    if len(obs) > max_observation or len(step) > 200:
        return None
    if _BANNED_PHRASES.search(obs) or _BANNED_PHRASES.search(step):
        return None
    if require_dates and not cited:
        return None

    # All cited dates must appear in the facts JSON
    for d in cited:
        if not isinstance(d, str):
            return None
        try:
            date.fromisoformat(d)
        except ValueError:
            return None
        if d not in facts_json:
            return None

    return NarrationResult(observation=obs.strip(), next_step=step.strip(), cited_days=cited)


async def narrate_structured(
    llm: LLMClient,
    messages: list[dict],
    *,
    facts_json: str,
    require_dates: bool,
    max_observation: int = 450,
    max_tokens: int = 512,
    temperature: float = 0.3,
    retries: int = 2,
) -> tuple[NarrationResult, str]:
    """(result, raw_response). Raises LLMError if the LLM fails. Returns None result if validation fails after retries."""
    last_raw = ""
    for _ in range(retries):
        raw = await llm.complete(messages, max_tokens=max_tokens, temperature=temperature)
        last_raw = raw
        result = _validate(raw, facts_json, require_dates=require_dates, max_observation=max_observation)
        if result is not None:
            return result, raw
    return None, last_raw  # type: ignore[return-value]


def sanitize_user_text(text: str, max_len: int, *, single_line: bool = False) -> str:
    """Strip control chars, optionally collapse to one line, and truncate."""
    out = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
    if single_line:
        out = re.sub(r'\s+', ' ', out).strip()
    return out[:max_len]


def fallback_next_step(pattern_key: str) -> str:
    """Returns a concrete one-liner for the most common slip patterns."""
    _STEPS = {
        "sleep->habits": "Tonight: phone charging outside the bedroom before midnight.",
        "screen_time->habits": "Cap screen time after 8 pm tomorrow.",
        "screen_time->sleep": "Set a hard app-limit for 9 pm tonight.",
        "sleep->screen_time": "After a bad night, keep screens off until you've eaten breakfast.",
        "urges->habits": "Log the urge the moment it happens — the habit slip comes later.",
    }
    return _STEPS.get(pattern_key, "Log every day next week, even rough numbers.")
