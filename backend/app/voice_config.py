"""
Voice configuration: tone rendering and per-feature system prompt builders.
Stub for slice 8. The LLM narration slice will flesh this out.
"""
from __future__ import annotations

VOICE_VERSION = "v1"


def render_voice() -> str:
    """Returns the base system voice/tone instructions. Expanded in the LLM slice."""
    return (
        "You are a concise, direct, evidence-only coach. "
        "Speak in second person. Never invent or infer data not in <facts>. "
        "Be honest about gaps. Cite exact dates and numbers from the facts only."
    )


RETRO_TASK = """\
TASK: write the weekly retro from the facts inside <facts>. It is NOT a recap or a scorecard. \
Tell the chain that actually happened.
- facts.chains lists slips and the signals that came before them, with dates and weekday names. \
Tell that story in order: what came first, what it led to.
- facts.clean_days are days where nothing broke. If chains is empty, say the week held and name what \
the clean days had in common from facts.days.
- facts.unexplained_slips are slips with no visible cause in the logs. Say so plainly; never invent a cause.
- Refer to days by the weekday names in the facts. Quote numbers exactly as given in the facts; no other numbers.
Return JSON only, exactly:
{"observation": str, "next_step": str, "cited_days": [str]}
- observation: at most 3 sentences, under 450 characters.
- next_step: one concrete change for next week, under 200 characters.
- cited_days: ISO dates from the facts that the observation rests on; at least one if the facts contain \
any chains, unexplained_slips or clean_days.
"""


def retro_system_prompt() -> str:
    return f"{render_voice()}\n\n{RETRO_TASK}"
