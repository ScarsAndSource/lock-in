"""
Input canonicalizer: ONE place that turns raw user text into something safe to put in a prompt, a title or a log.

Two views, on purpose:
  canonicalize()    what the model, the database and the UI see. Conservative: keeps real text (Hindi, emoji) intact.
  detection_view()  what the injection scorer matches against. Aggressive: lower-cased, de-obfuscated, never stored.

The crisis screen does NOT use this module. It runs on the RAW text, before anything here, exactly as before.
PURE: no I/O, no settings, no clock.
"""
from __future__ import annotations

import re
import unicodedata

_BRACKET_LOOKALIKES = dict.fromkeys(map(ord, "\u2039\u203a\u2329\u232a\u27e8\u27e9\u276c\u276d\u276e\u276f\u3008\u3009\u29fc\u29fd"), None)
_BRACKETS = {ord("<"): None, ord(">"): None, **_BRACKET_LOOKALIKES}

# Joiners are kept ONLY directly after a letter/mark of Indic or Arabic script (needed to shape conjuncts), so they
# can't be used to split an English word like "ig\u200bnore".
_JOINERS = {"\u200c", "\u200d"}
_JOINER_SCRIPTS = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x0900, 0x0DFF))

_ALLOWED_CONTROLS = {"\t", "\n", "\r"}
_REPEAT = re.compile(r"([^\d\s])\1{6,}")           # "heyyyyyyyyy" -> "heyyy". Digits are exempt ("1000000").
_SPACES = re.compile(r"[ \t\f\v\u00a0\u2000-\u200a\u202f\u205f\u3000]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_TAG_BLOCK = range(0xE0000, 0xE0080)               # invisible "tag" characters: ASCII smuggling
_MAX_INPUT_FACTOR = 4                              # bound the work on a hostile megabyte (NFKC can expand)


def _in_joiner_script(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _JOINER_SCRIPTS)


def _strip_invisible(text: str) -> tuple[str, int]:
    """Drop control, format (zero-width, bidi, tag), surrogate, private-use and unassigned characters.
    Returns (clean_text, how_many_hidden_characters_were_removed)."""
    out: list[str] = []
    hidden = 0
    prev = ""
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in _ALLOWED_CONTROLS:
            out.append(ch)
        elif cat in ("Cc", "Cs", "Co", "Cn"):
            hidden += 1
            continue
        elif cat == "Cf":
            if ch in _JOINERS and prev and _in_joiner_script(prev):
                out.append(ch)
            else:
                hidden += 1
                continue
        else:
            out.append(ch)
        prev = ch
    return "".join(out), hidden


def hidden_char_count(raw: str) -> int:
    _, hidden = _strip_invisible(unicodedata.normalize("NFKC", raw[:4000]))
    return hidden


def has_tag_chars(raw: str) -> bool:
    """Unicode tag characters (U+E0000-E007F): the 'invisible ASCII' smuggling channel."""
    return any(ord(ch) in _TAG_BLOCK for ch in raw[:4000])


def canonicalize(text: str, max_len: int, *, single_line: bool = False) -> str:
    """NFKC, no invisible characters, no angle brackets (or look-alikes), tidy whitespace, truncated."""
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", str(text)[: max_len * _MAX_INPUT_FACTOR])
    out, _ = _strip_invisible(out)
    out = out.translate(_BRACKETS)
    out = _REPEAT.sub(lambda m: m.group(1) * 3, out)
    if single_line:
        out = re.sub(r"\s+", " ", out).strip()
    else:
        out = _SPACES.sub(" ", out.replace("\r\n", "\n").replace("\r", "\n"))
        out = _BLANK_LINES.sub("\n\n", re.sub(r" *\n *", "\n", out)).strip()
    return out[:max_len]


# ---------------------------------------------------------------- detection view
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
# Cyrillic / Greek letters that render like Latin ones. Matching only: stored text is untouched.
_CONFUSABLES = str.maketrans({
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0443": "y", "\u0445": "x",
    "\u0456": "i", "\u0458": "j", "\u0455": "s", "\u0501": "d", "\u03bf": "o", "\u03b1": "a", "\u03bd": "v",
    "\u03b9": "i", "\u03ba": "k", "\u0261": "g",
})


def detection_view(raw: str) -> str:
    """For MATCHING ONLY. Keeps angle brackets (tag breakout is a signal), drops every invisible character including
    joiners, folds leetspeak, look-alike letters and Devanagari spelling variants. Never stored or sent to a model."""
    t = unicodedata.normalize("NFKC", raw[:4000]).lower()
    t, _ = _strip_invisible(t)
    t = "".join(ch for ch in t if ch not in _JOINERS)
    t = t.translate(_CONFUSABLES)
    t = t.replace("'", "").replace("\u2019", "").replace("`", "")
    t = t.replace("\u093c", "").replace("\u0901", "\u0902")          # nukta off, chandrabindu -> anusvara
    t = re.sub(r"(?<=[a-z])[._\-*](?=[a-z])", "", t)                 # i.g.n.o.r.e / ig-nore -> ignore
    t = t.translate(_LEET) if re.search(r"[a-z][0-9@$]|[0-9@$][a-z]", t) else t
    return re.sub(r"\s+", " ", t).strip()
