"""
The unified daily check-in: habits + sleep + screen time in one confirm.

  - Rest days (not scheduled) propose nothing and write nothing.
  - Sleep/screen proposals are persisted only if accepted (default: accepted),
    flagged is_default=True, and never used as the basis for future proposals.
  - journal_text: None keeps the existing journal, "" clears it, text replaces it.
  - Everything runs in the request's single DB transaction (see db.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from app.dates import Clock, assert_loggable_date, utc_now
from app.domain import (
    DailyCheckin, GoalStatus, HabitLog, HabitStatus, ScreenTimeLog, ScreenTimeProposal,
    ScreenTimeSource, SleepLog, SleepProposal,
)
from app.exceptions import DataIntegrityError, NotFoundError
from app.repositories.checkin_repository import CheckinRepository
from app.repositories.goal_repository import GoalRepository
from app.repositories.habit_repository import HabitRepository
from app.repositories.screen_time_repository import ScreenTimeRepository
from app.repositories.sleep_repository import SleepRepository
from app.security import FieldEncryptor
from app.services.defaults_service import compute_habit_defaults, compute_screen_time_default, compute_sleep_default

_PROPOSAL_LOOKBACK_DAYS = 30


def _parse_time(val: str | time | None) -> time | None:
    if val is None:
        return None
    if isinstance(val, time):
        return val
    try:
        return time.fromisoformat(val)
    except ValueError:
        return None


@dataclass(slots=True)
class CheckinEntry:
    habit_id: UUID
    habit_name: str
    status: HabitStatus | None
    is_default: bool
    is_low_confidence: bool
    reason: str
    is_scheduled: bool = True


@dataclass(slots=True)
class SleepInput:
    time_to_bed: time | None
    time_woke: time | None
    self_rated_quality: int | None


@dataclass(slots=True)
class ScreenTimeInput:
    total_minutes: int
    source: ScreenTimeSource
    category_breakdown: dict | None


@dataclass(slots=True)
class CheckinView:
    entries: list[CheckinEntry]
    already_confirmed: bool
    sleep_log: SleepLog | None
    sleep_proposal: SleepProposal | None
    screen_log: ScreenTimeLog | None
    screen_proposal: ScreenTimeProposal | None


@dataclass(slots=True)
class ConfirmResult:
    entries: list[CheckinEntry]
    confirmed_at: datetime
    sleep_log: SleepLog | None
    screen_log: ScreenTimeLog | None


class CheckinsService:
    def __init__(
        self, habit_repo: HabitRepository, checkin_repo: CheckinRepository, encryptor: FieldEncryptor,
        sleep_repo: SleepRepository, screen_repo: ScreenTimeRepository, clock: Clock = utc_now,
        goals: GoalRepository | None = None,
    ):
        self._habits = habit_repo
        self._checkins = checkin_repo
        self._encryptor = encryptor
        self._sleep = sleep_repo
        self._screen = screen_repo
        self._clock = clock
        self._goals = goals

    # ------------------------------------------------------------ read
    async def get_view(self, user_id: UUID, target_date: date) -> CheckinView:
        habits = await self._habits.list_active_habits(user_id)
        existing = await self._checkins.get(user_id, target_date)
        sleep_log = await self._sleep.get_log(user_id, target_date)
        screen_log = await self._screen.get_log(user_id, target_date)
        return CheckinView(
            entries=await self._build_entries(user_id, habits, target_date),
            already_confirmed=existing is not None and existing.confirmed_at is not None,
            sleep_log=sleep_log,
            sleep_proposal=None if sleep_log else await self._sleep_proposal(user_id, target_date),
            screen_log=screen_log,
            screen_proposal=None if screen_log else await self._screen_proposal(user_id, target_date),
        )

    async def get_journal(self, user_id: UUID, target_date: date) -> str | None:
        checkin = await self._checkins.get(user_id, target_date)
        if checkin is None:
            raise NotFoundError("No check-in for this date.")
        try:
            return self._encryptor.decrypt(checkin.journal_encrypted)
        except ValueError as exc:
            raise DataIntegrityError(str(exc)) from exc

    # ------------------------------------------------------------ write
    async def confirm(
        self, user_id: UUID, target_date: date,
        overrides: dict[UUID, tuple[HabitStatus, str | None]],
        journal_text: str | None,
        sleep: SleepInput | None = None,
        screen_time: ScreenTimeInput | None = None,
        accept_sleep_default: bool = True,
        accept_screen_time_default: bool = True,
    ) -> ConfirmResult:
        assert_loggable_date(target_date, self._clock().date())

        habits = await self._habits.list_active_habits(user_id)
        unknown = set(overrides) - {h.id for h in habits}
        if unknown:
            raise NotFoundError(f"Override(s) reference habit(s) not found for this user: {unknown}")

        proposed = await self._build_entries(user_id, habits, target_date)
        audit: dict[str, dict] = {}
        final_entries: list[CheckinEntry] = []

        for entry in proposed:
            if entry.habit_id in overrides:
                status, note = overrides[entry.habit_id]
                await self._habits.upsert_log(HabitLog(
                    habit_id=entry.habit_id, user_id=user_id, log_date=target_date,
                    status=status, note=note, is_default=False,
                ))
                final_status, is_default = status, False
            elif not entry.is_scheduled:
                final_status, is_default = None, False  # rest day: nothing written
            elif entry.is_default:
                await self._habits.upsert_log(HabitLog(
                    habit_id=entry.habit_id, user_id=user_id, log_date=target_date,
                    status=entry.status, note=None, is_default=True,
                ))
                final_status, is_default = entry.status, True
            else:
                final_status, is_default = entry.status, False  # already a real log; leave it

            audit[str(entry.habit_id)] = {
                "was_default_proposed": entry.is_default,
                "proposed_status": entry.status.value if entry.status else None,
                "final_status": final_status.value if final_status else None,
                "was_overridden": entry.habit_id in overrides,
                "was_scheduled": entry.is_scheduled,
            }
            final_entries.append(CheckinEntry(
                habit_id=entry.habit_id, habit_name=entry.habit_name, status=final_status,
                is_default=is_default, is_low_confidence=entry.is_low_confidence,
                reason=entry.reason, is_scheduled=entry.is_scheduled,
            ))

        sleep_log, audit["_sleep"] = await self._resolve_sleep(user_id, target_date, sleep, accept_sleep_default)
        screen_log, audit["_screen_time"] = await self._resolve_screen(
            user_id, target_date, screen_time, accept_screen_time_default
        )

        existing = await self._checkins.get(user_id, target_date)
        if journal_text is None:
            journal_bytes = existing.journal_encrypted if existing else None
        else:
            journal_bytes = self._encryptor.encrypt(journal_text)

        saved = await self._checkins.upsert(DailyCheckin(
            user_id=user_id, checkin_date=target_date, journal_encrypted=journal_bytes,
            defaults_applied=audit, confirmed_at=self._clock(),
        ))
        return ConfirmResult(final_entries, saved.confirmed_at or self._clock(), sleep_log, screen_log)

    # ------------------------------------------------------------ helpers
    async def _resolve_sleep(self, user_id, target_date, given: SleepInput | None, accept_default: bool):
        existing = await self._sleep.get_log(user_id, target_date)
        if given is not None:
            log = await self._sleep.upsert_log(SleepLog(
                user_id=user_id, log_date=target_date, time_to_bed=given.time_to_bed,
                time_woke=given.time_woke, self_rated_quality=given.self_rated_quality, is_default=False,
            ))
            return log, {"source": "override"}
        if existing is not None:
            return existing, {"source": "existing"}
        proposal = await self._sleep_proposal(user_id, target_date) if accept_default else None
        if proposal is None:
            return None, {"source": "none"}
        log = await self._sleep.upsert_log(SleepLog(
            user_id=user_id, log_date=target_date, time_to_bed=proposal.time_to_bed,
            time_woke=proposal.time_woke, self_rated_quality=proposal.self_rated_quality, is_default=True,
        ))
        return log, {"source": "default"}

    async def _resolve_screen(self, user_id, target_date, given: ScreenTimeInput | None, accept_default: bool):
        existing = await self._screen.get_log(user_id, target_date)
        if given is not None:
            log = await self._screen.upsert_log(ScreenTimeLog(
                user_id=user_id, log_date=target_date, total_minutes=given.total_minutes,
                source=given.source, category_breakdown=given.category_breakdown, is_default=False,
            ))
            return log, {"source": "override"}
        if existing is not None:
            return existing, {"source": "existing"}
        proposal = await self._screen_proposal(user_id, target_date) if accept_default else None
        if proposal is None:
            return None, {"source": "none"}
        log = await self._screen.upsert_log(ScreenTimeLog(
            user_id=user_id, log_date=target_date, total_minutes=proposal.total_minutes,
            source=ScreenTimeSource.MANUAL, category_breakdown=None, is_default=True,
        ))
        return log, {"source": "default"}

    async def _sleep_proposal(self, user_id: UUID, target_date: date) -> SleepProposal | None:
        history = await self._sleep.list_logs_in_range(
            user_id, target_date - timedelta(days=_PROPOSAL_LOOKBACK_DAYS), target_date - timedelta(days=1)
        )
        prop = compute_sleep_default(history, target_date)
        if prop is not None:
            return prop
        if self._goals is not None:
            active_goals = await self._goals.list(user_id, GoalStatus.ACTIVE)
            for g in active_goals:
                if g.domain == "sleep" and (g.target.get("bedtime") or g.target.get("wake")):
                    bed_t = _parse_time(g.target.get("bedtime"))
                    woke_t = _parse_time(g.target.get("wake"))
                    return SleepProposal(
                        time_to_bed=bed_t, time_woke=woke_t, self_rated_quality=4,
                        based_on_count=0, is_low_confidence=True, reason="Fallback to active sleep goal target",
                    )
        return None

    async def _screen_proposal(self, user_id: UUID, target_date: date) -> ScreenTimeProposal | None:
        history = await self._screen.list_logs_in_range(
            user_id, target_date - timedelta(days=_PROPOSAL_LOOKBACK_DAYS), target_date - timedelta(days=1)
        )
        prop = compute_screen_time_default(history, target_date)
        if prop is not None:
            return prop
        if self._goals is not None:
            active_goals = await self._goals.list(user_id, GoalStatus.ACTIVE)
            for g in active_goals:
                if g.domain == "screen_time" and "max_minutes_per_day" in g.target:
                    return ScreenTimeProposal(
                        total_minutes=g.target["max_minutes_per_day"],
                        based_on_count=0, is_low_confidence=True, reason="Fallback to active screen time goal target",
                    )
        return None

    async def _build_entries(self, user_id: UUID, habits, target_date: date) -> list[CheckinEntry]:
        if not habits:
            return []
        # One query for the day's existing logs (was one query per habit).
        existing_logs = {
            log.habit_id: log
            for log in await self._habits.get_logs_in_range(user_id, [h.id for h in habits], target_date, target_date)
        }
        needing_defaults = [h for h in habits if h.id not in existing_logs]
        defaults = {}
        if needing_defaults:
            logs_by_habit = await self._habits.get_recent_logs_by_habit(
                user_id, [h.id for h in needing_defaults], target_date
            )
            defaults = compute_habit_defaults(needing_defaults, logs_by_habit, target_date)

        entries: list[CheckinEntry] = []
        for habit in habits:
            log = existing_logs.get(habit.id)
            if log is not None:
                entries.append(CheckinEntry(
                    habit_id=habit.id, habit_name=habit.name, status=log.status,
                    is_default=log.is_default, is_low_confidence=False, reason="Already logged for this date.",
                ))
                continue
            d = defaults[habit.id]
            entries.append(CheckinEntry(
                habit_id=habit.id, habit_name=habit.name, status=d.status,
                is_default=d.is_scheduled,  # rest days are not "defaults to persist"
                is_low_confidence=d.is_low_confidence, reason=d.reason, is_scheduled=d.is_scheduled,
            ))
        return entries
