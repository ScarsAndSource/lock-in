"""
Goals = what "locked in" means per domain. They feed (a) progress numbers and (b) the check-in's
first-days defaults (see CheckinsService). Urge goals use a ROLLING relapse-free % -- never a
reset-to-zero streak (SPEC section 5).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import GOAL_DOMAINS, Goal, GoalStatus
from app.exceptions import NotFoundError, ValidationError
from app.repositories.goal_repository import GoalRepository
from app.repositories.habit_repository import HabitRepository
from app.repositories.screen_time_repository import ScreenTimeRepository
from app.repositories.sleep_repository import SleepRepository
from app.services.goal_targets import normalize_target
from app.services.profile_service import ProfileService
from app.services.stats_service import StatsService
from app.services.study_service import StudyService
from app.services.urges_service import UrgesService

MAX_ACTIVE_GOALS = 20


@dataclass(slots=True)
class GoalProgress:
    goal: Goal
    current: float | None
    target_value: float
    unit: str
    on_track: bool | None   # None = no data yet; never guessed
    detail: str


def clean_text(raw: str, label: str, max_len: int) -> str:
    text = " ".join(raw.replace("<", "").replace(">", "").split())
    if not text:
        raise ValidationError(f"{label} can't be blank.")
    if len(text) > max_len:
        raise ValidationError(f"{label} is too long (max {max_len} characters).")
    return text


class GoalsService:
    def __init__(
        self, goals: GoalRepository, habits: HabitRepository, sleep: SleepRepository,
        screen: ScreenTimeRepository, stats: StatsService, study: StudyService, urges: UrgesService,
        profiles: ProfileService, clock: Clock = utc_now,
    ):
        self._goals, self._habits, self._sleep, self._screen = goals, habits, sleep, screen
        self._stats, self._study, self._urges = stats, study, urges
        self._profiles, self._clock = profiles, clock

    async def _require_habit(self, user_id: UUID, habit_id: UUID) -> None:
        habit = await self._habits.get_habit(user_id, habit_id)
        if habit is None or not habit.is_active:
            raise NotFoundError(f"No active habit {habit_id} for this user.")

    async def create(self, user_id: UUID, domain: str, definition: str, target: dict) -> Goal:
        if domain not in GOAL_DOMAINS:
            raise ValidationError(f"domain must be one of {GOAL_DOMAINS}.")
        definition = clean_text(definition, "Goal definition", 200)
        norm = normalize_target(domain, target)
        if domain == "habit":
            await self._require_habit(user_id, UUID(norm["habit_id"]))
        if await self._goals.count_active(user_id) >= MAX_ACTIVE_GOALS:
            raise ValidationError(f"You can have at most {MAX_ACTIVE_GOALS} active goals.")
        return await self._goals.create(Goal(
            id=uuid4(), user_id=user_id, domain=domain, definition=definition, target=norm,
            status=GoalStatus.ACTIVE, created_at=self._clock(),
        ))

    async def list(self, user_id: UUID, status: GoalStatus | None = None) -> list[Goal]:
        return await self._goals.list(user_id, status)

    async def update(
        self, user_id: UUID, goal_id: UUID, definition: str | None, status: GoalStatus | None,
        target: dict | None,
    ) -> Goal:
        goal = await self._goals.get(user_id, goal_id)
        if goal is None:
            raise NotFoundError(f"No goal {goal_id} for this user.")
        clean_def = clean_text(definition, "Goal definition", 200) if definition is not None else None
        norm = normalize_target(goal.domain, target) if target is not None else None
        if norm is not None and goal.domain == "habit":
            await self._require_habit(user_id, UUID(norm["habit_id"]))
        if status == GoalStatus.ACTIVE and goal.status != GoalStatus.ACTIVE:
            if await self._goals.count_active(user_id) >= MAX_ACTIVE_GOALS:
                raise ValidationError(f"You can have at most {MAX_ACTIVE_GOALS} active goals.")
        updated = await self._goals.update(user_id, goal_id, clean_def, status, norm, self._clock())
        assert updated is not None
        return updated

    # ---------------------------------------------------------------- progress
    async def progress(self, user_id: UUID) -> list[GoalProgress]:
        today = await self._profiles.today(user_id)
        out: list[GoalProgress] = []
        for goal in await self._goals.list(user_id, GoalStatus.ACTIVE):
            out.append(await getattr(self, f"_progress_{goal.domain}")(user_id, goal, today))
        return out

    async def _progress_habit(self, user_id: UUID, g: Goal, today: date) -> GoalProgress:
        t = g.target
        _, items, _ = await self._stats.consistency(user_id, today, t["window_days"])
        item = next((i for i in items if str(i.habit_id) == t["habit_id"]), None)
        if item is None or item.consistency_pct is None:
            return GoalProgress(g, None, t["min_consistency_pct"], "%", None, "No data yet for this habit (or it's archived).")
        return GoalProgress(
            g, item.consistency_pct, t["min_consistency_pct"], "%", item.consistency_pct >= t["min_consistency_pct"],
            f"{item.consistency_pct}% over the last {t['window_days']} days.",
        )

    async def _progress_screen_time(self, user_id: UUID, g: Goal, today: date) -> GoalProgress:
        t = g.target
        start = today - timedelta(days=t["window_days"] - 1)
        real = [l for l in await self._screen.list_logs_in_range(user_id, start, today) if not l.is_default]
        if not real:
            return GoalProgress(g, None, t["min_days_within_pct"], "%", None, "No logged screen time in this window yet.")
        within = sum(1 for l in real if l.total_minutes <= t["max_minutes_per_day"])
        pct = round(100.0 * within / len(real), 1)
        avg = round(sum(l.total_minutes for l in real) / len(real))
        return GoalProgress(
            g, pct, t["min_days_within_pct"], "%", pct >= t["min_days_within_pct"],
            f"{within}/{len(real)} logged days within {t['max_minutes_per_day']} min (average {avg} min).",
        )

    async def _progress_sleep(self, user_id: UUID, g: Goal, today: date) -> GoalProgress:
        t = g.target
        start = today - timedelta(days=t["window_days"] - 1)
        nights = [
            l for l in await self._sleep.list_logs_in_range(user_id, start, today)
            if not l.is_default and l.duration_minutes is not None
        ]
        if not nights:
            return GoalProgress(g, None, t["min_nights_pct"], "%", None, "No logged sleep durations in this window yet.")
        ok = sum(1 for l in nights if l.duration_minutes >= t["min_minutes_per_night"])
        pct = round(100.0 * ok / len(nights), 1)
        return GoalProgress(
            g, pct, t["min_nights_pct"], "%", pct >= t["min_nights_pct"],
            f"{ok}/{len(nights)} logged nights at {t['min_minutes_per_night']} min or more.",
        )

    async def _progress_study(self, user_id: UUID, g: Goal, today: date) -> GoalProgress:
        t = g.target
        week_start = today - timedelta(days=today.weekday())
        actual = (await self._study.summary(user_id, week_start, today)).total_actual
        pace = round(t["weekly_minutes"] * (today.weekday() + 1) / 7)
        return GoalProgress(
            g, float(actual), float(t["weekly_minutes"]), "min", actual >= pace,
            f"{actual} of {t['weekly_minutes']} min this week; pace for today is {pace} min.",
        )

    async def _progress_urge(self, user_id: UUID, g: Goal, today: date) -> GoalProgress:
        t = g.target
        pct, longest = await self._urges.relapse_free_stats(user_id, today, t["window_days"])
        return GoalProgress(
            g, pct, t["min_relapse_free_days_pct"], "%", pct >= t["min_relapse_free_days_pct"],
            f"{pct}% of the last {t['window_days']} days had no logged relapse "
            f"(longest clean run in that window: {longest} days).",
        )
