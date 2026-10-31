"""
Tasks: AI capture, manual create/edit, complete (cadence-aware), snooze, and the "focus" view.

Order of business in capture() (the order IS the safety design, same as chat):
  1. crisis screen on the raw text -> support payload, NOTHING stored, no model call
  2. the model extracts structured tasks; anything it returns is validated in code (task_parser.py)
  3. model down / over budget / junk -> the person's own words are kept as plain tasks (mode="fallback")
Duplicates of an existing open task (same title, ignoring case) are skipped, never doubled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.dates import Clock, utc_now
from app.domain import NotificationPrefs, Task
from app.exceptions import NotFoundError, ValidationError
from app.guard import freetext
from app.repositories.notification_repository import NotificationRepository
from app.repositories.task_repository import TaskRepository
from app.safety import is_crisis, support_payload
from app.services.goals_service import clean_text
from app.services.llm import LLMClient
from app.services.narration import sanitize_user_text
from app.services.nudge_policy import classify, rank_key, trigger_at
from app.services.profile_service import ProfileService
from app.services.task_parser import (
    MAX_CAPTURE_CHARS, MAX_NOTES, MAX_TITLE, ParsedTask, fallback_parse, parse_capture,
)
from app.services.task_time import END_OF_DAY, at_local, format_local, next_occurrence, parse_local, zone

MAX_OPEN_TASKS = 200
MIN_SNOOZE_MINUTES = 5
MAX_SNOOZE_MINUTES = 7 * 24 * 60
FOCUS_NOW_LIMIT = 5
FOCUS_SECTION_LIMIT = 5


@dataclass(slots=True)
class TaskView:
    task: Task
    state: str          # backlog | upcoming | due | stale | snoozed | done | dropped
    due_local: str | None
    remind_local: str | None


@dataclass(slots=True)
class CaptureResult:
    mode: str           # parsed | fallback | support
    tasks: list[TaskView] = field(default_factory=list)
    skipped_duplicates: int = 0
    support: dict | None = None


@dataclass(slots=True)
class Focus:
    now: list[TaskView]
    small: list[TaskView]
    later_today: list[TaskView]
    stale: list[TaskView]
    hidden_now: int
    backlog_count: int


class TasksService:
    def __init__(
        self, repo: TaskRepository, notif: NotificationRepository, profiles: ProfileService,
        llm: LLMClient, clock: Clock = utc_now,
    ):
        self._repo, self._notif, self._profiles, self._llm, self._clock = repo, notif, profiles, llm, clock

    # ---------------------------------------------------------------- context
    async def _ctx(self, user_id: UUID) -> tuple[datetime, ZoneInfo, str, NotificationPrefs]:
        profile = await self._profiles.get(user_id)
        prefs = await self._notif.get_prefs(user_id)
        return self._clock(), zone(profile.timezone), profile.timezone, prefs

    @staticmethod
    def _view(task: Task, now: datetime, prefs: NotificationPrefs, tz: ZoneInfo) -> TaskView:
        return TaskView(
            task=task, state=classify(task, now, prefs, tz),
            due_local=format_local(task.due_at, task.due_has_time, tz),
            remind_local=format_local(task.remind_at, True, tz),
        )

    @staticmethod
    def _first_due(now: datetime, tz: ZoneInfo, prefs: NotificationPrefs) -> datetime:
        """A new cadence task with no stated start: today if the day's nudge hour hasn't passed, else tomorrow."""
        local = now.astimezone(tz)
        day = local.date() if local.hour < prefs.nudge_hour else local.date() + timedelta(days=1)
        return at_local(day, END_OF_DAY, tz)

    @staticmethod
    def _mark_seen_if_triggered(task: Task, now: datetime, prefs: NotificationPrefs, tz: ZoneInfo) -> None:
        """Making a task that is already due counts as having seen it: don't push about it the same minute."""
        trig = trigger_at(task, prefs, tz)
        if trig is not None and trig <= now:
            task.last_nudged_at = now

    # ---------------------------------------------------------------- capture
    async def capture(self, user_id: UUID, text: str) -> CaptureResult:
        raw = text or ""
        now, tz, tz_name, prefs = await self._ctx(user_id)

        if is_crisis(raw):
            return CaptureResult(mode="support", support=support_payload(tz_name))

        clean = sanitize_user_text(raw, MAX_CAPTURE_CHARS)
        if not clean.strip():
            raise ValidationError("Write something to capture.")

        open_tasks = await self._repo.list(user_id, "open")
        room = MAX_OPEN_TASKS - len(open_tasks)
        if room <= 0:
            raise ValidationError(f"You already have {MAX_OPEN_TASKS} open tasks. Finish or drop some first.")

        # Text that reads like an instruction to the model never reaches it: the deterministic parser takes it instead.
        parsed = None if await freetext.screen(user_id, raw, source="capture") else await parse_capture(self._llm, clean, now, tz, tz_name)
        mode = "parsed"
        if parsed is None:
            parsed, mode = fallback_parse(clean), "fallback"
        return await self._create_parsed(user_id, parsed, clean, mode, now, tz, prefs, open_tasks)

    async def capture_parsed(self, user_id: UUID, parsed: list[ParsedTask], source_text: str) -> CaptureResult:
        """Create tasks that were ALREADY extracted and validated elsewhere (the chat agent), no second model call.
        Same duplicate / limit / cadence rules as capture()."""
        now, tz, _, prefs = await self._ctx(user_id)
        open_tasks = await self._repo.list(user_id, "open")
        if MAX_OPEN_TASKS - len(open_tasks) <= 0:
            raise ValidationError(f"You already have {MAX_OPEN_TASKS} open tasks. Finish or drop some first.")
        clean = sanitize_user_text(source_text or "", MAX_CAPTURE_CHARS)
        return await self._create_parsed(user_id, parsed, clean, "parsed", now, tz, prefs, open_tasks)

    async def _create_parsed(
        self, user_id: UUID, parsed: list[ParsedTask], clean: str, mode: str, now: datetime, tz: ZoneInfo,
        prefs: NotificationPrefs, open_tasks: list[Task],
    ) -> CaptureResult:
        room = MAX_OPEN_TASKS - len(open_tasks)
        existing = {t.title.casefold() for t in open_tasks}
        created: list[TaskView] = []
        skipped = 0
        for p in parsed:
            if p.title.casefold() in existing:
                skipped += 1
                continue
            if len(created) >= room:
                break
            due_at, has_time = p.due_at, p.due_has_time
            if p.repeat_days and due_at is None and p.remind_at is None:
                due_at, has_time = self._first_due(now, tz, prefs), False
            task = Task(
                id=uuid4(), user_id=user_id, title=p.title, created_at=now, notes=p.notes,
                source_text=clean, importance=p.importance, due_at=due_at, due_has_time=has_time,
                remind_at=p.remind_at, repeat_days=p.repeat_days, ai_parsed=(mode == "parsed"),
            )
            self._mark_seen_if_triggered(task, now, prefs, tz)
            await self._repo.create(task)
            existing.add(p.title.casefold())
            created.append(self._view(task, now, prefs, tz))
        return CaptureResult(mode=mode, tasks=created, skipped_duplicates=skipped)

    # ---------------------------------------------------------------- manual create / read
    async def create(
        self, user_id: UUID, title: str, notes: str | None, importance: int, due: str | None,
        remind: str | None, repeat_days: int | None,
    ) -> TaskView:
        now, tz, _, prefs = await self._ctx(user_id)
        if await self._repo.count_open(user_id) >= MAX_OPEN_TASKS:
            raise ValidationError(f"You already have {MAX_OPEN_TASKS} open tasks. Finish or drop some first.")
        task = Task(
            id=uuid4(), user_id=user_id, title=clean_text(title, "Title", MAX_TITLE), created_at=now,
            notes=self._clean_notes(notes), importance=self._check_importance(importance),
            repeat_days=self._check_repeat(repeat_days),
        )
        if due:
            task.due_at, task.due_has_time = parse_local(due, tz)
        if remind:
            task.remind_at = self._check_remind(remind, now, tz)
        if task.repeat_days and task.due_at is None and task.remind_at is None:
            task.due_at, task.due_has_time = self._first_due(now, tz, prefs), False
        self._mark_seen_if_triggered(task, now, prefs, tz)
        await self._repo.create(task)
        return self._view(task, now, prefs, tz)

    async def list(self, user_id: UUID, status: str | None = None) -> list[TaskView]:
        if status is not None and status not in ("open", "done", "dropped"):
            raise ValidationError("status must be open, done or dropped.")
        now, tz, _, prefs = await self._ctx(user_id)
        tasks = await self._repo.list(user_id, status)
        return [self._view(t, now, prefs, tz) for t in tasks]

    # ---------------------------------------------------------------- update
    async def update(self, user_id: UUID, task_id: UUID, changes: dict) -> TaskView:
        now, tz, _, prefs = await self._ctx(user_id)
        task = await self._get(user_id, task_id)
        reschedule = False

        if "title" in changes and changes["title"] is not None:
            task.title = clean_text(changes["title"], "Title", MAX_TITLE)
        if "notes" in changes:
            task.notes = self._clean_notes(changes["notes"])
        if "importance" in changes and changes["importance"] is not None:
            task.importance = self._check_importance(changes["importance"])
        if "repeat_days" in changes:
            task.repeat_days = self._check_repeat(changes["repeat_days"])
            reschedule = True
        if "due" in changes:
            if changes["due"]:
                task.due_at, task.due_has_time = parse_local(changes["due"], tz)
            else:
                task.due_at, task.due_has_time = None, True
            reschedule = True
        if "remind" in changes:
            task.remind_at = self._check_remind(changes["remind"], now, tz) if changes["remind"] else None
            reschedule = True
        status = changes.get("status")
        if status == "dropped":
            task.status = "dropped"
        elif status == "open" and task.status != "open":
            task.status, task.completed_at, reschedule = "open", None, True
        if task.repeat_days and task.due_at is None and task.remind_at is None and task.status == "open":
            task.due_at, task.due_has_time = self._first_due(now, tz, prefs), False

        if reschedule:  # a new time is a fresh start: no stale backoff, no leftover snooze
            task.nudge_count, task.last_nudged_at, task.snoozed_until = 0, None, None
            self._mark_seen_if_triggered(task, now, prefs, tz)
        saved = await self._repo.save(task, now)
        if saved is None:
            raise NotFoundError(f"No task {task_id} for this user.")
        return self._view(saved, now, prefs, tz)

    async def complete(self, user_id: UUID, task_id: UUID) -> TaskView:
        now, tz, _, prefs = await self._ctx(user_id)
        task = await self._get(user_id, task_id)
        if task.status != "open":
            return self._view(task, now, prefs, tz)  # idempotent: a double-tap changes nothing
        task.last_done_at = now
        task.done_count += 1
        task.nudge_count, task.last_nudged_at, task.snoozed_until = 0, None, None
        if task.repeat_days:
            task.due_at, task.due_has_time, task.remind_at = next_occurrence(
                done_at=now, repeat_days=task.repeat_days, due_at=task.due_at,
                due_has_time=task.due_has_time, remind_at=task.remind_at, tz=tz,
            )
        else:
            task.status, task.completed_at = "done", now
        saved = await self._repo.save(task, now)
        if saved is None:
            raise NotFoundError(f"No task {task_id} for this user.")
        return self._view(saved, now, prefs, tz)

    async def snooze(self, user_id: UUID, task_id: UUID, minutes: int) -> TaskView:
        if not MIN_SNOOZE_MINUTES <= minutes <= MAX_SNOOZE_MINUTES:
            raise ValidationError(f"Snooze must be {MIN_SNOOZE_MINUTES} minutes to 7 days.")
        now, tz, _, prefs = await self._ctx(user_id)
        task = await self._get(user_id, task_id)
        if task.status != "open":
            raise ValidationError("Only open tasks can be snoozed.")
        task.snoozed_until = now + timedelta(minutes=minutes)
        saved = await self._repo.save(task, now)
        if saved is None:
            raise NotFoundError(f"No task {task_id} for this user.")
        return self._view(saved, now, prefs, tz)

    async def delete(self, user_id: UUID, task_id: UUID) -> None:
        if not await self._repo.delete(user_id, task_id):
            raise NotFoundError(f"No task {task_id} for this user.")

    # ---------------------------------------------------------------- undo support (chat agent)
    RESTORABLE = (
        "status", "due_at", "due_has_time", "remind_at", "snoozed_until", "completed_at", "last_done_at",
        "done_count", "nudge_count", "last_nudged_at",
    )

    @staticmethod
    def snapshot(task: Task) -> dict:
        """JSON-safe copy of the fields an agent action can change, for a one-tap Undo."""
        out: dict = {}
        for key in TasksService.RESTORABLE:
            value = getattr(task, key)
            out[key] = value.isoformat() if isinstance(value, datetime) else value
        return out

    async def get(self, user_id: UUID, task_id: UUID) -> Task:
        return await self._get(user_id, task_id)

    async def restore(self, user_id: UUID, task_id: UUID, fields: dict) -> TaskView:
        """Put back what snapshot() recorded. Only RESTORABLE fields, only the right types; anything else is ignored."""
        now, tz, _, prefs = await self._ctx(user_id)
        task = await self._get(user_id, task_id)
        for key in self.RESTORABLE:
            if key not in fields:
                continue
            value = fields[key]
            if key in ("due_at", "remind_at", "snoozed_until", "completed_at", "last_done_at", "last_nudged_at"):
                try:
                    value = datetime.fromisoformat(value) if value else None
                except (TypeError, ValueError) as exc:
                    raise ValidationError(f"Bad value for {key}.") from exc
                if value is not None and value.tzinfo is None:
                    raise ValidationError(f"Bad value for {key}.")
            elif key == "status":
                if value not in ("open", "done", "dropped"):
                    raise ValidationError("Bad status.")
            elif key == "due_has_time":
                value = bool(value)
            else:  # counters
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValidationError(f"Bad value for {key}.")
            setattr(task, key, value)
        saved = await self._repo.save(task, now)
        if saved is None:
            raise NotFoundError(f"No task {task_id} for this user.")
        return self._view(saved, now, prefs, tz)

    # ---------------------------------------------------------------- focus
    async def focus(self, user_id: UUID) -> Focus:
        now, tz, _, prefs = await self._ctx(user_id)
        views = [self._view(t, now, prefs, tz) for t in await self._repo.list(user_id, "open")]
        today = now.astimezone(tz).date()

        def ranked(items: list[TaskView]) -> list[TaskView]:
            return sorted(items, key=lambda v: rank_key(v.task, prefs, tz))

        due = [v for v in views if v.state == "due"]
        now_all = ranked([v for v in due if v.task.importance >= 2])
        small = ranked([v for v in due if v.task.importance == 1])
        later = ranked([
            v for v in views
            if v.state == "upcoming"
            and (trig := trigger_at(v.task, prefs, tz)) is not None and trig.astimezone(tz).date() == today
        ])
        stale = ranked([v for v in views if v.state == "stale"])
        return Focus(
            now=now_all[:FOCUS_NOW_LIMIT], small=small[:FOCUS_SECTION_LIMIT], later_today=later[:FOCUS_SECTION_LIMIT],
            stale=stale[:FOCUS_SECTION_LIMIT], hidden_now=max(0, len(now_all) - FOCUS_NOW_LIMIT),
            backlog_count=sum(1 for v in views if v.state == "backlog"),
        )

    # ---------------------------------------------------------------- helpers
    async def _get(self, user_id: UUID, task_id: UUID) -> Task:
        task = await self._repo.get(user_id, task_id)
        if task is None:
            raise NotFoundError(f"No task {task_id} for this user.")
        return task

    @staticmethod
    def _clean_notes(notes: str | None) -> str | None:
        if notes is None or not notes.strip():
            return None
        return clean_text(notes, "Notes", MAX_NOTES)

    @staticmethod
    def _check_importance(value: int) -> int:
        if value not in (1, 2, 3):
            raise ValidationError("importance must be 1 (small), 2 (normal) or 3 (real deadline).")
        return value

    @staticmethod
    def _check_repeat(value: int | None) -> int | None:
        if value is None:
            return None
        if not 1 <= value <= 365:
            raise ValidationError("repeat_days must be 1-365.")
        return value

    @staticmethod
    def _check_remind(value: str, now: datetime, tz: ZoneInfo) -> datetime:
        when, has_time = parse_local(value, tz)
        if not has_time:
            raise ValidationError("A reminder needs a clock time (YYYY-MM-DDTHH:MM).")
        if when <= now:
            raise ValidationError("A reminder has to be in the future.")
        return when