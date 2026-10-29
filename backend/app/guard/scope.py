"""
Scope gate: a cheap lexical check for "write my code / essay / translate this" asks. Canned reply, NO model call.
Deliberately narrow: a verb alone never trips it, and it steps aside when the user is talking about their own to-do
("remind me to write the essay"). Runs after the crisis screen and the injection scorer, on the raw message. PURE.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.guard.canon import detection_view

OUT_OF_SCOPE_REPLY = (
    "I only work from your logs: habits, sleep, study, screen time, urges and tasks. "
    "Ask me about those, or tell me what to log."
)


@dataclass(frozen=True, slots=True)
class ScopeVerdict:
    out_of_scope: bool
    kind: str | None = None      # generate | translate | solve | trivia | rewrite | hinglish (never user text)


_THING = (r"(?:code|script|program|function|class|algorithm|regex|sql(?:\s+query)?|api|website|essay|poem|story|song|lyrics|rap|"
          r"joke|speech|cover\s+letter|resume|article|blog(?:\s+post)?|assignment|homework|report|paragraph|caption|tweet|"
          r"thread|email|letter|recipe)")

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (kind, re.compile(rx)) for kind, rx in (
        ("generate", rf"\b(?:write|generate|create|make|give\s+me|draft|compose|code|build|program|implement|debug|refactor)\b"
                     rf"[^.?!]{{0,40}}\b{_THING}\b"),
        ("translate", r"\btranslate\b[^.?!]{0,40}\b(?:this|that|the\s+following|into|to)\b"),
        ("solve", r"\b(?:solve|calculate|derive|prove|integrate|differentiate)\b[^.?!]{0,30}(?:\d|\bequation\b|\bproblem\b|\bintegral\b)"),
        ("trivia", r"\b(?:capital\s+of|population\s+of|who\s+(?:invented|discovered|won\s+the|was\s+the\s+first|is\s+the\s+(?:president|ceo|prime|richest|best))|tell\s+me\s+a\s+joke|"
                   r"bitcoin\s+price|stock\s+price|weather\s+in)\b"),
        ("rewrite", r"\b(?:summari[sz]e|paraphrase|rewrite|proofread|rephrase)\b[^.?!]{0,30}\b"
                    r"(?:this|that|the\s+following|text|article|paragraph|essay|email|document)\b"),
        ("hinglish", r"\b(?:code|essay|poem|kavita|story|kahani|gaana|joke|chutkula)\s+(?:likh|likho|bana|banao|sunao|de|do)\w*"),
    )
)

# Words just BEFORE the match that say the user is talking about their own to-do, not asking the model.
_OWN_TODO = re.compile(
    r"(?:remind|reminder|task|todo|to-do|add|schedule|need\s+to|have\s+to|got\s+to|gotta|must|going\s+to|plan\s+to|"
    r"planning\s+to|finish|finished|working\s+on|worked\s+on|did|done|due|deadline|i\s+should|i\s+want\s+to|yaad)\b[^.?!]{0,30}$"
)
_LOOKBACK = 45


def check(raw: str | None) -> ScopeVerdict:
    if not raw or not raw.strip():
        return ScopeVerdict(False)
    view = detection_view(raw)
    for kind, rx in _RULES:
        m = rx.search(view)
        if m is None:
            continue
        if _OWN_TODO.search(view[max(0, m.start() - _LOOKBACK): m.start()] + " "):
            continue
        return ScopeVerdict(True, kind)
    return ScopeVerdict(False)
