"""
Rough-week mode for the weekly retro.
Detection is DETERMINISTIC (never the model's call): a week is "rough" when at least two independent
signals fire AND there is enough logged data to say so.
A thin week (under 3 days with data) is an under-logged week, not a rough one, and is never labelled rough.
The tone shift is SCOPE, not softness: one thing that held, at most one chain, one minimum next step,
no consolation and no cheerleading. The voice rules (direct, no cushioning, no identity language) still apply in full.
The user can override the read either way (source="user") after the fact.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from app.services.llm import LLMClient, LLMError
from app.services.narration import NarrationResult, fallback_next_step, narrate_structured
from app.services.retro_engine import _CAUSE_WORDS, _SLIP_WORDS, fallback_narrative  # noqa: PLC2701
from app.voice_config import retro_system_prompt

MIN_KNOWN_DAYS = 3
SLIP_DAYS_THRESHOLD = 4
LOW_HABIT_PCT = 40.0
RELAPSES_THRESHOLD = 3
LOW_STUDY_FOLLOW_THROUGH = 40.0
MIN_PLANNED_STUDY_MINUTES = 120
SIGNALS_NEEDED = 2
ROUGH_MAX_OBSERVATION = 300
ROUGH_MAX_STEP = 140
NORMAL_MAX_OBSERVATION = 450
NORMAL_MAX_STEP = 200

_DOMAINS = ("habits", "sleep", "screen_time", "study", "urges")
_SLIP_DOMAINS = ("habits", "study", "urges")

# Consolation / cheerleading / week-labelling the rough read must never contain.
ROUGH_BANNED = re.compile(
    r"\b(you've got this|you got this|it's okay|it's ok|don't worry|proud of you|keep going|keep it up|"
    r"better days|silver lining|everything will|come back stronger|bad week|terrible week|awful week|"
    r"failed|failure|slump)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class WeekMode:
    mode: Literal["normal", "rough"]
    reasons: list[str] = field(default_factory=list)
    source: Literal["auto", "user"] = "auto"

    def as_dict(self) -> dict:
        return {"mode": self.mode, "reasons": list(self.reasons), "source": self.source}


def signals(summary: dict) -> list[str]:
    """Which rough-week signals fired for this retro summary (empty on thin data)."""
    known = [d for d in summary.get("days", []) if any(d.get(k, "none") != "none" for k in _DOMAINS)]
    if len(known) < MIN_KNOWN_DAYS:
        return []
    fired: list[str] = []
    slip_days = [d for d in known if any(d.get(k) == "bad" for k in _SLIP_DOMAINS)]
    if len(slip_days) >= SLIP_DAYS_THRESHOLD:
        fired.append("many_slip_days")
    pct = summary.get("habit_overall_pct")
    if pct is not None and pct < LOW_HABIT_PCT:
        fired.append("low_habit_consistency")
    if (summary.get("urges") or {}).get("relapsed", 0) >= RELAPSES_THRESHOLD:
        fired.append("repeated_relapses")
    study = summary.get("study") or {}
    ft = study.get("follow_through_pct")
    if (
        ft is not None
        and ft < LOW_STUDY_FOLLOW_THROUGH
        and study.get("planned_minutes", 0) >= MIN_PLANNED_STUDY_MINUTES
    ):
        fired.append("study_far_below_plan")
    return fired


def resolve_week_mode(summary: dict, requested: str = "auto") -> WeekMode:
    fired = signals(summary)
    if requested in ("rough", "normal"):
        return WeekMode(requested, fired, "user")
    return WeekMode("rough" if len(fired) >= SIGNALS_NEEDED else "normal", fired, "auto")


def fallback_rough(summary: dict) -> tuple[str, str, list[str]]:
    """Deterministic rough-week text from structure alone: what held, one chain, one minimum step."""
    parts: list[str] = []
    cited: list[str] = []
    step = "Monday: do the smallest version of one habit and log it."
    clean = summary.get("clean_days") or []
    if clean:
        parts.append(f"{clean[0]['weekday']} held: nothing broke.")
        cited.append(clean[0]["date"])
    else:
        resisted = (summary.get("urges") or {}).get("resisted", 0)
        if resisted:
            parts.append(f"{resisted} urge{'s' if resisted != 1 else ''} resisted.")
    chains = summary.get("chains") or []
    if chains:
        c = chains[0]
        slips = " and ".join(_SLIP_WORDS[s] for s in c["slips"])
        causes = " and ".join(f"{_CAUSE_WORDS[u['signal']]} ({u['weekday']})" for u in c["caused_by"])
        parts.append(f"{c['weekday']}: {slips}, after {causes}.")
        cited += [c["slip_date"], *[u["date"] for u in c["caused_by"]]]
        step = fallback_next_step(f"{c['caused_by'][0]['signal']}->{c['slips'][0]}")
    elif summary.get("unexplained_slips"):
        parts.append("The slips this week have no visible cause in your logs.")
        cited += [u["date"] for u in summary["unexplained_slips"][:2]]
    if not parts:
        parts.append("Most of this week has no logged data to read.")
        step = "Log tomorrow, even rough numbers."
    return " ".join(parts)[:ROUGH_MAX_OBSERVATION], step[:ROUGH_MAX_STEP], list(dict.fromkeys(cited))


def fallback_for_mode(summary: dict) -> tuple[str, str, list[str]]:
    if (summary.get("week_mode") or {}).get("mode") == "rough":
        return fallback_rough(summary)
    return fallback_narrative(summary)


async def narrate_retro(llm: LLMClient, summary: dict) -> NarrationResult | None:
    """Mode-aware, validated retro narration. None => caller uses fallback_for_mode()."""
    rough = (summary.get("week_mode") or {}).get("mode") == "rough"
    facts_json = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    require_dates = bool(summary["chains"] or summary["unexplained_slips"] or summary["clean_days"])
    messages = [
        {"role": "system", "content": retro_system_prompt("rough" if rough else "normal")},
        {"role": "user", "content": f"<facts>\n{facts_json}\n</facts>"},
    ]
    try:
        narration, _ = await narrate_structured(
            llm,
            messages,
            facts_json=facts_json,
            require_dates=require_dates,
            max_observation=ROUGH_MAX_OBSERVATION if rough else NORMAL_MAX_OBSERVATION,
            max_step=ROUGH_MAX_STEP if rough else NORMAL_MAX_STEP,
            max_tokens=300 if rough else 450,
            temperature=0.3,
            extra_banned=ROUGH_BANNED if rough else None,
        )
    except LLMError:
        return None
    return narration
