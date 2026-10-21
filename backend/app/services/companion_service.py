"""
Gathers what the companion policy needs for ONE user, then asks it what (if anything) to say.

Cost control: the job runs every 5 minutes for everyone with a device, so data is loaded LAZILY. Each block is read
only when its time window is open and its moment has not already been sent today (the ledger says so). A user with
no urge plans never costs an urge query; nobody costs a sleep query at 2 pm.

Every read goes through the same repositories/services the app uses, so RLS and validation are unchanged. Free text
(urge trigger/coping/note, journal) is never read here -- only timestamps, counts, and the person's own plan wording.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from app.exceptions import ValidationError
from app.services.nudge_policy import reason as task_reason
from app.services.next_action import HabitFacts, NextAction, NextInput, TaskFacts, pick_next
from app.services.profile_service import ProfileService
from app.services.rhythm import Rhythm, build_rhythm
from app.services.tasks_service import TasksService
from app.services.tone import resolve_tone
from app.services.task_time import zone
from app.repositories.goal_repository import IntentionRepository
from app.services.checkins_service import CheckinsService
from app.dates import Clock, utc_now

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain import NotificationPrefs
from app.repositories.checkin_repository import CheckinRepository
from app.repositories.companion_repository import CompanionRepository
from app.repositories.goal_repository import GoalRepository
from app.repositories.habit_repository import HabitRepository
from app.repositories.sleep_repository import SleepRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.urge_repository import UrgeRepository
from app.services import companion_policy as cp
from app.services import risk_windows
from app.services.bounce_back import LOOKBACK_DAYS, compute_bounce_state
from app.services.intentions_service import DueIntention, IntentionsService, reminder_level
from app.services.nudge_policy import PushMessage, classify, in_quiet_hours, min_gap
from app.services.pause_days import split_pause_days
from app.services.schedule import check_scheduled, credit, week_start
from app.services.stats_service import StatsService
from app.services.study_service import StudyService

LEDGER_DAYS = 14
BEDTIME_LOOKBACK_DAYS = 21
WINDDOWN_HOURS = (19, 3)      # only look at sleep data between 19:00 and 03:00 local


def _cues(items: list[DueIntention]) -> list[cp.PlanCue]:
    return [
        cp.PlanCue(cue=d.intention.cue, action=d.intention.action, level=d.level, entity_id=d.intention.linked_entity_id)
        for d in items
    ]


class CompanionPlanner:
    def __init__(
        self, ledger: CompanionRepository, habits: HabitRepository, checkins: CheckinRepository,
        urges: UrgeRepository, sleep: SleepRepository, goals: GoalRepository, study: StudyService,
        intentions: IntentionsService, stats: StatsService, pauses,
        tasks: TaskRepository | None = None, bounce_enabled: bool = True, insights=None,
    ):
        self._ledger, self._habits, self._checkins, self._urges = ledger, habits, checkins, urges
        self._sleep, self._goals, self._study = sleep, goals, study
        self._intentions, self._stats, self._pauses = intentions, stats, pauses
        self._tasks, self._bounce_enabled = tasks, bounce_enabled   # no task repo: the morning push is habit-only
        self._insights = insights

    async def plan(
        self, user_id, now: datetime, prefs: NotificationPrefs, tz: ZoneInfo, paused: bool,
    ) -> list[PushMessage]:
        if paused or not prefs.push_enabled or not prefs.companion_enabled:
            return []
        local = now.astimezone(tz)
        today = local.date()
        ledger = await self._ledger.list_since(user_id, now - timedelta(days=LEDGER_DAYS))
        sent = {r.key for r in ledger}
        ctx = cp.CompanionContext(now=now, tz=tz, prefs=prefs, paused=False, ledger=ledger)
        iso = today.isoformat()

        # Cheap exits first: the daily ceiling and spacing can't be beaten by any block below.
        todays = [r for r in ledger if r.kind in cp.COMPANION_KINDS and r.local_date == today]
        if len(todays) >= cp.MAX_PER_DAY or any(now - r.sent_at < cp.MIN_SPACING for r in ledger if r.kind in cp.COMPANION_KINDS):
            return []

        # ---- the day's check-in state (also what "acted" means for check-in / habit pushes)
        evening = local.hour >= min(prefs.nudge_hour, prefs.checkin_hour)
        resolvable_days = {r.local_date for r in ledger if r.kind in cp.RESOLVABLE_KINDS and r.acted_at is None}
        if evening:
            resolvable_days.add(today)
        confirmed: set[date] = set()
        for d in resolvable_days:
            row = await self._checkins.get(user_id, d)
            if row is not None and row.confirmed_at is not None:
                confirmed.add(d)
        ctx.confirmed_dates = frozenset(confirmed)
        ctx.checkin_confirmed_today = today in confirmed

        plans = await self._intentions.list(user_id, None, active_only=True)
        domains = {p.linked_domain for p in plans}

        # ---- habits: open today? (check-in + habit pushes)
        habit_window = prefs.nudge_hour <= local.hour < prefs.checkin_hour and f"habit:{iso}" not in sent
        checkin_window = local.hour >= prefs.checkin_hour and f"checkin:{iso}" not in sent
        if (habit_window or checkin_window) and not ctx.checkin_confirmed_today:
            ctx.open_habits = await self._open_habits(user_id, today, with_consistency=habit_window)
            if habit_window and "habit" in domains:
                ctx.habit_cues = _cues(await self._intentions.due(user_id, "habit", today))

        # ---- study: only while behind
        if prefs.nudge_hour <= local.hour < prefs.checkin_hour and f"study:{iso}" not in sent:
            await self._load_study(ctx, user_id, today)
            if "study" in domains:
                ctx.study_cues = _cues(await self._intentions.due(user_id, "study", today))

        # ---- risk windows: only for people who wrote an urge plan, and only if the pattern is still alive
        if "urge" in domains:
            ctx.urge_cues = _cues(await self._intentions.due(user_id, "urge", today))
            events = [u.occurred_at for u in await self._urges.list_in_range(
                user_id, today - timedelta(days=risk_windows.LOOKBACK_DAYS), today)]
            ctx.risk_windows = risk_windows.find_windows(events, tz, now)

        # ---- wind-down: only in the evening, only with enough real sleep logs
        if (local.hour >= WINDDOWN_HOURS[0] or local.hour < WINDDOWN_HOURS[1]) and not any(k.startswith("winddown:") and k.endswith(iso) for k in sent):
            logs = await self._sleep.list_logs_in_range(user_id, today - timedelta(days=BEDTIME_LOOKBACK_DAYS), today)
            ctx.bedtime = cp.median_bedtime([l.time_to_bed for l in logs if not l.is_default and l.time_to_bed is not None])
            if ctx.bedtime is not None and "sleep" in domains:
                ctx.sleep_cues = _cues(await self._intentions.due(user_id, "sleep", today))

        # ---- a new insight from today's pulse (the pulse row in the ledger means the day's data is in)
        if self._insights is not None and f"pulse:{iso}" in sent and f"insight:{iso}" not in sent:
            ctx.fresh_insights = sum(1 for i in await self._insights.list_all(user_id, 10) if i.generated_on == today)

        # ---- morning / comeback: one window, one push; a person who went quiet gets the comeback, not the morning
        await self._load_morning(ctx, user_id, local, domains, sent)

        return cp.plan_companion(ctx)

    # ------------------------------------------------------------------ blocks
    async def _load_morning(self, ctx: cp.CompanionContext, user_id, local: datetime, domains: set, sent: set[str]) -> None:
        prefs, today = ctx.prefs, local.date()
        iso = today.isoformat()
        if f"morning:{iso}" in sent or f"comeback:{iso}" in sent:
            return                                                  # this moment already went out today
        if local.hour >= prefs.nudge_hour or in_quiet_hours(local.time(), prefs.quiet_start, prefs.quiet_end):
            return                                                  # the window can only exist before the habit-nudge hour
        if not cp.morning_possible(ctx.now, ctx.tz, prefs):
            return                                                  # no wake time could open it now: skip the sleep read
        logs = await self._sleep.list_logs_in_range(user_id, today - timedelta(days=BEDTIME_LOOKBACK_DAYS), today)
        real = [l for l in logs if not l.is_default]                # guesses are never evidence
        ctx.wake = cp.median_wake([l.time_woke for l in real if l.time_woke is not None])
        if not cp.morning_window_open(ctx.now, ctx.tz, prefs, ctx.wake):
            return                                                  # nobody pays for the heavy reads outside the window
        ctx.comeback = await self._comeback_info(user_id, today, frozenset(l.log_date for l in real))
        if ctx.comeback is not None:
            return                                                  # silent: the comeback cadence owns the morning
        if cp.is_muted(ctx.ledger, "morning", ctx.now, ctx.confirmed_dates):
            return
        ctx.morning_pick = await self._morning_pick(ctx, user_id, today, domains)

    async def _morning_pick(self, ctx: cp.CompanionContext, user_id, today: date, domains: set) -> cp.MorningPick | None:
        tasks = await self._due_tasks(ctx, user_id, today)
        if any(t.importance >= 2 for t in tasks):
            return cp.pick_morning(tasks, [], [])                   # a task wins: skip the habit reads
        habits = await self._open_habits(user_id, today, with_consistency=True)
        cues = _cues(await self._intentions.due(user_id, "habit", today)) if habits and "habit" in domains else []
        return cp.pick_morning(tasks, habits, cues)

    async def _due_tasks(self, ctx: cp.CompanionContext, user_id, today: date) -> list[cp.OpenTask]:
        """Open tasks due today or overdue that the normal task nudges are NOT about to push right now (so the
        person never gets the same task twice within one run)."""
        if self._tasks is None:
            return []
        out: list[cp.OpenTask] = []
        for t in await self._tasks.list(user_id, "open"):
            if t.importance < 2 or t.due_at is None:
                continue                                            # small chores ride in the digest; backlog never pushes
            state = classify(t, ctx.now, ctx.prefs, ctx.tz)
            if state not in ("due", "upcoming"):
                continue                                            # snoozed / nudged out / not triggered at all
            if state == "due" and (t.last_nudged_at is None or ctx.now - t.last_nudged_at >= min_gap(t)):
                continue                                            # the task flow pushes this one itself
            due_day = t.due_at.astimezone(ctx.tz).date()
            if due_day > today:
                continue
            out.append(cp.OpenTask(
                task_id=t.id, title=t.title, importance=t.importance, due_at=t.due_at, overdue=due_day < today,
            ))
        return out

    async def _comeback_info(self, user_id, today: date, sleep_days: frozenset[date]) -> cp.ComebackInfo | None:
        """Silent = bounce_back says the last 2+ scheduled days slipped AND nothing real was logged (habit or sleep)
        on the last 2+ days. Returns None for someone who is already back today, or who never started."""
        if not self._bounce_enabled:
            return None
        habits = await self._habits.list_active_habits(user_id)
        if not habits:
            return None
        start = today - timedelta(days=LOOKBACK_DAYS)
        logs = await self._habits.get_logs_in_range(user_id, [h.id for h in habits], start, today)
        if any(l.log_date == today and not l.is_default for l in logs):
            return None                                             # they are already back today
        covering = await self._pauses.list_overlapping(user_id, start, today) if self._pauses is not None else []
        global_days, by_habit = split_pause_days(covering, start, today)
        if today in global_days:
            return None
        state = compute_bounce_state(habits, logs, today, global_days, by_habit)
        if not state.active or state.slip_streak < cp.COMEBACK_MIN_SILENT_DAYS:
            return None
        real_days = {l.log_date for l in logs if not l.is_default} | set(sleep_days)
        silent, day = 0, today - timedelta(days=1)
        while silent < LOOKBACK_DAYS and day not in real_days:
            silent += 1
            day -= timedelta(days=1)
        if silent < cp.COMEBACK_MIN_SILENT_DAYS:
            return None                                             # slipped, but they are still showing up
        # Restart with the habit they were most steady on (the easiest win), floor version only.
        mine: dict = {}
        for l in logs:
            mine.setdefault(l.habit_id, []).append(l)
        best = None
        for h in habits:
            if today in by_habit.get(h.id, frozenset()):
                continue
            history = mine.get(h.id, [])
            if not check_scheduled(h.target_frequency, today, [l for l in history if l.log_date < today]).scheduled:
                continue
            score = sum(credit(l.status) for l in history if not l.is_default and l.log_date < today)
            key = (-score, h.floor_text is None, h.name)
            if best is None or key < best[0]:
                best = (key, h)
        if best is None:                                            # nothing scheduled today: still silent, nothing to offer
            return cp.ComebackInfo(habit_id=None, name="", floor_text=None, silent_days=silent, slip_streak=state.slip_streak)
        h = best[1]
        return cp.ComebackInfo(
            habit_id=h.id, name=h.name, floor_text=h.floor_text, silent_days=silent, slip_streak=state.slip_streak,
        )
    async def _open_habits(self, user_id, today: date, *, with_consistency: bool) -> list[cp.OpenHabit]:
        habits = await self._habits.list_active_habits(user_id)
        if not habits:
            return []
        covering = await self._pauses.list_overlapping(user_id, today, today) if self._pauses is not None else []
        if any(p.habit_id is None for p in covering):
            return []
        paused = {p.habit_id for p in covering}
        logs = await self._habits.get_logs_in_range(user_id, [h.id for h in habits], week_start(today), today)
        by_habit: dict = {}
        for log in logs:
            by_habit.setdefault(log.habit_id, []).append(log)
        stats = {}
        if with_consistency:
            _, items, _ = await self._stats.consistency(user_id, today, 30)
            stats = {c.habit_id: c for c in items}
        out: list[cp.OpenHabit] = []
        for h in habits:
            if h.id in paused:
                continue
            mine = by_habit.get(h.id, [])
            if any(l.log_date == today and not l.is_default for l in mine):
                continue                                           # already dealt with today
            if not check_scheduled(h.target_frequency, today, [l for l in mine if l.log_date < today]).scheduled:
                continue                                           # rest day / weekly target already met
            c = stats.get(h.id)
            pct = c.consistency_pct if c else None
            out.append(cp.OpenHabit(
                habit_id=h.id, name=h.name, floor_text=h.floor_text, consistency_pct=pct,
                automatic=reminder_level(pct, c.expected if c else 0.0) == "off",
            ))
        return out

    async def _load_study(self, ctx: cp.CompanionContext, user_id, today: date) -> None:
        goals = await self._goals.list_active_by_domain(user_id, "study")
        targets = [int(g.target.get("weekly_minutes", 0)) for g in goals if g.target.get("weekly_minutes")]
        if not targets:
            return
        ctx.study_weekly_target = max(targets)
        week = await self._study.summary(user_id, week_start(today), today)
        day = await self._study.summary(user_id, today, today)
        ctx.study_week_minutes, ctx.study_today_minutes = week.total_actual, day.total_actual



LOOKBACK_DAYS = 60
MAX_SKIPPED = 10
MAX_REF_CHARS = 80
EVENT_KINDS = frozenset({"app_open", "nba_shown", "nba_acted", "nba_skipped", "push_opened"})


@dataclass(slots=True)
class CompanionNow:
    action: NextAction
    rhythm: Rhythm
    local_minute: int
    tone: str
    habits_done: int
    habits_total: int
    confirmed: bool
    seed: int
    today: date


class CompanionService:
    def __init__(
        self, repo: CompanionRepository, checkins: CheckinsService, tasks: TasksService, profiles: ProfileService,
        intentions: IntentionRepository, clock: Clock = utc_now,
    ):
        self._repo, self._checkins, self._tasks, self._profiles = repo, checkins, tasks, profiles
        self._intentions, self._clock = intentions, clock

    async def now(self, user_id: UUID, skipped: Iterable[str] = ()) -> CompanionNow:
        now = self._clock()
        profile = await self._profiles.get(user_id)
        tz = zone(profile.timezone)
        local = now.astimezone(tz)
        today = local.date()

        view = await self._checkins.get_view(user_id, today)
        focus = await self._tasks.focus(user_id)
        rhythm = build_rhythm(await self._repo.observations(user_id, tz, now, LOOKBACK_DAYS))
        plans = await self._intentions.list(user_id, "urge", active_only=True)

        habits = tuple(
            HabitFacts(str(e.habit_id), e.habit_name, e.status, e.is_default, e.is_scheduled, e.floor_text)
            for e in view.entries
        )
        tasks = tuple(
            TaskFacts(str(v.task.id), v.task.title, v.task.importance, task_reason(v.task, now, tz)) for v in focus.now
        )
        tone = resolve_tone(profile.tone_preference, view.bounce.slip_streak)
        local_minute = local.hour * 60 + local.minute
        seed = today.toordinal()
        keys = frozenset(str(k)[:MAX_REF_CHARS] for k in list(skipped)[:MAX_SKIPPED])

        action = pick_next(NextInput(
            habits=habits, tasks=tasks, confirmed=view.already_confirmed, bounce=view.bounce.active,
            local_minute=local_minute, rhythm=rhythm, tone=tone, plan=plans[0].action if plans else None,
            seed=seed, skipped=keys,
        ))

        scheduled = [h for h in habits if h.is_scheduled]
        done = [
            h for h in scheduled
            if h.status is not None and h.status != "skipped" and (not h.is_default or view.already_confirmed)
        ]
        return CompanionNow(
            action=action, rhythm=rhythm, local_minute=local_minute, tone=tone, habits_done=len(done),
            habits_total=len(scheduled), confirmed=view.already_confirmed, seed=seed, today=today,
        )

    async def record_event(self, user_id: UUID, kind: str, ref: str | None) -> None:
        if kind not in EVENT_KINDS:
            raise ValidationError(f"kind must be one of: {', '.join(sorted(EVENT_KINDS))}.")
        clean = (ref or "").strip()[:MAX_REF_CHARS] or None
        await self._repo.add_event(user_id, kind, clean, self._clock())
