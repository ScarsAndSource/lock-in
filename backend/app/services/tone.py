"""
Tone dial. profile.tone_preference is one of:

  direct  always the blunt analyst voice
  coach   always the warmer register (same facts, same rules, gentler delivery)
  auto    direct normally, coach after a rough stretch (2+ slipped scheduled days in a row)

Pure.
"""
from __future__ import annotations

TONES = ("auto", "direct", "coach")
AUTO_COACH_STREAK = 2


def resolve_tone(preference: str, slip_streak: int = 0) -> str:
    """The register to use RIGHT NOW: 'direct' or 'coach'."""
    if preference == "coach":
        return "coach"
    if preference == "auto" and slip_streak >= AUTO_COACH_STREAK:
        return "coach"
    return "direct"
