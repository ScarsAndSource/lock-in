"""Plain data the companion works on. No DB, no framework: the repository fills it, the pure modules read it."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Observations:
    """
    What the person's own history says about their day. Every value is a minute of the LOCAL day (0-1439).
    Only things the person did themselves are counted (a defaulted sleep row is a guess, not an observation).
    """
    wake_minutes: tuple[int, ...] = ()
    bed_minutes: tuple[int, ...] = ()
    checkin_minutes: tuple[int, ...] = ()
    first_open_minutes: tuple[int, ...] = ()          # the first app open of each day
    urges: tuple[tuple[int, bool], ...] = ()           # (minute, relapsed?)
