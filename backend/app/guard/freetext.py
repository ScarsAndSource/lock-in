"""
One screen for every free-text box that feeds a model OUTSIDE the chat: task capture ("remind me to ..."), the typed
check-in and the voice check-in transcript. The chat already scores messages (guard/inject.py) before anything else; these
three entry points did not, so they were the cheap way to spend the AI budget or to aim an instruction at a parser.

screen() returns True when the text should NOT go to a model. The caller then takes its deterministic path (capture:
the regex fallback parser; check-in: an empty proposal). Nothing is refused and nothing is accused: the person's own text
is still kept as written, it just isn't handed to a model. A hit adds a strike (limits/strikes.py), with a keyed digest of
the text for correlation, never the text itself. Runs AFTER the crisis screen, on the raw text, same threshold as the chat's
"contained" mode. A false positive costs one capture parsed by regex instead of by the model.
"""
from __future__ import annotations

from uuid import UUID

from app import audit
from app.guard.inject import assess
from app.limits import strikes


async def screen(user_id: UUID | str, raw: str, *, source: str) -> bool:
    verdict = assess(raw)
    if not (verdict.blocked or verdict.contained):
        return False
    await strikes.record(
        user_id, "injection_blocked" if verdict.blocked else "injection_contained",
        meta={"msg": audit.digest(raw), "src": source, "reasons": ",".join(verdict.reasons)[:60]},
    )
    return True
    