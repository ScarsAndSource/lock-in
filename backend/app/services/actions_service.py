"""
Push actions: what happens when someone taps a button on a notification.

Two entry points, ONE implementation:
  run_token()   the service worker POSTs the signed token from the push payload. No session. The token is verified,
                its single-use ledger row is claimed, and the action runs -- all in ONE transaction, so if the action
                fails the claim rolls back and the button can be tapped again.
  run_in_app()  the app (signed in) runs the same action after a deep link such as /?a=checkin. This is what iOS web
                push needs, because iOS notifications carry no action buttons.

Every write goes through the services the app already uses (TasksService, CheckinsService, HabitsService), so
validation, rest-day / pause rules and RLS are exactly what they are everywhere else. A token can only trigger the
actions it was minted with. The effect is deliberately small and reversible from the app: lock the day, log a floor
version, snooze an hour, mark done.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.dates import Clock, utc_now
from app.domain import HabitStatus
from app.exceptions import NotFoundError, ValidationError
from app.repositories.companion_repository import CompanionRepository
from app.services import push_actions
from app.services.checkins_service import CheckinsService
from app.services.habits_service import HabitsService
from app.services.profile_service import ProfileService
from app.services.tasks_service import TasksService

SNOOZE_MINUTES = 60
NOOP_ACTIONS = {"ok": "Nice. Go for it.", "later": "Okay, not now.", "open": "Opened.", "view": "Opened.", "start": "Let's go."}

# kind -> actions that are real writes (anything in NOOP_ACTIONS is accepted for every kind)
KIND_ACTIONS: dict[str, tuple[str, ...]] = {
    "task": ("done", "snooze"),
    "crew_sunday": (), "crew_boost": ("cheer",), "crew_buddy": ("send",),   # tap targets for the crew pushes
    "checkin": ("lock", "rough"),
    "habit": ("done", "floor", "skip"),
    "comeback": ("floor",),                    # the one real write: log today's floor version of the offered habit
    "risk": (), "winddown": (), "study": (), "insight": (), "morning": (),   # morning's "Start" is a no-op that opens the app
}


@dataclass(slots=True)
class ActionResult:
    status: str        # done | already | failed
    message: str
    kind: str = ""
    action: str = ""


class ActionsService:
    def __init__(
        self, *, ledger: CompanionRepository | None, tasks: TasksService, checkins: CheckinsService,
        habits: HabitsService, profiles: ProfileService, secret: bytes, clock: Clock = utc_now, crew=None,
    ):
        self._ledger, self._tasks, self._checkins, self._habits = ledger, tasks, checkins, habits
        self._profiles, self._secret, self._clock = profiles, secret, clock
        self._crew = crew   # CrewService | None; only the push-token path wires it

    # ------------------------------------------------------------------ entry points
    async def run_token(self, token: str, action: str) -> ActionResult:
        now = self._clock()
        claims = push_actions.verify(self._secret, token, now)       # ActionTokenError -> router maps to 401 / 410
        if action not in ("open", "dismiss") and action not in claims.allowed:
            raise ValidationError("That action isn't part of this notification.")
        if self._ledger is None:
            raise ValidationError("Actions aren't available.")
        if action == "dismiss":
            # Swiped away. Not an action: it claims nothing and changes nothing the person sees. It only tells the
            # anti-nag backoff "ignored" right now, and only if nobody tapped the push first.
            await self._ledger.mark_dismissed(claims.user_id, claims.push_id, now)
            return ActionResult("done", "Dismissed.", claims.kind, action)
        claimed = await self._ledger.mark_acted(claims.user_id, claims.push_id, action, now)
        if claimed is None:
            return ActionResult("already", "Already handled.", claims.kind, action)
        return await self._perform(claims.user_id, claims.kind, action, claims.args)

    async def run_in_app(self, user_id: UUID, kind: str, action: str, args: dict) -> ActionResult:
        if kind not in KIND_ACTIONS:
            raise ValidationError(f"Unknown action kind {kind!r}.")
        if action not in KIND_ACTIONS[kind] and action not in NOOP_ACTIONS:
            raise ValidationError(f"{kind} has no action {action!r}.")
        return await self._perform(user_id, kind, action, {str(k): str(v) for k, v in args.items()})

    # ------------------------------------------------------------------ the writes
    async def _perform(self, user_id: UUID, kind: str, action: str, args: dict) -> ActionResult:
        if action in NOOP_ACTIONS:
            return ActionResult("done", NOOP_ACTIONS[action], kind, action)
        try:
            if kind == "task":
                msg = await self._task(user_id, action, args)
            elif kind == "checkin":
                msg = await self._checkin(user_id, action, args)
            elif kind in ("crew_boost", "crew_buddy"):
                msg = await self._crew_action(user_id, kind, action, args)
            elif kind in ("habit", "comeback"):
                msg = await self._habit(user_id, action, args)
            else:
                raise ValidationError(f"{kind} has no action {action!r}.")
        except (NotFoundError, ValidationError) as exc:
            return ActionResult("failed", str(exc), kind, action)
        return ActionResult("done", msg, kind, action)

    async def _crew_action(self, user_id: UUID, kind: str, action: str, args: dict) -> str:
        from app.exceptions import ConflictError

        if self._crew is None:
            raise ValidationError("That isn't available here. Open the app.")
        try:
            if kind == "crew_boost" and action == "cheer":
                await self._crew.send_cheer(self._uuid(args.get("crew"), "crew"), str(args.get("to", "")), "rooting")
                return "Cheer sent."
            if kind == "crew_buddy" and action == "send":
                await self._crew.buddy_send(user_id, self._uuid(args.get("deal"), "deal"))
                return "Sent."
        except ConflictError as exc:
            raise ValidationError(str(exc)) from exc
        raise ValidationError(f"{kind} has no action {action!r}.")

    async def _task(self, user_id: UUID, action: str, args: dict) -> str:
        task_id = self._uuid(args.get("task_id"), "task")
        if action == "done":
            await self._tasks.complete(user_id, task_id)
            return "Marked done."
        if action == "snooze":
            await self._tasks.snooze(user_id, task_id, SNOOZE_MINUTES)
            return "Snoozed for an hour."
        raise ValidationError(f"task has no action {action!r}.")

    async def _day(self, user_id: UUID, args: dict) -> date:
        """Only today (or yesterday, for a late tap) can be closed from a notification."""
        today = await self._profiles.today(user_id)
        try:
            day = date.fromisoformat(args.get("date", ""))
        except ValueError:
            day = today
        if not today - timedelta(days=1) <= day <= today:
            raise ValidationError("That day is too old to close from a notification. Open the app.")
        return day

    async def _checkin(self, user_id: UUID, action: str, args: dict) -> str:
        day = await self._day(user_id, args)
        if action == "lock":
            await self._checkins.confirm(user_id, day, overrides={}, journal_text=None)
            return "Locked. Day closed."
        if action == "rough":
            view = await self._checkins.get_view(user_id, day)
            overrides = {
                e.habit_id: (HabitStatus.FLOOR, None)
                for e in view.entries if e.is_scheduled and (e.status is None or e.is_default)
            }
            # Rough day = the floor version counts; sleep and screen time are NOT guessed for a day like this.
            await self._checkins.confirm(
                user_id, day, overrides=overrides, journal_text=None,
                accept_sleep_default=False, accept_screen_time_default=False,
            )
            return "Rough day noted. The floor version counts."
        raise ValidationError(f"checkin has no action {action!r}.")

    async def _habit(self, user_id: UUID, action: str, args: dict) -> str:
        habit_id = self._uuid(args.get("habit_id"), "habit")
        day = await self._day(user_id, args)
        status = {"done": HabitStatus.DONE, "floor": HabitStatus.FLOOR, "skip": HabitStatus.SKIPPED}.get(action)
        if status is None:
            raise ValidationError(f"habit has no action {action!r}.")
        await self._habits.log_habit(user_id, habit_id, day, status, None)
        return {"done": "Logged. Nice.", "floor": "Floor version logged. It counts.", "skip": "Skipped. Fine."}[action]

    @staticmethod
    def _uuid(value: str | None, what: str) -> UUID:
        try:
            return UUID(value or "")
        except ValueError as exc:
            raise ValidationError(f"Missing {what}.") from exc
