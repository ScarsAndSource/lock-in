"""
The companion's words. PURE and deterministic: a small bank per situation and tone, picked by the day number so the
line is stable within a day and different the next. No model call, so it works offline and costs nothing.

House rules (same as the nudge copy): plain, specific, never guilt, never urgency theatre, nothing that scolds.
"""
from __future__ import annotations

_CARD: dict[str, dict[str, tuple[str, ...]]] = {
    "floor": {
        "direct": ("Floor counts. Do the small version.", "Smallest version, then you're done.", "Floor day. Stay on the board."),
        "coach": ("Small is still showing up.", "Keep it gentle today. The floor counts.", "One small thing is enough today."),
    },
    "deadline": {
        "direct": ("This one has a clock on it.", "Do this first.", "Everything else can wait behind this."),
        "coach": ("This one matters most right now.", "Start with this, the rest will follow.", "One thing to land first."),
    },
    "guard": {
        "direct": ("Your own logs put urges here.", "This is your usual tough hour.", "Decide now, not at the moment."),
        "coach": ("A tough stretch is coming, and you can be ready.", "Your plan is cheaper to make now.", "You know this hour. Get ahead of it."),
    },
    "close": {
        "direct": ("Ten seconds. Defaults cover the usual.", "Lock it in or fix what was different.", "Close the day."),
        "coach": ("Whenever you're ready. The usual is filled in.", "Just confirm what happened today.", "A quick look back, then rest."),
    },
    "habit": {
        "direct": ("Next on the list.", "One tap when it's done.", "This one's still open."),
        "coach": ("Whenever feels right.", "A good moment for this one.", "One at a time."),
    },
    "task": {
        "direct": ("Next up.", "This is the one to clear.", "Open and waiting."),
        "coach": ("A gentle next step.", "Small win available.", "One thing off the list."),
    },
    "checkin": {
        "direct": ("Check-in is open whenever.", "Defaults are filled in.", "Ten seconds when you're ready."),
        "coach": ("No rush. It's ready when you are.", "The usual is already filled in.", "Whenever you like."),
    },
    "clear": {
        "direct": ("Nothing needs you right now.", "All clear.", "Quiet. Good."),
        "coach": ("You're all caught up.", "Nothing open. Enjoy it.", "A clear stretch."),
    },
}

_EVENING: dict[str, tuple[str, ...]] = {
    "direct": ("Ten seconds. Defaults cover the usual.", "Lock it in, or fix what was different.", "Close the day."),
    "coach": ("Whenever you're ready. The usual is filled in.", "A quick look back, then rest.", "Just confirm what happened today."),
}

TITLE_CHARS = 80


def _pick(bank: tuple[str, ...], seed: int) -> str:
    return bank[seed % len(bank)]


def clock_text(minute: int) -> str:
    """'9:30 PM'. No platform-specific strftime flags."""
    minute %= 1440
    h, m = divmod(minute, 60)
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def card_voice(kind: str, tone: str, seed: int) -> str:
    bank = _CARD.get(kind, _CARD["clear"])
    return _pick(bank.get(tone, bank["direct"]), seed)


def why_line(kind: str, tone: str, window: tuple[int, int] | None = None) -> str | None:
    """One short, honest reason the card is on top. Shown small, so the companion is never a black box."""
    if kind == "floor":
        return "Yesterday was a rough one, so today is lowered to the floor."
    if kind == "guard" and window is not None:
        return f"Your urge logs cluster around {clock_text(window[0])}–{clock_text(window[1])}."
    if kind == "deadline":
        return "It's your highest-importance open task."
    if kind == "close":
        return "It's near the time you usually close the day."
    if kind in ("habit", "task"):
        return "Nothing more urgent is open."
    return None


def moment_copy(moment: str, tone: str, seed: int, kind: str, title: str) -> tuple[str, str]:
    """(title, body) of the push for a moment."""
    if moment == "evening":
        bank = _EVENING.get(tone, _EVENING["direct"])
        return "Close today", _pick(bank, seed)
    shown = title if len(title) <= TITLE_CHARS else title[: TITLE_CHARS - 1].rstrip() + "…"
    return shown, card_voice(kind, tone, seed)
