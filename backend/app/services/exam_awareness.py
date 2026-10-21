"""
Exam awareness for the next-best-action engine. PURE.

Given the person's upcoming exams, produce AT MOST ONE nudge, scaled to how close the nearest exam is.
It is a candidate with a score, not an override: it slots into next_action's ranking.

  100  floor (after a slip)  <- still wins
   95  exam today, not yet started    "Exam today": eat, check what to bring, leave early
   92  deadline task
   90  exam tomorrow                  "Keep tonight light"
   88  guard
   85  close
   62  exam in 2-3 days               one focused block on the weakest topic
   60  habit
   40  exam in 4-7 days               a gentle heads-up that sits under real work
   30  checkin

Once an exam has started today, the nudge disappears (we never know when it ends). Two exams on the nearest
day collapse into one card ("+1 more that day"). It does not know the syllabus and never pretends to.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

SCORE_TODAY, SCORE_TOMORROW, SCORE_NEAR, SCORE_FAR = 95, 90, 62, 40
NEAR_DAYS = 3
WINDOW_DAYS = 7
MAX_TITLE = 60


@dataclass(frozen=True, slots=True)
class ExamEvent:
    event_id: str
    title: str
    starts_at: datetime  # aware
    all_day: bool
    day: date  # local calendar date of the exam
    start_minute: int | None  # local minute of day; None for all-day events

    def days_until(self, today: date) -> int:
        return (self.day - today).days


@dataclass(frozen=True, slots=True)
class ExamNudge:
    key: str
    score: int
    eyebrow: str
    title: str
    detail: str
    event_id: str
    days_until: int


def _short(title: str) -> str:
    return title if len(title) <= MAX_TITLE else title[: MAX_TITLE - 1].rstrip() + "…"


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def exam_nudge(
    exams: list[ExamEvent] | tuple[ExamEvent, ...], today: date, local_minute: int, tone: str,
) -> ExamNudge | None:
    live = [
        e for e in exams
        if 0 <= e.days_until(today) <= WINDOW_DAYS
        and not (e.days_until(today) == 0 and e.start_minute is not None and local_minute >= e.start_minute)
    ]
    if not live:
        return None
    live.sort(key=lambda e: (e.day, e.start_minute if e.start_minute is not None else -1, e.event_id))
    nearest = live[0]
    days = nearest.days_until(today)
    same_day = sum(1 for e in live if e.day == nearest.day) - 1
    coach = tone == "coach"
    title = _short(nearest.title)

    if days == 0:
        score, eyebrow, head = SCORE_TODAY, "Exam today", f"{title} today"
        when = f"Starts {_hhmm(nearest.start_minute)}. " if nearest.start_minute is not None else ""
        detail = (
            f"{when}You've done the work. Eat, breathe, and head out early."
            if coach
            else f"{when}Eat something, check what to bring, leave early."
        )
    elif days == 1:
        score, eyebrow, head = SCORE_TOMORROW, "Exam tomorrow", f"{title} is tomorrow"
        detail = (
            "Keep tonight light: a short review, pack your bag, and get to bed on time."
            if coach
            else "Light review only. Pack your bag. Sleep on time."
        )
    elif days <= NEAR_DAYS:
        score, eyebrow, head = SCORE_NEAR, f"Exam in {days} days", f"{title} in {days} days"
        detail = (
            "Pick the topic that worries you most and give it one focused block today."
            if coach
            else "Pick the weakest topic. One focused block today."
        )
    else:
        score, eyebrow, head = SCORE_FAR, f"Exam in {days} days", f"{title} in {days} days"
        detail = (
            "No panic yet. One short block on the shakiest topic keeps it moving."
            if coach
            else "One short block on the weakest topic keeps it moving."
        )

    if same_day > 0:
        detail += f" (+{same_day} more that day)"

    return ExamNudge(
        key=f"exam:{nearest.event_id}:{days}",
        score=score,
        eyebrow=eyebrow,
        title=head,
        detail=detail,
        event_id=nearest.event_id,
        days_until=days,
    )
