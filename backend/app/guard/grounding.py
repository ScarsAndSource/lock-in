"""
Grounding check for agent actions: does each action trace back to WORDS THE USER ACTUALLY WROTE?

validate_plan() proves an action is well-formed; it can't prove the person asked for it. Names also reach the planner
from imports (calendar, photos), an indirect-injection path. A failed check never drops the action and never lets it
through silently: it is DOWNGRADED to a pending card (one tap, re-validated on confirm). Only model output is checked;
the confirm endpoint is not (the person tapping Save IS the grounding). PURE.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

BULK_LIMIT = 3
BULK_TOOLS = frozenset({"complete_task", "reschedule_task", "snooze_task"})
TITLE_COVERAGE = 0.7
GENERIC_REASON = "I couldn't tie that to your exact words. Is this right?"


@dataclass(frozen=True, slots=True)
class Ungrounded:
    code: str                       # habit_name | status | day | task_name | title | remind | repeat | notes | sleep_time | quality | minutes
    reason: str = GENERIC_REASON    # shown on the pending card


_STOP = frozenset("""
the and for with that this from have has had was were are you your not but can will just got get its into out about some
then than too very today tomorrow yesterday tonight please pls remind reminder reminders me my mine our add task tasks todo
set log mark move push snooze reschedule postpone complete finish finished done did kar karna karo ko ka ki ke hai hain ho
hu hoon liya diya kal aaj mujhe ek yaad dila dena toh aur se pe par mein main mai tick check note put create schedule
""".split())
_NEGATIONS = frozenset("""
not no never nope didnt dont doesnt cant cannot couldnt wont wasnt isnt missed miss skip skipped skipping forgot nahi nhi
nai nahin chhod chhoda chod bhool bhul नहीं नही छोड़ छोड भूल मिस
""".split())
_YESTERDAY = frozenset({"yesterday", "yday", "kal", "कल"})

_CUES: dict[str, frozenset[str]] = {
    "done": frozenset("""
        done did finished finish completed complete hit crushed nailed went worked trained studied meditated ran walked
        read played practiced practised cooked cleaned drank ate woke tick ticked checked mark marked log logged kar liya
        li kiya gaya gya hogaya hogya pura poora khatam कर किया लिया हो गया पूरा खत्म
    """.split()),
    "skipped": frozenset("""
        skip skipped skipping missed miss didnt dont couldnt cant not no nahi nhi nai nahin forgot bailed passed rested
        chhod chhoda chod bhool bhul नहीं नही छोड़ छोड भूल मिस
    """.split()),
    "partial": frozenset("""
        partial partially half halfway bit little some only floor minimum minimal tiny short shortened quick barely
        lighter light reduced just thoda aadha आधा थोड़ा थोडा
    """.split()),
    "stretch": frozenset("stretch extra more double bonus longer over beyond additional pr zyada ज्यादा".split()),
}
_CUES["floor"] = _CUES["partial"]
_LOG_VERBS = frozenset({"log", "mark", "tick", "check", "add", "put", "note"})
_REMIND_CUES = frozenset("remind reminder reminders reminded alert notify ping yaad याद".split())
_REPEAT_CUES = frozenset("every daily weekly each repeat repeating recurring weekdays weekends nightly monthly har roz rozana हर रोज रोजाना".split())
_QUALITY_WORDS = frozenset("great good bad terrible awful poor ok okay fine restless rough amazing deep light broken well badly rested tired accha acha bura kharab achhi neend".split())
_TIME_WORDS = frozenset("hour hours hr hrs min mins minute minutes half quarter tomorrow tonight morning evening afternoon week weekend later kal ghanta ghante aadha".split())
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "noon": 12, "midnight": 0,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "saat": 7, "aath": 8,
    "nau": 9, "das": 10, "gyarah": 11, "barah": 12,
}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text[:4000]).lower()
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    return t.replace("'", "").replace("\u2019", "").replace("`", "")


def _words(text: str) -> list[str]:
    """Unicode-aware tokens. Python's \\w drops Devanagari vowel signs, so split on letter/mark/number categories."""
    out: list[str] = []
    cur: list[str] = []
    for ch in _norm(text):
        if unicodedata.category(ch)[0] in "LMN":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def content_tokens(text: str) -> list[str]:
    out = []
    for w in _words(text):
        if w in _STOP:
            continue
        if w.isdigit() or len(w) >= 3 or (len(w) >= 2 and not w.isascii()):
            out.append(w)
    return out


def _match(a: str, b: str) -> bool:
    """Same word allowing endings: meditate/meditated/meditation, run/running, study/studied."""
    if a == b:
        return True
    n = min(len(a), len(b))
    cp = 0
    while cp < n and a[cp] == b[cp]:
        cp += 1
    return cp >= 4 or (cp == n and cp >= 3)


def _covered(token: str, message_words: list[str]) -> bool:
    return any(_match(token, w) for w in message_words)


