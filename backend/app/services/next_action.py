"""
The ONE thing the Now screen leads with. PURE: everything arrives as arguments, so every rule is testable.

Candidates are scored, not hard-ordered, so the rhythm can move things: "close today" only takes over near the
person's own check-in time, and a risk window their own urge logs revealed outranks an ordinary habit.

  100  floor        after a slip, the first habit not yet done at its floor version
   92  deadline     the highest-importance open task
   88  guard        a risk window is open or about to open (shows the person's own if-then plan when they have one)
   85  close        past the usual check-in time and the day isn't closed
   60  habit        a scheduled habit with nothing logged and nothing to propose
   55  task         the next due task
   30  checkin      daytime nudge that the check-in exists (never before "close" would be right)

"Not now" works by key: skipped candidates drop out and the next one rises. Nothing left -> an honest "all clear".
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.companion_voice import card_voice, why_line
from app.services.rhythm import DAY, BUCKET, Rhythm, RiskWindow, evening_at, window_near

SCORE_FLOOR, SCORE_DEADLINE, SCORE_GUARD, SCORE_CLOSE, SCORE_HABIT, SCORE_TASK, SCORE_CHECKIN = (
    100, 92, 88, 85, 60, 55, 30,
)
CONCRETE_KINDS = frozenset({"floor", "deadline", "habit", "task"})   # worth a morning push


@dataclass(frozen=True, slots=True)
class HabitFacts:
    habit_id: str
    name: str
    status: str | None
    is_default: bool
    is_scheduled: bool
    floor_text: str | None = None


@dataclass(frozen=True, slots=True)
class TaskFacts:
    task_id: str
    title: str
    importance: int
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class Target:
    type: str                       # habit | task | checkin | urge | none
    habit_id: str | None = None
    status: str | None = None       # done | floor (habit targets)
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class NextAction:
    key: str
    kind: str                       # floor | deadline | guard | close | habit | task | checkin | clear
    eyebrow: str
    title: str
    detail: str | None
    cta: str | None
    target: Target
    why: str | None
    voice: str | None


@dataclass(frozen=True, slots=True)
class NextInput:
    habits: tuple[HabitFacts, ...]
    tasks: tuple[TaskFacts, ...]
    confirmed: bool
    bounce: bool
    local_minute: int
    rhythm: Rhythm
    tone: str
    plan: str | None                # the person's own urge if-then action, when they wrote one
    seed: int                       # day number: keeps a line stable within a day
    skipped: frozenset[str] = frozenset()


def _inside(window: RiskWindow, minute: int) -> bool:
    length = (window.end - window.start) % DAY or BUCKET
    return (minute - window.start) % DAY < length


def _task(t: TaskFacts, kind: str, inp: NextInput) -> NextAction:
    return NextAction(
        key=f"task:{t.task_id}", kind=kind, eyebrow="Deadline" if kind == "deadline" else "Next up",
        title=t.title, detail=t.detail, cta="Done", target=Target("task", task_id=t.task_id),
        why=why_line(kind, inp.tone), voice=card_voice(kind, inp.tone, inp.seed),
    )


def _floor(h: HabitFacts, inp: NextInput) -> NextAction:
    return NextAction(
        key=f"floor:{h.habit_id}", kind="floor", eyebrow="Floor day", title=h.name,
        detail=f"Floor: {h.floor_text}" if h.floor_text else "Keep it small today. The floor version counts.",
        cta="Floor done", target=Target("habit", habit_id=h.habit_id, status="floor"),
        why=why_line("floor", inp.tone), voice=card_voice("floor", inp.tone, inp.seed),
    )


def _guard(w: RiskWindow, inp: NextInput) -> NextAction:
    inside = _inside(w, inp.local_minute)
    return NextAction(
        key=f"guard:{w.start}", kind="guard", eyebrow="Heads up",
        title="You're in your usual tough hour" if inside else "Your usual tough hour is near",
        detail=inp.plan or "Take two minutes to decide what you'll do first.",
        cta="Log an urge", target=Target("urge"),
        why=why_line("guard", inp.tone, (w.start, w.end)), voice=card_voice("guard", inp.tone, inp.seed),
    )


def _plain(kind: str, eyebrow: str, title: str, detail: str | None, cta: str, key: str, inp: NextInput) -> NextAction:
    return NextAction(
        key=key, kind=kind, eyebrow=eyebrow, title=title, detail=detail, cta=cta, target=Target("checkin"),
        why=why_line(kind, inp.tone), voice=card_voice(kind, inp.tone, inp.seed),
    )


def clear_action(inp: NextInput) -> NextAction:
    return NextAction(
        key="clear", kind="clear", eyebrow="All clear", title="Locked in." if inp.confirmed else "Nothing open.",
        detail=card_voice("clear", inp.tone, inp.seed), cta=None, target=Target("none"), why=None, voice=None,
    )


def candidates(inp: NextInput) -> list[tuple[int, NextAction]]:
    out: list[tuple[int, NextAction]] = []
    habits = [h for h in inp.habits if h.is_scheduled]
    deadline = next((t for t in inp.tasks if t.importance == 3), None)

    if inp.bounce:
        # After a slip the proposals are already lowered to the floor; lead with the first not yet done.
        h = next((h for h in habits if h.status is None or (h.is_default and h.status == "floor")), None)
        if h is not None:
            out.append((SCORE_FLOOR, _floor(h, inp)))
    if deadline is not None:
        out.append((SCORE_DEADLINE, _task(deadline, "deadline", inp)))
    window = window_near(inp.rhythm, inp.local_minute)
    if window is not None:
        out.append((SCORE_GUARD, _guard(window, inp)))
    if not inp.confirmed:
        if inp.local_minute >= evening_at(inp.rhythm):
            out.append((SCORE_CLOSE, _plain(
                "close", "End of day", "Close today", card_voice("close", inp.tone, inp.seed), "Lock it in", "close", inp,
            )))
        else:
            out.append((SCORE_CHECKIN, _plain(
                "checkin", "Check-in", "Today's check-in", card_voice("checkin", inp.tone, inp.seed), "Open",
                "checkin", inp,
            )))
    if not inp.bounce:
        open_habit = next((h for h in habits if h.status is None), None)
        if open_habit is not None:
            out.append((SCORE_HABIT, NextAction(
                key=f"habit:{open_habit.habit_id}", kind="habit", eyebrow="Next habit", title=open_habit.name,
                detail=f"Floor: {open_habit.floor_text}" if open_habit.floor_text else None, cta="Done",
                target=Target("habit", habit_id=open_habit.habit_id, status="done"),
                why=why_line("habit", inp.tone), voice=card_voice("habit", inp.tone, inp.seed),
            )))
    other = next((t for t in inp.tasks if deadline is None or t.task_id != deadline.task_id), None)
    if other is not None:
        out.append((SCORE_TASK, _task(other, "task", inp)))
    out.sort(key=lambda pair: -pair[0])   # stable: equal scores keep insertion order
    return out


def pick_next(inp: NextInput) -> NextAction:
    for _, action in candidates(inp):
        if action.key not in inp.skipped:
            return action
    return clear_action(inp)
