"""
Prompt-injection scorer: deterministic, 0-3, English + Hinglish + Devanagari. No model, no I/O.

  0-1  normal.   2  CONTAINED: no planner (no writes), hardened reminder, answer from facts.   3  BLOCKED: canned reply.
It never accuses. Runs AFTER the crisis screen, on the RAW message. Result carries category codes only, never user text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.guard.canon import detection_view, has_tag_chars, hidden_char_count

CONTAINED = 2
BLOCKED = 3


@dataclass(frozen=True, slots=True)
class InjectionVerdict:
    score: int
    reasons: tuple[str, ...] = ()

    @property
    def contained(self) -> bool:
        return self.score >= CONTAINED

    @property
    def blocked(self) -> bool:
        return self.score >= BLOCKED


def _fold(pattern: str) -> str:
    return re.sub(r"([aeiou])\1+", r"\1", pattern)     # Roman Hindi has no spelling standard: collapse doubled vowels


_VERB = r"(?:ignore|disregard|forget|override|bypass)"
_NOUN = r"(?:instructions?|rules|prompts?|guidelines|directives|constraints|restrictions|programming)"

_ENGLISH: tuple[tuple[str, int, re.Pattern[str]], ...] = tuple(
    (code, pts, re.compile(rx)) for code, pts, rx in (
        ("override", 2, rf"\b{_VERB}\s+(?:all\s+|any\s+|every\s+|the\s+|your\s+|these\s+|those\s+|my\s+|of\s+)*"
                        rf"(?:previous|prior|above|earlier|preceding|former|original|initial|system|safety)\s+{_NOUN}\b"),
        ("override", 2, rf"\b{_VERB}\s+(?:all\s+|any\s+)?(?:of\s+)?(?:your|ur)\s+(?:\w+\s+)?"
                        rf"(?:instructions?|rules|guidelines|programming|restrictions|training|prompt)\b"),
        ("override", 2, rf"\b(?:ignore|disregard|forget)\s+(?:everything|all)\s+(?:above|before|i\s+said\s+before|"
                        rf"you\s+were\s+told|you\s+know)\b"),
        ("reveal", 2, r"\b(?:reveal|show|print|display|repeat|output|tell|leak|dump|recite|read)\b[^.?!]{0,30}\b"
                      r"(?:system\s+(?:prompt|message|instructions?)|(?:initial|hidden|original|secret)\s+(?:prompt|instructions?)|"
                      r"(?:your|ur)\s+(?:prompt|instructions?|programming|guidelines|rules))\b"),
        ("reveal", 1, r"\bsystem\s+prompt\b"),
        ("reveal", 1, r"\bwhat\s+(?:are|were|is)\s+your\s+(?:system\s+)?(?:instructions?|prompt|rules|guidelines)\b"),
        ("persona", 1, r"\byou\s+are\s+now\b"),
        ("persona", 1, r"\bpretend\s+(?:you|to\s+be|that\s+you)\b"),
        ("persona", 1, r"\b(?:pretend|act|behave)\s+(?:as|like)\s+(?:an?\s+|the\s+)?(?:\w+\s+){0,2}"
                       r"(?:ai|assistant|bot|chatbot|gpt|llm|model|developer|dan|jailbroken|unfiltered|unrestricted|evil|hacker|admin|root|system)\b"),
        ("persona", 2, r"\b(?:developer|dev|debug|god|admin|sudo|jailbreak(?:ed)?|dan)\s+mode\b"),
        ("persona", 2, r"\bjailbreak\b|\bdo\s+anything\s+now\b"),
        ("role_token", 2, r"<\|[a-z_]{2,20}\|>|\[/?inst\]|<<\s*/?sys\s*>>|\[system\]"),
        ("role_token", 2, r"(?:^|\s)#{2,}\s*(?:system|instructions?|assistant|new\s+instructions?)\b"),
        ("role_token", 1, r"(?:^|\s)(?:system|assistant|developer)\s*:\s"),
        ("tag_breakout", 2, r"</?\s*(?:user_question|facts|message|context|system|instructions?|assistant|prompt)\b"),
        ("new_instructions", 2, r"\b(?:new|updated|real|actual|important)\s+instructions?\s*:"),
        ("new_instructions", 1, r"\bfrom\s+now\s+on\b[^.?!]{0,40}\b(?:you|only|always|never|respond|reply|answer)\b"),
        ("new_instructions", 1, r"\b(?:decode|decrypt)\s+(?:this|the\s+following|the\s+text\s+below)\b"),
        ("exfil", 2, r"!\[[^\]]*\]\(|\[[^\]]{0,80}\]\(\s*(?:https?:|//|data:|javascript:)"),
        ("url", 1, r"\bhttps?://|\bwww\.|\bftp://|\bdata:[a-z]+/[a-z0-9.+-]+;base64"),
    )
)

_HINGLISH: tuple[tuple[str, int, re.Pattern[str]], ...] = tuple(
    (code, pts, re.compile(_fold(rx))) for code, pts, rx in (
        ("hinglish", 2, r"\b(?:pehle|pichle|pichhle|purane|upar ke|saare|sare|sab)\s+(?:ke\s+)?(?:instructions?|niyam|rules?|nirdesh|prompt)"
                        r"\s+(?:ko\s+)?(?:bhool|bhul|ignore|nazar ?andaz|andekha|hata|delete)\w*"),
        ("hinglish", 2, r"\b(?:instructions?|niyam|rules?|nirdesh)\s+(?:ko\s+)?(?:bhool|bhul|ignore|nazar ?andaz|andekha)\w*\s+(?:kar|karo|kr|do|de)\b"),
        ("hinglish", 2, r"\bsystem\s*prompt\s+(?:ko\s+)?(?:dikha|bata|batao|dikhao|show|print|likh|bol)\w*"),
        ("hinglish", 2, r"\b(?:apne|tumhare|tere|aapke|apni)\s+(?:instructions?|rules?|niyam|prompt)\s+(?:ko\s+)?(?:bata|dikha|batao|dikhao|bol)\w*"),
    )
)

# No \b in Devanagari: a matra is not a "word" character to Python's regex. Nukta is already stripped by detection_view.
_DEVANAGARI: tuple[tuple[str, int, re.Pattern[str]], ...] = tuple(
    (code, pts, re.compile(rx)) for code, pts, rx in (
        ("devanagari", 2, r"(?:पिछले|पहले|ऊपर\s+के|सारे|सभी|पुराने)\s*(?:के\s+)?"
                          r"(?:निर्देश(?:ों)?|नियम(?:ों)?|इंस्ट्रक्शन(?:्स|स)?|प्रॉम्प्ट|प्रोम्प्ट)\s*(?:को\s+)?"
                          r"(?:भूल|भुला|नजरअंदाज|अनदेखा|इग्नोर)"),
        ("devanagari", 2, r"सिस्टम\s*(?:प्रॉम्प्ट|प्रोम्प्ट)\s*(?:को\s+)?(?:दिखा|बता|बोल|लिख)"),
        ("devanagari", 2, r"(?:अपने|तुम्हारे|आपके|तेरे)\s+(?:निर्देश|नियम|इंस्ट्रक्शन)\s*(?:को\s+)?(?:बताओ|दिखाओ|बताइए|बताएं|बता|दिखा)"),
        ("devanagari", 1, r"सिस्टम\s*(?:प्रॉम्प्ट|प्रोम्प्ट)"),
    )
)

_BASE64 = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")


def _points_to_score(points: int) -> int:
    if points <= 0:
        return 0
    if points == 1:
        return 1
    return 2 if points <= 3 else 3


def assess(raw: str | None) -> InjectionVerdict:
    """Score a RAW user message. Each category counts once, at its highest weight, so repeating a phrase doesn't stack."""
    if not raw or not raw.strip():
        return InjectionVerdict(0)
    best: dict[str, int] = {}

    def hit(code: str, pts: int) -> None:
        if pts > best.get(code, 0):
            best[code] = pts

    view = detection_view(raw)
    hinglish_view = re.sub(r"([aeiou])\1+", r"\1", view)
    for code, pts, rx in _ENGLISH:
        if rx.search(view):
            hit(code, pts)
    for code, pts, rx in _HINGLISH:
        if rx.search(hinglish_view):
            hit(code, pts)
    for code, pts, rx in _DEVANAGARI:
        if rx.search(view):
            hit(code, pts)

    sample = raw[:4000]
    if _BASE64.search(sample) or _HEX.search(sample):
        hit("blob", 1)
    if has_tag_chars(sample):
        hit("tag_chars", 2)
    elif hidden_char_count(sample) >= 3:
        hit("hidden_chars", 1)
    return InjectionVerdict(_points_to_score(sum(best.values())), tuple(sorted(best)))
