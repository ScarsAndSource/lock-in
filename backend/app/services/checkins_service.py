from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from app.domain import DailyCheckin, HabitLog, HabitStatus
from app.exceptions import NotFoundError
from app.repositories.checkin_repository import CheckinRepository
from app.repositories.habit_repository import HabitRepository
from app.security import FieldEncryptor
from app.services.defaults_service import compute_habit_defaults


@dataclass(slots=True)
class CheckinEntry:
    habit_id: UUID
    habit_name: str
    status: HabitStatus
    is_default: bool
    is_low_confidence: bool
    reason: str


class CheckinsService:
    def __init__(
        self,
        habit_repo: HabitRepository,
        checkin_repo: CheckinRepository,
        encryptor: FieldEncryptor,
    ):
        self._habits = habit_repo
        self._checkins = checkin_repo
        self._encryptor = encryptor

    async def get_view(
        self, user_id: UUID, target_date: date
    ) -> tuple[list[CheckinEntry], bool]:
        """
        Returns the proposed check-in view for target_date: every active
        habit, either showing its real logged status (already recorded) or
        a computed default (not yet recorded). Never mutates anything —
        safe to call repeatedly, e.g. every time the check-in screen loads.
        """
        habits = await self._habits.list_active_habits(user_id)
        existing_checkin = await self._checkins.get(user_id, target_date)
        entries = await self._build_entries(user_id, habits, target_date)
        return entries, existing_checkin is not None and existing_checkin.confirmed_at is not None

    async def confirm(
        self,
        user_id: UUID,
        target_date: date,
        overrides: dict[UUID, tuple[HabitStatus, str | None]],
        journal_text: str | None,
    ) -> list[CheckinEntry]:
        habits = await self._habits.list_active_habits(user_id)
        active_habit_ids = {h.id for h in habits}

        unknown_override_ids = set(overrides) - active_habit_ids
        if unknown_override_ids:
            raise NotFoundError(
                f"Override(s) reference habit(s) not found for this user: "
                f"{unknown_override_ids}"
            )

        proposed_entries = await self._build_entries(user_id, habits, target_date)
        defaults_applied_audit: dict[str, dict] = {}
        final_entries: list[CheckinEntry] = []

        for entry in proposed_entries:
            if entry.habit_id in overrides:
                status, note = overrides[entry.habit_id]
                await self._habits.upsert_log(
                    HabitLog(
                        habit_id=entry.habit_id,
                        user_id=user_id,
                        log_date=target_date,
                        status=status,
                        note=note,
                        is_default=False,
                    )
                )
                final_status, is_default = status, False
            elif entry.is_default:
                # No override given -- the proposed default is accepted as-is.
                await self._habits.upsert_log(
                    HabitLog(
                        habit_id=entry.habit_id,
                        user_id=user_id,
                        log_date=target_date,
                        status=entry.status,
                        note=None,
                        is_default=True,
                    )
                )
                final_status, is_default = entry.status, True
            else:
                # Already had a real log before this confirm call -- leave
                # it untouched, don't overwrite a real entry with itself
                # under a new timestamp for no reason.
                final_status, is_default = entry.status, False

            defaults_applied_audit[str(entry.habit_id)] = {
                "was_default_proposed": entry.is_default,
                "proposed_status": entry.status.value,
                "final_status": final_status.value,
                "was_overridden": entry.habit_id in overrides,
            }
            final_entries.append(
                CheckinEntry(
                    habit_id=entry.habit_id,
                    habit_name=entry.habit_name,
                    status=final_status,
                    is_default=is_default,
                    is_low_confidence=entry.is_low_confidence,
                    reason=entry.reason,
                )
            )

        await self._checkins.upsert(
            DailyCheckin(
                user_id=user_id,
                checkin_date=target_date,
                journal_encrypted=self._encryptor.encrypt(journal_text),
                defaults_applied=defaults_applied_audit,
                confirmed_at=datetime.now(timezone.utc),
            )
        )

        return final_entries

    async def _build_entries(self, user_id, habits, target_date) -> list[CheckinEntry]:
        habits_needing_defaults = []
        entries: list[CheckinEntry] = []

        for habit in habits:
            existing_log = await self._habits.get_log(user_id, habit.id, target_date)
            if existing_log is not None:
                entries.append(
                    CheckinEntry(
                        habit_id=habit.id,
                        habit_name=habit.name,
                        status=existing_log.status,
                        is_default=existing_log.is_default,
                        is_low_confidence=False,
                        reason="Already logged for this date.",
                    )
                )
            else:
                habits_needing_defaults.append(habit)

        if habits_needing_defaults:
            logs_by_habit = await self._habits.get_recent_logs_by_habit(
                user_id, [h.id for h in habits_needing_defaults], target_date
            )
            defaults = compute_habit_defaults(habits_needing_defaults, logs_by_habit, target_date)
            for habit in habits_needing_defaults:
                d = defaults[habit.id]
                entries.append(
                    CheckinEntry(
                        habit_id=habit.id,
                        habit_name=habit.name,
                        status=d.status,
                        is_default=True,
                        is_low_confidence=d.is_low_confidence,
                        reason=d.reason,
                    )
                )

        return entries