def _numbers(text: str) -> set[int]:
    """Every number in the message: any-script digits, 'h:mm' and 'hmm' forms, and number words."""
    out: set[int] = set()
    cur: list[str] = []

    def flush() -> None:
        if not cur:
            return
        s = "".join(cur)
        cur.clear()
        out.add(int(s))
        if 3 <= len(s) <= 4:                      # "130" / "0130" -> 1 and 30
            out.add(int(s[:-2]))
            out.add(int(s[-2:]))

    for ch in _norm(text):
        if unicodedata.category(ch) == "Nd":
            cur.append(str(unicodedata.decimal(ch)))
        else:
            flush()
    flush()
    for w in _words(text):
        if w in _NUMBER_WORDS:
            out.add(_NUMBER_WORDS[w])
    return out


def _has(words: list[str], vocab: frozenset[str]) -> bool:
    return any(w in vocab for w in words)


# ---------------------------------------------------------------- per-tool checks
def _day_check(words: list[str], day_offset: int) -> Ungrounded | None:
    said_yesterday = _has(words, _YESTERDAY)
    last_night = "last" in words and ("night" in words or "evening" in words)   # reads as yesterday, esp. for sleep
    if day_offset < 0 and not (said_yesterday or last_night):
        return Ungrounded("day")
    if day_offset == 0 and said_yesterday:
        return Ungrounded("day", "You mentioned yesterday. Is this for today?")
    return None


def _habit(args: dict, words: list[str], message: str, habit_name: str | None, day_offset: int) -> Ungrounded | None:
    if not habit_name:
        return Ungrounded("habit_name")
    name_tokens = content_tokens(habit_name)
    named = any(_covered(t, words) for t in name_tokens) if name_tokens else _norm(habit_name).strip() in _norm(message)
    if not named:
        return Ungrounded("habit_name")
    status = str(args.get("status", ""))
    positive = status in ("done", "partial", "floor", "stretch")
    if positive and _has(words, _NEGATIONS):                       # the costliest model error: flipping polarity
        return Ungrounded("status", "That sounded negative. Is this right?")
    if not (_has(words, _CUES.get(status, frozenset())) or (positive and _has(words, _LOG_VERBS))):
        return Ungrounded("status")
    return _day_check(words, day_offset)


def _sleep(args: dict, words: list[str], message: str, day_offset: int) -> Ungrounded | None:
    nums = _numbers(message)
    half_or_quarter = "half" in words or "quarter" in words
    for key in ("bed", "woke"):
        value = args.get(key)
        if not value:
            continue
        try:
            hh, mm = int(str(value)[:2]), int(str(value)[3:5])
        except ValueError:
            return Ungrounded("sleep_time")
        hour_ok = bool(nums & {hh, hh % 12 or 12}) or (hh == 0 and "midnight" in words) or (hh == 12 and "noon" in words)
        if not hour_ok:
            return Ungrounded("sleep_time")
        if mm and mm not in nums and not half_or_quarter:
            return Ungrounded("sleep_time")
    q = args.get("quality")
    if q and q not in nums and not _has(words, _QUALITY_WORDS):
        return Ungrounded("quality")
    return _day_check(words, day_offset)


def _capture(args: dict, words: list[str]) -> Ungrounded | None:
    title = content_tokens(str(args.get("title") or ""))
    if not title:
        return Ungrounded("title")
    if sum(1 for t in title if _covered(t, words)) / len(title) < TITLE_COVERAGE:
        return Ungrounded("title", "I changed your wording a bit. Is this task right?")
    if args.get("remind") and not _has(words, _REMIND_CUES):
        return Ungrounded("remind", "You didn't ask for a reminder. Set one anyway?")
    if args.get("repeat_days") and not _has(words, _REPEAT_CUES):
        return Ungrounded("repeat", "You didn't say this repeats. Save it as repeating?")
    notes = content_tokens(str(args.get("notes") or ""))
    if notes and sum(1 for t in notes if _covered(t, words)) / len(notes) < TITLE_COVERAGE:
        return Ungrounded("notes")
    return None


def _task_ref(tool: str, args: dict, words: list[str], message: str, task_title: str | None) -> Ungrounded | None:
    if not task_title:
        return Ungrounded("task_name")
    title = content_tokens(task_title)
    if not title or not any(_covered(t, words) for t in title):
        return Ungrounded("task_name", "I'm not sure which task you meant. Is this the one?")
    if tool == "snooze_task" and not (_numbers(message) or _has(words, _TIME_WORDS)):
        return Ungrounded("minutes")
    return None


def grounding_reason(
    tool: str, args: dict, message: str, *,
    habit_name: str | None = None, task_title: str | None = None, day_offset: int = 0,
) -> Ungrounded | None:
    """None = grounded. habit_name / task_title are the names the CALLER resolved from the action's id (never the
    model's own wording). day_offset is 0 for today, -1 for yesterday."""
    words = _words(message)
    if tool == "log_habit":
        return _habit(args, words, message, habit_name, day_offset)
    if tool == "log_sleep":
        return _sleep(args, words, message, day_offset)
    if tool == "capture_task":
        return _capture(args, words)
    if tool in ("complete_task", "snooze_task", "reschedule_task"):
        return _task_ref(tool, args, words, message, task_title)
    return None     # set_intention is always confirmed by the executor


def bulk_guard(tools: list[str]) -> bool:
    """True when one message would change BULK_LIMIT or more existing tasks: all of them wait for a tap."""
    return sum(1 for t in tools if t in BULK_TOOLS) >= BULK_LIMIT
