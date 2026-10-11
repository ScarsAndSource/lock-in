"""
Narration helpers: structured LLM output parsing and validation.
The trust pipeline: the model may only narrate what the deterministic layer already established.
Its JSON is rejected (caller falls back to deterministic text) if it:
- is malformed, empty, or over length
- uses banned tone (identity-level / prescriptive / shaming phrases)
- cites a day that isn't in the facts (or, when given, isn't in the allowed set)
- (check_numbers) contains a number that doesn't appear in the facts
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from app.services.llm import LLMClient

_BANNED_PHRASES = re.compile(
    r"\b(you should|you must|you need to|you always|you never|you're lazy|try harder|give up|"
    r"i hate to say|no excuses|pathetic|worthless|loser|you're weak|you failed again)\b",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass(slots=True)
class NarrationResult:
    observation: str  # chat stores its "answer" here
    next_step: str
    cited_days: list[str]


def tone_ok(*texts: str) -> bool:
    return not any(_BANNED_PHRASES.search(t.replace("\u2019", "'")) for t in texts)


def numbers_grounded(text: str, facts_json: str) -> bool:
    """Every number in `text` must appear as a standalone number somewhere in the facts."""
    fact_numbers = set(_NUMBER.findall(facts_json))
    return all(n in fact_numbers for n in _NUMBER.findall(text))


def _load_json(raw: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            return None


def _validate(
    raw: str,
    facts_json: str,
    *,
    require_dates: bool,
    max_observation: int,
    text_key: str = "observation",
    max_step: int = 200,
    check_numbers: bool = False,
    allowed_days: set[str] | None = None,
    extra_banned: re.Pattern[str] | None = None,
) -> NarrationResult | None:
    """Parse and validate the LLM JSON response. Returns None on any failure."""
    data = _load_json(raw)
    if not isinstance(data, dict):
        return None
    obs = data.get(text_key, "")
    step = data.get("next_step", "")
    cited = data.get("cited_days", [])
    if not isinstance(obs, str) or not isinstance(step, str) or not isinstance(cited, list):
        return None
    if not obs.strip() or not step.strip():
        return None
    if len(obs) > max_observation or len(step) > max_step:
        return None
    if not tone_ok(obs, step):
        return None
    if extra_banned is not None and extra_banned.search(f"{obs} {step}".replace("\u2019", "'")):
        return None
    if require_dates and not cited:
        return None
    if check_numbers and not numbers_grounded(obs, facts_json):
        return None
    for d in cited:
        if not isinstance(d, str):
            return None
        try:
            date.fromisoformat(d)
        except ValueError:
            return None
        if d not in facts_json:
            return None
        if allowed_days is not None and d not in allowed_days:
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
    text_key: str = "observation",
    max_step: int = 200,
    check_numbers: bool = False,
    allowed_days: set[str] | None = None,
    extra_banned: re.Pattern[str] | None = None,
) -> tuple[NarrationResult | None, str]:
    """(result, raw_response). LLMError propagates (callers fall back). None result = failed validation."""
    last_raw = ""
    for _ in range(retries):
        raw = await llm.complete(messages, max_tokens=max_tokens, temperature=temperature)
        last_raw = raw
        result = _validate(
            raw,
            facts_json,
            require_dates=require_dates,
            max_observation=max_observation,
            text_key=text_key,
            max_step=max_step,
            check_numbers=check_numbers,
            allowed_days=allowed_days,
            extra_banned=extra_banned,
        )
        if result is not None:
            return result, raw
    return None, last_raw


def sanitize_user_text(text: str, max_len: int, *, single_line: bool = False) -> str:
    """Strip control chars and angle brackets (no tag breakout), optionally one line, truncate."""
    out = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    out = out.replace("<", "").replace(">", "")
    if single_line:
        out = re.sub(r"\s+", " ", out).strip()
    return out[:max_len]


def fallback_next_step(pattern_key: str) -> str:
    """Returns a concrete one-liner for the most common slip patterns."""
    _STEPS = {
        "sleep->habits": "Tonight: phone charging outside the bedroom before midnight.",
        "screen_time->habits": "Cap screen time after 8 pm tomorrow.",
        "screen_time->sleep": "Set a hard app-limit for 9 pm tonight.",
        "sleep->screen_time": "After a bad night, keep screens off until you've eaten breakfast.",
        "urges->habits": "Log the urge the moment it happens — the habit slip comes later.",
        "sleep->study": "Tonight: lights out on time so tomorrow's study block survives.",
        "screen_time->study": "Phone out of the room for the first hour of tomorrow's study block.",
        "sleep->urges": "After a short night, plan your evening before the urge shows up.",
        "screen_time->urges": "Heavy screen day: set a hard stop time tonight and decide what you'll do instead.",
    }
    return _STEPS.get(pattern_key, "Log every day next week, even rough numbers.")
