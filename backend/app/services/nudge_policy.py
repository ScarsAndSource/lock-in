"""
Nudge policy. PURE: no DB, no clock, no network -- everything comes in as arguments, so every rule is testable.

Design (SPEC section 6 reminder principle + section 8 "no escalating guilt notifications"):
  * A task is nudge-eligible only once its TRIGGER passes: the exact reminder if one was asked for, else the due
    time, else (a bare date) the person's nudge hour on that day. A task with no trigger is a backlog item and is
    never pushed.
  * Nudges BACK OFF, they never escalate: the gap before the next one doubles each time, and after a small
    importance-based number of nudges the app stops pushing and the task moves to "stale" -- the person decides
    (done / reschedule / drop) in the app. No endless nagging.
  * Small things (importance 1: the laundry / call-a-relative kind) never ping individually. They ride in ONE
    digest at the person's nudge hour. Only an exact reminder the person asked for fires on its own.
  * Quiet hours always win. A global pause silences everything except a reminder the person set for an exact time
    (its first fire only).
  * Copy is plain and carries no guilt. It only ever repeats the person's own title.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.domain import NotificationPrefs, Task
from app.services.task_time import at_local, clock_label

# gap before the NEXT nudge = base[importance] * 2**nudges_already_sent, capped
BASE_GAP_HOURS = {1: 24, 2: 6, 3: 2}
MAX_GAP_HOURS = 72
MAX_NUDGES = {1: 2, 2: 3, 3: 5}
MAX_SINGLES_PER_RUN = 3
MAX_DIGEST_TITLES = 3
TITLE_PUSH_CHARS = 80


@dataclass(frozen=True, slots=True)
class PushMessage:
    task_ids: tuple[UUID, ...]
    title: str
    body: str
    tag: str          # same tag replaces the earlier notification instead of stacking
    digest: bool
    # --- actionable pushes (companion layer). All defaulted, so plain task pushes keep working unchanged.
    kind: str = "task"                      # task | task-digest | checkin | habit | risk | winddown | study | morning | comeback
    key: str | None = None                  # unique moment id; a message with a key is tracked in the push ledger
    args: dict = field(default_factory=dict)  # str -> str, travels inside the signed action token
    actions: tuple[tuple[str, str], ...] = ()  # (action id, button label); max 2 so every platform shows them
    url: str = "/"                          # where tapping the body goes (deep link, handled by the app)
    priority: int = 50                      # higher goes first when the daily budget is tight
    ttl_minutes: int = 360                  # how long the buttons keep working


def min_gap(task: Task) -> timedelta:
    base = BASE_GAP_HOURS.get(task.importance, BASE_GAP_HOURS[2])
    return timedelta(hours=min(base * (2 ** max(0, task.nudge_count)), MAX_GAP_HOURS))


def trigger_at(task: Task, prefs: NotificationPrefs, tz: ZoneInfo) -> datetime | None:
    if task.remind_at is not None:
        return task.remind_at
    if task.due_at is None:
        return None
    if task.due_has_time:
        return task.due_at
    return at_local(task.due_at.astimezone(tz).date(), time(prefs.nudge_hour), tz)


def classify(task: Task, now: datetime, prefs: NotificationPrefs, tz: ZoneInfo) -> str:
    """done | dropped | snoozed | backlog | upcoming | due | stale"""
    if task.status != "open":
        return task.status
    if task.snoozed_until is not None and task.snoozed_until > now:
        return "snoozed"
    trig = trigger_at(task, prefs, tz)
    if trig is None:
        return "backlog"
    if trig > now:
        return "upcoming"
    if task.nudge_count >= MAX_NUDGES.get(task.importance, 3):
        # Nudged out. It only goes stale after a full backoff period passes with no action, so a task that
        # just got its last ping still shows as due.
        if task.last_nudged_at is not None and now - task.last_nudged_at >= min_gap(task):
            return "stale"
    return "due"


def in_quiet_hours(at: time, start: time, end: time) -> bool:
    """start == end means no quiet hours. Handles windows that wrap midnight (22:00-08:00)."""
    if start == end:
        return False
    if start < end:
        return start <= at < end
    return at >= start or at < end


def rank_key(task: Task, prefs: NotificationPrefs, tz: ZoneInfo):
    trig = trigger_at(task, prefs, tz)
    return (-task.importance, trig or datetime.max.replace(tzinfo=tz), task.created_at)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def reason(task: Task, now: datetime, tz: ZoneInfo) -> str:
    """One calm line. Never guilt, never urgency theatre."""
    if task.nudge_count > 0:
        return "Still open. Mark it done, snooze it or drop it."
    due = task.due_at
    if due is None:
        return "Reminder"
    if task.remind_at is not None and task.remind_at <= now < due:
        when = "today" if not task.due_has_time else clock_label(due, tz)
        return f"Reminder · due {when}"
    if due > now:
        return "Due today" if not task.due_has_time else f"Due {clock_label(due, tz)}"
    if task.due_has_time and now - due <= timedelta(hours=1):
        return "Due now"
    return "Overdue"


def plan_pushes(
    tasks: list[Task], now: datetime, prefs: NotificationPrefs, tz: ZoneInfo, *, paused: bool = False,
) -> list[PushMessage]:
    """Which pushes to send right now, before the daily cap (the caller applies that)."""
    local_now = now.astimezone(tz)
    if not prefs.push_enabled or in_quiet_hours(local_now.time(), prefs.quiet_start, prefs.quiet_end):
        return []

    eligible: list[Task] = []
    for t in tasks:
        if classify(t, now, prefs, tz) != "due":
            continue
        if t.last_nudged_at is not None and now - t.last_nudged_at < min_gap(t):
            continue  # still backing off
        if paused and not (t.remind_at is not None and t.nudge_count == 0):
            continue
        eligible.append(t)
    if not eligible:
        return []
    eligible.sort(key=lambda t: rank_key(t, prefs, tz))

    def is_single(t: Task) -> bool:
        # importance >= 2, or an exact reminder the person asked for (first fire only).
        return t.importance >= 2 or (t.remind_at is not None and t.nudge_count == 0)

    singles = [t for t in eligible if is_single(t)]
    small = [t for t in eligible if not is_single(t)]
    overflow = singles[MAX_SINGLES_PER_RUN:]
    singles = singles[:MAX_SINGLES_PER_RUN]

    out = [
        PushMessage(
            task_ids=(t.id,), title=_shorten(t.title, TITLE_PUSH_CHARS), body=reason(t, now, tz),
            tag=f"task-{t.id}", digest=False, kind="task", key=f"task:{t.id}:{t.nudge_count}",
            args={"task_id": str(t.id)}, actions=(("done", "Done"), ("snooze", "Snooze 1h")),
            url="/?a=tasks", priority=70, ttl_minutes=24 * 60,
        )
        for t in singles
    ]

    digest_items = list(overflow)
    if small and local_now.hour >= prefs.nudge_hour:
        digest_items += small
    if digest_items:
        titles = [_shorten(t.title, 40) for t in digest_items[:MAX_DIGEST_TITLES]]
        extra = len(digest_items) - len(titles)
        body = ", ".join(titles) + (f" +{extra} more" if extra > 0 else "")
        one = len(digest_items) == 1
        noun = ("thing open" if one else "things open") if overflow else ("small thing" if one else "small things")
        label = f"{len(digest_items)} {noun}"
        out.append(PushMessage(
            task_ids=tuple(t.id for t in digest_items), title=label, body=body, tag="digest", digest=True,
            kind="task-digest", url="/?a=tasks", priority=30,
        ))
    return out
