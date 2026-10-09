"""
If-then plans ("if <cue>, then <action>") against any of the five domains.
They are SURFACED, not scheduled: due() returns only plans relevant right now. For habit-linked
plans the reminder FADES as the habit becomes consistent (Gollwitzer follow-ups: fixed-cadence
reminders can undermine automaticity) -- see reminder_level().
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import GOAL_DOMAINS, Intention
from app.exceptions import NotFoundError, ValidationError
from app.repositories.goal_repository import IntentionRepository
from app.repositories.habit_repository import HabitRepository
from app.repositories.study_repository import SubjectRepository
from app.services.goals_service import clean_text
from app.services.profile_service import ProfileService
from app.services.stats_service import StatsService

MAX_ACTIVE_INTENTIONS = 30
_FADE_MIN_EXPECTED = 8.0   # need ~8 scheduled days of evidence before a reminder may fade
_FADE_OFF_PCT = 90.0
_FADE_LIGHT_PCT = 75.0


@dataclass(slots=True)
class DueIntention:
    intention: Intention
    level: str     # "full" | "light"  ("off" plans are simply not returned)
    reason: str


def reminder_level(consistency_pct: float | None, expected_days: float) -> str:
    """full -> still building it. light -> mostly automatic. off -> automatic, stop nagging."""
    if consistency_pct is None or expected_days < _FADE_MIN_EXPECTED:
        return "full"
    if consistency_pct >= _FADE_OFF_PCT:
        return "off"
    if consistency_pct >= _FADE_LIGHT_PCT:
        return "light"
    return "full"


class IntentionsService:
    def __init__(
        self, repo: IntentionRepository, habits: HabitRepository, subjects: SubjectRepository,
        stats: StatsService, profiles: ProfileService, clock: Clock = utc_now,
    ):
        self._repo, self._habits, self._subjects = repo, habits, subjects
        self._stats, self._profiles, self._clock = stats, profiles, clock

    async def _check_link(self, user_id: UUID, domain: str, entity_id: UUID | None) -> None:
        if domain == "habit":
            habit = await self._habits.get_habit(user_id, entity_id) if entity_id else None
            if habit is None or not habit.is_active:
                raise NotFoundError("A habit plan needs linked_entity_id = one of your active habits.")
        elif domain == "study":
            if entity_id is not None and await self._subjects.get(user_id, entity_id) is None:
                raise NotFoundError("That subject doesn't exist for this user.")
        elif entity_id is not None:
            raise ValidationError(f"linked_entity_id isn't used for {domain} plans.")

    async def create(
        self, user_id: UUID, linked_domain: str, linked_entity_id: UUID | None, cue: str, action: str,
    ) -> Intention:
        if linked_domain not in GOAL_DOMAINS:
            raise ValidationError(f"linked_domain must be one of {GOAL_DOMAINS}.")
        cue, action = clean_text(cue, "Cue", 200), clean_text(action, "Action", 200)
        await self._check_link(user_id, linked_domain, linked_entity_id)
        if await self._repo.count_active(user_id) >= MAX_ACTIVE_INTENTIONS:
            raise ValidationError(f"You can have at most {MAX_ACTIVE_INTENTIONS} active plans.")
        return await self._repo.create(Intention(
            id=uuid4(), user_id=user_id, linked_domain=linked_domain, cue=cue, action=action,
            created_at=self._clock(), linked_entity_id=linked_entity_id, active=True,
        ))

    async def list(self, user_id: UUID, domain: str | None = None, active_only: bool = False) -> list[Intention]:
        if domain is not None and domain not in GOAL_DOMAINS:
            raise ValidationError(f"domain must be one of {GOAL_DOMAINS}.")
        return await self._repo.list(user_id, domain, active_only)

    async def update(
        self, user_id: UUID, intention_id: UUID, cue: str | None, action: str | None, active: bool | None,
    ) -> Intention:
        clean_cue = clean_text(cue, "Cue", 200) if cue is not None else None
        clean_action = clean_text(action, "Action", 200) if action is not None else None
        if active is True:
            current = await self._repo.get(user_id, intention_id)
            if current is not None and not current.active:
                if await self._repo.count_active(user_id) >= MAX_ACTIVE_INTENTIONS:
                    raise ValidationError(f"You can have at most {MAX_ACTIVE_INTENTIONS} active plans.")
        updated = await self._repo.update(user_id, intention_id, clean_cue, clean_action, active, self._clock())
        if updated is None:
            raise NotFoundError(f"No plan {intention_id} for this user.")
        return updated

    async def delete(self, user_id: UUID, intention_id: UUID) -> None:
        if not await self._repo.delete(user_id, intention_id):
            raise NotFoundError(f"No plan {intention_id} for this user.")

    async def due(self, user_id: UUID, domain: str | None = None, on_date: date | None = None) -> list[DueIntention]:
        """Plans worth showing NOW. Ask with domain=urge when opening urge capture, domain=study when
        starting a session, etc. Habit plans skip rest days, already-logged days, and faded habits."""
        today = on_date or await self._profiles.today(user_id)
        plans = await self.list(user_id, domain, active_only=True)
        if not plans:
            return []

        habit_plans = [p for p in plans if p.linked_domain == "habit"]
        habits, consistency = {}, {}
        if habit_plans:
            habits = {h.id: h for h in await self._habits.list_active_habits(user_id)}
            _, items, _ = await self._stats.consistency(user_id, today, 30)
            consistency = {c.habit_id: c for c in items}

        out: list[DueIntention] = []
        for plan in plans:
            if plan.linked_domain != "habit":
                out.append(DueIntention(plan, "full", "Cue for this moment."))
                continue
            habit = habits.get(plan.linked_entity_id)
            if habit is None:
                continue  # archived or gone
            freq = habit.target_frequency
            if freq.type == "weekdays" and today.weekday() not in freq.days:
                continue
            log = await self._habits.get_log(user_id, habit.id, today)
            if log is not None and not log.is_default:
                continue  # you already dealt with it today
            c = consistency.get(habit.id)
            level = reminder_level(c.consistency_pct if c else None, c.expected if c else 0.0)
            if level == "off":
                continue
            out.append(DueIntention(
                plan, level,
                "Still building this one." if level == "full" else "Mostly automatic now -- light reminder.",
            ))
        return out
