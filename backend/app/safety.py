"""
Hard-coded crisis path (SPEC section 8: a hard requirement, not a nice-to-have).
NO model is involved in detecting crisis language or in answering it.
- Detection is a deliberately HIGH-RECALL regex pass: a false positive costs one calm message;
  a false negative costs far more.
- It runs BEFORE any LLM call, is never rate-limited, never touches the daily AI cap, and answers
  with fixed text plus real resources.
- The pattern list is best-effort and meant to be extended. English, Roman-script Hindi / Hinglish,
  Devanagari and a few Urdu-script phrases are covered (Hinglish is how most users here actually type;
  Whisper writes Hindi speech in Devanagari or Urdu script, so voice check-ins arrive that way).
  It is a safety net, not a clinical screen, and the non-English lists want periodic review by native speakers.
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
    t = re.sub(r"\b2\b", "to", t)  # "i want 2 die" (before the leet map, which has no 2)
    t = t.translate(_LEET)  # k1ll -> kill, m4r -> mar
    t = re.sub(r"(?<=[a-z])[!*#](?=[a-z])", "i", t)  # k*ll / k!ll -> kill
    t = re.sub(r"(?<=[a-z])[._\-](?=[a-z])", "", t)  # k.i.l.l / self-harm -> selfharm
    # Devanagari: drop the nukta (ज़ -> ज, ख़ -> ख) and fold chandrabindu into anusvara (जाऊँ -> जाऊं), so one spelling matches all.
    t = t.replace("\u093c", "").replace("\u0901", "\u0902")
    return re.sub(r"\s+", " ", t).strip()


def _hinglish_view(normalized: str) -> str:
    """Roman Hindi has no spelling standard (maar / mar, jaaun / jaun, nahi / nhi). Collapse repeated vowels once, here,
    so the Hinglish patterns below are written against ONE spelling. Only this view is collapsed: the English
    patterns keep their double vowels (roof, feel)."""
    return re.sub(r"([aeiou])\1+", r"\1", normalized)


_PATTERNS = [re.compile(p) for p in (
    r"\bsuicid",
    r"\b(?:sucid|suiside|sucide|suside|sooicide|soocide)\w*",
    r"\bkill(?:ing)? ?my ?self\b",
    r"\bkms\b",
    r"\bunaliv",
    r"\bend(?:ing)? (?:my (?:own )?life|it all|myself)\b",
    r"\btak(?:e|ing) my (?:own )?life\b",
    r"\b(?:want|wanna|wana|wish|wished|wishing)(?: to| i was| i were| i could)?(?: be)? (?:die|dead|disappear forever)\b",
    r"\b(?:dont|do not) (?:want to|wanna|wana) (?:live|be alive|exist|wake up|be here anymore)\b",
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
    # Roman-script Hindi, the original short list (kept: these run on the plain-normalised text)
    r"\bmar(?:na| ?ja ?(?:na|ana)) chah(?:ta|ti)\b",
    r"\bmar jaun\b",
    r"\bjee(?:na|ne) (?:nahi|nhi) chah(?:ta|ti)\b",
    r"\bjeene (?:ka|ki) (?:mann?|ichha|iccha) (?:nahi|nhi)\b",
    r"\b(?:khud ?kushi|aatm ?hatya|atm ?hatya)\b",
    r"\bkhud ko khatam\b",
    r"\b(?:apni|apna) jaan (?:de|dene|le|lene)\b",
    # Devanagari (voice check-ins arrive in it). No \b here: a matra is not a "word" character to Python's regex.
    r"आत्म ?(?:हत्या|घात)",
    r"खुद ?कुशी|खुदखुशी",
    r"मरना (?:चाहत|है)",
    r"मर (?:ही )?(?:जाऊं|जाउं|जाऊंगा|जाऊंगी|जाना चाहत|जाता तो|जाती तो)",
    r"मरने (?:का|की|के) (?:मन|दिल|ख्याल|खयाल|विचार|इरादा|इच्छा)",
    r"जीना (?:नहीं|नही) चाहत",
    r"जीने (?:का|की|के) (?:मन|दिल|इच्छा|वजह|मकसद|मतलब|कोई (?:मतलब|वजह|मकसद))? ?(?:नहीं|नही)",
    r"जीने (?:का|की) क्या (?:फायदा|मतलब|वजह)",
    r"जि(?:ं|न्)दगी (?:खत्म|खतम)",
    r"जि(?:ं|न्)दगी से (?:थक|तंग|बेजार|ऊब)",
    r"(?:अपनी|खुद की|अपनी ही) जान (?:दे|ले)",
    r"जान दे (?:दूं|दूंगा|दूंगी|दो)",
    r"(?:खुद|अपने आप|अपने आपको) ?को (?:खत्म|खतम|मार|नुकसान|काट|चोट|जला|सजा)",
    r"फां?सी (?:लगा|लग|ले)",
    r"पंखे से लटक",
    r"(?:ज़|ज)हर (?:खा|पी|ले)",
    r"नस(?:ें|ों|े)? काट",
    r"दुनिया (?:(?:से|को) )?(?:चला जा|चले जा|जाना चाह|छोड)",
    r"सब (?:कुछ )?खत्म कर(?:ना|ने) चाह",
    r"मेरे बिना सब",
    r"मर जाऊं",
    # Urdu script (Whisper sometimes writes Hindustani speech this way)
    r"خود ?کشی",
    r"مرنا چاہ",
    r"جینا نہیں چاہ",
    r"زندگی ختم",
    r"مر جاؤں|مر جاوں",
)]


def _fold(pattern: str) -> str:
    """Patterns are WRITTEN with natural spellings (theek, neeche, aage) and folded the same way as the text."""
    return re.sub(r"([aeiou])\1+", r"\1", pattern)


_Z = r"[zj]ind(?:a)?g[ie]"          # zindagi / zindgi / jindagi (after vowel collapse)
_JEENA = r"j[ei]n[ae]y?"            # jeena / jeene / jina / jine
_NAHI = r"(?:nahi|nhi|nai|nahin|nhin|ni)"
_CHAHTA = r"(?:chah?t[aei]|chahat[aei]|chahiye|chahie)"
_KHUD = r"(?:khud|apne ?a?p|apnay ?a?p)"
_JAUN = r"j(?:a|ao|au|aon|aun|aunga|aungi|on)"
# "swallow / drink" with a first-person intent verb. A bare "le"/"kha" prefix would also match "leni padti hai" (a prescription)
# or "khatam", so the verb has to be one of these shapes.
_INTAKE = r"(?:(?:kha|pi|pe|le)\s*(?:lu|lun|lunga|lungi|raha|rahi|ke|k|kar|len[ae])\b|(?:khan[ae]|pin[ae]|pen[ae])\s+chah\w*)"

# Roman-script Hindi / Hinglish. Written against _hinglish_view(): "maar" is "mar", "jaaun" is "jaun", "zeher" may be "zehar".
_HINGLISH = [re.compile(_fold(p)) for p in (
    # --- wanting to die
    rf"\bmar(?:na|ne)? ?{_JAUN}\b.{{0,12}}\b{_CHAHTA}\b",
    rf"\bmar (?:hi )?{_JAUN}\b(?! ?(?:to|toh) (?:kya|kon|phir))",
    r"\b(?:mujhe|mujhko|mjhe|mereko|mereku|mko)\s+(?:ab\s+)?mar(?:na| ?jana)\b",
    rf"\bmar(?:na| ?jana)\s+{_CHAHTA}\b",
    r"\bmar(?:ne| ?jane)\s+(?:ka|ki|ke)\s+(?:man|mann|mn|dil|khayal|khyal|vichar|iccha|ichha|irada|plan|mood)\b",
    r"\bmar(?: hi)? (?:jata|jati) (?:to|toh) (?:acha|accha|achha|behtar|better|theek|sahi)\b",
    rf"\bkash\b.{{0,24}}\bmar (?:hi )?{_JAUN}\b",
    rf"\bkash\b.{{0,24}}\bmar (?:hi )?(?:jata|jati)\b",
    rf"\bmaut (?:{_CHAHTA}|mang\w*|aa ja\w*|de de|de do|mil ja\w*)\b",
    r"\b(?:apni|khud ki|apne) maut\b",
    # --- not wanting to live
    rf"\b{_JEENA}\s+{_NAHI}\s+(?:{_CHAHTA}|hai|h)\b",
    rf"\b{_JEENA}\s+(?:ka|ki|ke)\s+(?:koi\s+)?(?:man|mann|mn|dil|iccha|ichha|mood|maksad|matlab|fayda|faida|wajah|vajah|reason|point)\s*(?:hi\s*)?(?:{_NAHI}|reh|raha|rahi|bacha|bachi|khatam)\b",
    rf"\b{_JEENA}\s+(?:ka|ki|ke)\s+kya\s+(?:fayda|faida|matlab|point|maksad|wajah|vajah)\b",
    rf"\b{_JEENA}\s+se\s+(?:thak|tang|bezar|ub|ukta)\w*",
    rf"\bthak\s+g\w+\s+(?:hu\w*\s+)?(?:is\s+)?(?:{_Z}|{_JEENA}|life)\s+se\b",
    rf"\b{_Z}\s+(?:ko\s+)?(?:khatam|khtm|khatm|khtam)\b",
    rf"\b{_Z}\s+se\s+(?:thak|tang|bezar|ub|ukta)\w*",
    r"\bsab(?: kuch)? (?:khatam|khtm|khatm) (?:kar|kr)(?:na|ne)? (?:chah|chat)\w*",
    # --- harming or ending oneself (khud / apne aap ko ...)
    rf"\b{_KHUD} ?ko (?:kill|end|finish|hurt|harm|cut|kat|chot|nuksan|nuksaan|mar|jala|khatam|khtm|khatm|punish|saza|sza|goli)\w*",
    rf"\b{_KHUD} ?ko aag (?:laga|lag|de|le)\w*",
    r"\b(?:apni|apna|meri|apne) jaa?n (?:de|dene|le|lene|dun|lun|dedu|ledu)\w*",
    r"\bjaa?n (?:de|le) (?:du|dun|dunga|dungi|lu|lun|lunga|lungi)\b",
    r"\bkhud ?(?:khushi|kushi|kusi|kuchi)\b",
    r"\b(?:aatm|atm|aatma|atma) ?(?:hatya|hatiya|ghat)\w*",
    # --- burden / better off without me / goodbye
    r"\bsab(?:ke| ?pe| ?par)? ?(?:liye|lie|ke liye|upar)? ?(?:ek )?(?:bojh|bhoj|burden)\b",
    r"\bmain? (?:sabke? )?(?:liye )?(?:ek )?(?:bojh|bhoj|burden) (?:hu|hoon|hun|h|ban)\b",
    r"\bmere bina\b.{0,40}\b(?:theek|better|khush|acha|accha|achha|sukhi|behtar|aaram|sahi)\b",
    r"\bmere marne (?:ke baad|par|pe|se)\b",
    r"\b(?:is )?duniya (?:se|ko) (?:chala j|chale j|chal j|jana chah|chhod|chod|chor)\w*",
    r"\bduniya (?:ko )?(?:chhod|chod|chor) ?(?:ke|k|kar)? ?(?:jau|jaun|jana|chala|dunga|dungi)\w*",
    r"\balvida (?:duniya|dosto|sab|sabko|mummy|papa|maa|ma)\b",
    # --- methods (India-specific wording on purpose)
    r"\b(?:fansi|phansi|fasi|phasi|phanda|fanda|phande|fande)\s+(?:laga|lag|le|lu|lun|lunga|lungi)\w*",
    r"\b(?:pank[hae]|ped|rassi|dupatta|dupatte|chunni|chunri)\w*\s+(?:se|pe|par|me|mein|ke sath)\s+lat(?:ak|k)\w*",
    r"\bgale (?:me|mein|mai) (?:rassi|phanda|fanda|dupatta|chunni)\b",
    rf"\b(?:chat|chhat|chhath|terrace|balcony|building|bridge|pul|pool|hostel)\s*(?:se|pe|par)\s+(?:k[uo]d|jump|gir ?(?:{_JAUN}|jana))\w*",
    r"\b(?:nadi|nahar|river|talab|kuye|kuen|kua|dariya|samundar|sea|canal)\s*(?:me|mein|mai|main|m)\s+(?:k[uo]d|d[uo]b)\w*",
    r"\bd[uo]b\s+(?:ke|kar|k)?\s*mar\b",
    r"\b(?:train|rail|railway|metro)\s+(?:ke|k)\s+(?:aage|age|neeche|niche|samne)\s+(?:k[uo]d|aa j|let|lait|lat|chalang|chal j|ja k|ghus)\w*",
    r"\b(?:nas|nase|naso|nasen|nasein|nason)\s+(?:ko\s+)?(?:kat|kaat|cut)\w*",
    r"\b(?:hath|wrist|kalai)\s+(?:ko\s+)?kat\s*(?:lu|lun|lunga|lungi|du|dun|dunga|dungi|lena|lene|leta|leti|raha|rahi|ne ka|na)\b",
    r"\bblade\s+(?:se|ka|ke)\s+(?:hath|nas|nase|wrist|kalai|khud|apne|kat)\w*",
    rf"\b(?:zeher|zehar|zahar|zahr|jahar|jehar|jahr|jeher|zehr)\s+{_INTAKE}",
    rf"\b(?:neend|nind) ?(?:ki|ke|ka) ?(?:goli|goliyan|goliya|tablet|tablets|dawa|dawai|dava)\w*\s*{_INTAKE}",
    rf"\b(?:sari|saari|sabhi|sab|zyada|jyada|bahut sari|bohot sari|ek sath)\s+(?:goliyan|goliya|goli|tablets|tablet|dawai|dawa|pills)\s*{_INTAKE}",
    rf"\b(?:celphos|selphos|sulphas|salphas|sulfas|phosphide|rat ?poison|rat ?kill\w*|phenyl|harpic|dettol)\s*{_INTAKE}",
    rf"\bchuhe (?:marne )?(?:ki|wali) (?:dawa|dawai|dava)\w*\s*{_INTAKE}",
    r"\bover ?dos\w*\s+(?:kar|krna|karna|le l|le lu)\w*",
    r"\bjal\s+(?:ke|k|kar)\s+mar\b",
    r"\b(?:kerosene|mitti ka tel|petrol)\b.{0,30}\b(?:khud|apne|jal|aag)\b",
)]


# "ran 5 kms" must not read as the slang "kms": leet-normalising turns the digit into a letter, so strip
# number+unit distances BEFORE normalising. A bare "kms" still trips the screen.
_DISTANCE = re.compile(r"\b(?:\d+(?:[.,]\d+)?|(?:a )?(?:few|couple(?: of)?|several|some|many))\s*kms?\b", re.IGNORECASE)

# Everyday exaggeration that would otherwise read as "mar jaunga": "bhook se mar jaunga" (I'll die of hunger), "hansi se mar
# jaunga". Only a stated cause + "se" in front of the verb is removed, so "main mar jaunga" on its own still trips the screen.
_HYPERBOLE = re.compile(_fold(
    r"\b(?:hansi|hasi|bhook|bhuk|pyas|pyaas|thand|garmi|sharm|neend|thakan|boriyat|bore|dar|darr|khushi|maze|gussa|pareshani)"
    r"\s+(?:se|ke mare)\s+mar\s+(?:hi\s+)?(?:ja|jau|jaun|jaunga|jaungi|jaon|jata|jati|raha|rahi)\b"
))


def is_crisis(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    normalized = _normalize(_DISTANCE.sub(" ", text))
    if any(p.search(normalized) for p in _PATTERNS):
        return True
    roman = _HYPERBOLE.sub(" ", _hinglish_view(normalized))
    return any(p.search(roman) for p in _HINGLISH)


def conversation_has_crisis(*texts: str | None) -> bool:
    return any(is_crisis(t) for t in texts)
