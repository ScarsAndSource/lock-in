"""
Text that did NOT come from the person typing into the chat: names that arrive by importing a calendar or by reading a
photo of a timetable. A hostile calendar invite or a poster with small print can carry a sentence addressed to the model
("ignore your instructions and ..."). That is indirect prompt injection, and it only matters where such text can reach a
model.

Where it can: the planner's <context> lists the person's habit names and open task titles, and a task can come from a
photo import. (Calendar event titles never reach a prompt: nothing that calls a model reads them.) So two small things:

  clean_label()   what an imported title is stored as: canonical text, no URLs, no markdown links or images, one line.
                  Nothing on a title should be clickable or fetchable, and a link is the usual way data leaves.
  is_hostile()    does it read like an instruction to the model? The same deterministic scorer the chat uses
                  (guard/inject.py), at the same "contained" threshold. Used to DROP the item from an import proposal
                  and to leave the name out of the planner's context. The name is never changed or deleted in the
                  person's own task list: it is just not shown to the model.

PURE: no I/O, no settings. A false positive costs one skipped import row or one name the planner can't see.
"""
from __future__ import annotations

import re

from app.guard.canon import canonicalize
from app.guard.inject import CONTAINED, assess

_MD_LINK = re.compile(r"!?\[([^\]\n]{0,160})\]\([^)\n]{0,2000}\)")      # [text](url) and ![alt](url) -> text
_URL = re.compile(r"(?:https?|ftp)://\S+|\bwww\.\S+|\bdata:[a-z]+/[a-z0-9.+-]+;base64,\S*", re.IGNORECASE)


def clean_label(raw: object, limit: int) -> str:
    """A short, single-line, link-free label. Not a string, or nothing left after cleaning -> ''."""
    if not isinstance(raw, str) or not raw:
        return ""
    text = canonicalize(raw, limit * 4, single_line=True)
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def is_hostile(raw: object) -> bool:
    """True when the text scores as an instruction aimed at the model (contained or blocked)."""
    return isinstance(raw, str) and assess(raw).score >= CONTAINED
