"""
Hard-coded crisis path (SPEC section 8: a hard requirement, not a nice-to-have).
NO model is involved in detecting crisis language or in answering it.
- Detection is a deliberately HIGH-RECALL regex pass: a false positive costs one calm message;
  a false negative costs far more.
- It runs BEFORE any LLM call, is never rate-limited, never touches the daily AI cap, and answers
  with fixed text plus real resources.
- The pattern list is best-effort and meant to be extended (esp. other languages/slang). It is a
  safety net, not a clinical screen.
Resource numbers go stale: re-verify on a schedule and bump VERIFIED_ON.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

VERIFIED_ON = "2026-10-10"

SUPPORT_MESSAGE = (
    "What you wrote sounds heavy, and it's bigger than a habit, a streak or a score. "
    "I'm an app, not a crisis service, so I'm not going to coach you through this. "
    "Please reach a real person now: one of the lines below, or someone you trust who can be with you. "
    "If you might act on these thoughts soon, call your local emergency number right now. "
    "Your logs will still be here whenever you want them."
)


@dataclass(frozen=True)
class SupportResource:
    name: str
    contact: str
    detail: str


RESOURCES: dict[str, list[SupportResource]] = {
    "IN": [
        SupportResource("Emergency (India)", "112", "If you are in immediate danger, call this now."),
        SupportResource(
            "Tele-MANAS",
            "14416 or 1800-891-4416",
            "Free, 24x7 government mental-health helpline; counselling in many Indian languages.",
        ),
        SupportResource(
            "KIRAN",
            "1800-599-0019",
            "Free, 24x7 government mental-health helpline (now linked with Tele-MANAS).",
        ),
    ],
}

_FIND_A_HELPLINE = SupportResource("Find a helpline", "findahelpline.com", "Helplines listed by country.")
_LOCAL_EMERGENCY = SupportResource(
    "Local emergency number", "your local emergency number", "If you might act on these thoughts soon, call it now."
)

_TZ_REGION = {"Asia/Kolkata": "IN", "Asia/Calcutta": "IN"}  # extend as you add regions to RESOURCES


def support_payload(timezone: str | None = None, region: str | None = None) -> dict:
    code = (region or _TZ_REGION.get(timezone or "", "")).upper()
    if code in RESOURCES:
        items = [*RESOURCES[code], _FIND_A_HELPLINE]
    else:
        code, items = "GLOBAL", [_LOCAL_EMERGENCY, _FIND_A_HELPLINE]
    return {
        "region": code,
        "message": SUPPORT_MESSAGE,
        "resources": [asdict(r) for r in items],
        "verified_on": VERIFIED_ON,
    }


# ---------------------------------------------------------------- detection

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text[:5000]).lower()
    t = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", t)  # zero-width characters
    t = t.replace("'", "").replace("\u2019", "").replace("`", "")  # don't -> dont
    t = t.translate(_LEET)  # k1ll -> kill
    t = re.sub(r"(?<=[a-z])[!*#](?=[a-z])", "i", t)  # k*ll / k!ll -> kill
    t = re.sub(r"(?<=[a-z])[._\-](?=[a-z])", "", t)  # k.i.l.l / self-harm -> selfharm
    return re.sub(r"\s+", " ", t).strip()


_PATTERNS = [re.compile(p) for p in (
    r"\bsuicid",
    r"\bkill(?:ing)? ?my ?self\b",
    r"\bkms\b",
    r"\bunaliv",
    r"\bend(?:ing)? (?:my (?:own )?life|it all|myself)\b",
    r"\btak(?:e|ing) my (?:own )?life\b",
    r"\b(?:want|wanna|wish|wished|wishing)(?: to| i was| i were| i could)?(?: be)? (?:die|dead|disappear forever)\b",
    r"\b(?:dont|do not) (?:want to|wanna) (?:live|be alive|exist|wake up|be here anymore)\b",
    r"\bno (?:reason|point) (?:to|in) (?:live|living|go on|going on|being alive)\b",
    r"\bnothing to live for\b",
    r"\b(?:not|isnt|aint|wasnt) worth living\b",
    r"\bbetter off (?:dead|without me)\b",
    r"\b(?:cant|cannot|can not) go on\b",
    r"\b(?:hurt|harm|cut|burn|punish|injure)(?:ing|ting)? ?my ?self\b",
    r"\bself ?(?:harm|injur|mutilat)",
    r"\b(?:hang|shoot|poison|drown|stab|slit)(?:ing)? (?:my ?self|my wrists)\b",
    r"\bover ?dos\w* (?:on purpose|myself|on my)",
    r"\bjump(?:ing)? (?:off|from) (?:the |a |my )?(?:roof|bridge|building|terrace|balcony|hostel)",
    # Roman-script Hindi (best effort, extend freely)
    r"\bmar(?:na| ?ja ?(?:na|ana)) chah(?:ta|ti)\b",
    r"\bmar jaun\b",
    r"\bjee(?:na|ne) (?:nahi|nhi) chah(?:ta|ti)\b",
    r"\bjeene (?:ka|ki) (?:mann?|ichha|iccha) (?:nahi|nhi)\b",
    r"\b(?:khud ?kushi|aatm ?hatya|atm ?hatya)\b",
    r"\bkhud ko khatam\b",
    r"\b(?:apni|apna) jaan (?:de|dene|le|lene)\b",
)]


# "ran 5 kms" must not read as the slang "kms": leet-normalising turns the digit into a letter, so strip
# number+unit distances BEFORE normalising. A bare "kms" still trips the screen.
_DISTANCE = re.compile(r"\b\d+(?:[.,]\d+)?\s*kms?\b", re.IGNORECASE)


def is_crisis(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    normalized = _normalize(_DISTANCE.sub(" ", text))
    return any(p.search(normalized) for p in _PATTERNS)


def conversation_has_crisis(*texts: str | None) -> bool:
    return any(is_crisis(t) for t in texts)
