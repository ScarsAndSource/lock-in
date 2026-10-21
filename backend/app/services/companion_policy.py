"""
Companion policy: WHAT the app should say on its own, and when. PURE: no DB, no clock, no network.

Before this, only tasks ever pushed. Now five more moments can, all built from the person's own data and all bound by
the same anti-nag rules as nudge_policy:

  checkin   evening "Does today look normal?"  -> Lock it / Rough day            (one tap closes the day)
  habit     one open habit, with the person's own if-then plan or floor version -> Done / Floor version
  risk      30 min before an hour their urges cluster: their OWN if-then plan, neutral on the lock screen
  winddown  ~40 min before their usual bedtime (their own sleep plan, else a plain heads-up)
  study     only when this week's study goal is falling behind and nothing was studied today
  insight   ONE neutral push the day a new pattern shows up in your data (the lock screen never names it)

Rules that hold for every kind (the same philosophy as nudge_policy, SPEC sections 6 and 8):
  * Quiet hours win. The one exception is the person's OWN if-then plan, and only if they turned
    `plan_cues_in_quiet` on. A global pause silences all companion pushes.
  * At most MAX_PER_DAY companion pushes a day, at most one per run, never within MIN_SPACING of the last one.
  * Back off, never escalate: three pushes of a kind in a row that were ignored mute that kind for 3 days, six for
    7 days (a push counts as "acted" when a button was tapped, or the day's check-in was confirmed for check-in/habit).
  * Habits that are already automatic never get a push (same fade rule as intentions_service.reminder_level).
  * Copy is plain and uses only the person's own words. Nothing guilt-based, nothing about streaks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.domain import CompanionPush, NotificationPrefs
from app.services.nudge_policy import PushMessage, in_quiet_hours
from app.services.risk_windows import RiskWindow
from app.services.task_time import at_local

COMPANION_KINDS = ("checkin", "habit", "risk", "winddown", "study", "insight")
PLAN_CUE_KINDS = ("risk", "winddown", "study", "habit")   # kinds that can carry the person's own if-then plan
RESOLVABLE_KINDS = ("checkin", "habit")                   # "acted" also when that day's check-in was confirmed

MAX_PER_DAY = 3
MIN_SPACING = timedelta(minutes=45)
PENDING_GRACE = timedelta(hours=3)        # a push this fresh is not "ignored" yet
MUTE_AFTER_IGNORED, MUTE_DAYS = 3, 3
LONG_MUTE_AFTER_IGNORED, LONG_MUTE_DAYS = 6, 7
RISK_LEAD, RISK_GRACE = timedelta(minutes=30), timedelta(minutes=15)
WIND_LEAD, WIND_GRACE = timedelta(minutes=45), timedelta(minutes=-20)   # fires bed-45m .. bed-20m
STUDY_BEHIND_RATIO = 0.6
PRIORITY = {"risk": 90, "winddown": 80, "checkin": 65, "habit": 60, "insight": 55, "study": 50}
TTL_MINUTES = {"risk": 120, "winddown": 90, "checkin": 6 * 60, "habit": 4 * 60, "study": 4 * 60, "insight": 12 * 60}


@dataclass(frozen=True, slots=True)
class OpenHabit:
    """A habit scheduled today with no real log yet (and not paused)."""
    habit_id: UUID
    name: str
    floor_text: str | None = None
    consistency_pct: float | None = None
    automatic: bool = False        # consistent enough that the reminder has faded (intentions_service rule)


@dataclass(frozen=True, slots=True)
class PlanCue:
    """The person's own if-then plan, as returned by IntentionsService.due()."""
    cue: str
    action: str
    level: str = "full"            # full | light
    entity_id: UUID | None = None  # the habit a habit plan is linked to


@dataclass(slots=True)
class CompanionContext:
    now: datetime
    tz: ZoneInfo
    prefs: NotificationPrefs
    paused: bool = False
    ledger: list[CompanionPush] = field(default_factory=list)       # last ~14 days
    confirmed_dates: frozenset[date] = frozenset()                  # local days whose check-in was confirmed
    checkin_confirmed_today: bool = False
    open_habits: list[OpenHabit] = field(default_factory=list)
    habit_cues: list[PlanCue] = field(default_factory=list)
    urge_cues: list[PlanCue] = field(default_factory=list)
    sleep_cues: list[PlanCue] = field(default_factory=list)
    study_cues: list[PlanCue] = field(default_factory=list)
    risk_windows: list[RiskWindow] = field(default_factory=list)
    bedtime: time | None = None
    study_weekly_target: int | None = None
    study_week_minutes: int = 0
    study_today_minutes: int = 0
    fresh_insights: int = 0        # new insights generated TODAY by the daily pulse and not yet pushed


# ---------------------------------------------------------------- small pure helpers
def clip(text: str, limit: int) -> str:
    one = " ".join(text.split())
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "â€¦"


def occurrence_near(now: datetime, tz: ZoneInfo, at: time, lead: timedelta, grace: timedelta) -> date | None:
    """The local date whose `at` o'clock is within [-lead, +grace] of now. Looks at today, tomorrow (a lead that
    crosses midnight) and yesterday (a grace that does), so 00:10 windows fire at 23:40 and not never."""
    local = now.astimezone(tz)
    for offset in (0, 1, -1):
        day = local.date() + timedelta(days=offset)
        start = at_local(day, at, tz)
        if start - lead <= local <= start + grace:
            return day
    return None


def ignored_streak(
    ledger: list[CompanionPush], kind: str, now: datetime, confirmed_dates: frozenset[date],
) -> int:
    mine = sorted((r for r in ledger if r.kind == kind), key=lambda r: r.sent_at, reverse=True)
    streak = 0
    for row in mine:
        if row.acted_at is not None:
            break
        if kind in RESOLVABLE_KINDS and row.local_date in confirmed_dates:
            break                                  # they dealt with that day in the app: not ignored
        if now - row.sent_at < PENDING_GRACE:
            continue                               # too fresh to call ignored
        streak += 1
    return streak


def is_muted(
    ledger: list[CompanionPush], kind: str, now: datetime, confirmed_dates: frozenset[date],
) -> bool:
    streak = ignored_streak(ledger, kind, now, confirmed_dates)
    if streak >= LONG_MUTE_AFTER_IGNORED:
        days = LONG_MUTE_DAYS
    elif streak >= MUTE_AFTER_IGNORED:
        days = MUTE_DAYS
    else:
        return False
    last = max(r.sent_at for r in ledger if r.kind == kind)
    return now - last < timedelta(days=days)


def _msg(
    kind: str, key: str, title: str, body: str, actions: tuple[tuple[str, str], ...], args: dict, url: str,
    *, has_plan: bool = False,
) -> PushMessage:
    return PushMessage(
        task_ids=(), title=clip(title, 80), body=clip(body, 140), tag=kind, digest=False, kind=kind, key=key,
        args={**args, **({"has_plan": "1"} if has_plan else {})}, actions=actions, url=url,
        priority=PRIORITY[kind], ttl_minutes=TTL_MINUTES[kind],
    )


def _plan_text(cue: PlanCue) -> str:
    return f"If {clip(cue.cue, 60)}, then {clip(cue.action, 60)}"


# ---------------------------------------------------------------- the five moments
def _checkin(ctx: CompanionContext, local: datetime) -> PushMessage | None:
    if local.hour < ctx.prefs.checkin_hour or ctx.checkin_confirmed_today or not ctx.open_habits:
        return None
    names = [h.name for h in ctx.open_habits]
    shown = ", ".join(clip(n, 24) for n in names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
    return _msg(
        "checkin", f"checkin:{local.date().isoformat()}", "Does today look normal?",
        f"{shown}. Lock the defaults, or call it a rough day.",
        (("lock", "Lock it"), ("rough", "Rough day")), {"date": local.date().isoformat()}, "/?a=checkin",
    )


def _habit(ctx: CompanionContext, local: datetime) -> PushMessage | None:
    p = ctx.prefs
    if not (p.nudge_hour <= local.hour < p.checkin_hour) or ctx.checkin_confirmed_today or not ctx.open_habits:
        return None
    by_id = {h.habit_id: h for h in ctx.open_habits}
    chosen, cue = None, None
    for c in ctx.habit_cues:                       # their own plan first, but only a plan that is still "full"
        if c.level == "full" and c.entity_id in by_id:
            chosen, cue = by_id[c.entity_id], c
            break
    if chosen is None:
        pool = [h for h in ctx.open_habits if not h.automatic]
        if not pool:
            return None
        chosen = min(pool, key=lambda h: 50.0 if h.consistency_pct is None else h.consistency_pct)
    if cue is not None:
        body = _plan_text(cue)
    elif chosen.floor_text:
        body = f"Floor version counts: {clip(chosen.floor_text, 80)}"
    else:
        body = "Still open today. The small version counts."
    return _msg(
        "habit", f"habit:{local.date().isoformat()}", chosen.name, body,
        (("done", "Done"), ("floor", "Floor version")),
        {"habit_id": str(chosen.habit_id), "date": local.date().isoformat()}, "/?a=habit", has_plan=cue is not None,
    )


def _risk(ctx: CompanionContext, local: datetime) -> PushMessage | None:
    if not ctx.urge_cues:
        return None
    cue = ctx.urge_cues[0]
    for w in ctx.risk_windows:
        if w.recent_events < 1:
            continue                                # the pattern faded: stop talking about it
        day = occurrence_near(ctx.now, ctx.tz, w.start, RISK_LEAD, RISK_GRACE)
        if day is None or day.weekday() not in w.weekdays:
            continue
        title, body = ("Your plan", "Tap to see it.") if ctx.prefs.discreet_push else ("Heads up", _plan_text(cue))
        return _msg(
            "risk", f"risk:{day.isoformat()}:{w.start_hour:02d}", title, body,
            (("ok", "Got it"), ("later", "Not today")), {}, "/?a=plan", has_plan=True,
        )
    return None


def _winddown(ctx: CompanionContext, local: datetime) -> PushMessage | None:
    if ctx.bedtime is None:
        return None
    day = occurrence_near(ctx.now, ctx.tz, ctx.bedtime, WIND_LEAD, WIND_GRACE)
    if day is None:
        return None
    cue = ctx.sleep_cues[0] if ctx.sleep_cues else None
    body = _plan_text(cue) if cue else f"Bedtime is usually around {ctx.bedtime.strftime('%H:%M')}. Good time to wind down."
    return _msg(
        "winddown", f"winddown:{day.isoformat()}", "Wind down", body,
        (("ok", "On it"), ("later", "Not tonight")), {}, "/?a=sleep", has_plan=cue is not None,
    )


def _study(ctx: CompanionContext, local: datetime) -> PushMessage | None:
    p = ctx.prefs
    target = ctx.study_weekly_target
    if target is None or not (p.nudge_hour <= local.hour < p.checkin_hour) or ctx.study_today_minutes > 0:
        return None
    expected = target * (local.weekday() + 1) / 7
    if ctx.study_week_minutes >= STUDY_BEHIND_RATIO * expected:
        return None
    cue = ctx.study_cues[0] if ctx.study_cues else None
    remaining = max(0, target - ctx.study_week_minutes)
    body = _plan_text(cue) if cue else f"{remaining} min to go this week. One short block now?"
    return _msg(
        "study", f"study:{local.date().isoformat()}", "Study", body,
        (("ok", "Starting"), ("later", "Not today")), {}, "/?a=study", has_plan=cue is not None,
    )


def _insight(ctx: CompanionContext, local: datetime) -> PushMessage | None:
    if ctx.fresh_insights < 1:
        return None
    return _msg(
        "insight", f"insight:{local.date().isoformat()}", "A pattern showed up",
        "Something in your recent data lines up. Tap to see it.", (("view", "Show me"),), {}, "/?a=insight",
    )


_BUILDERS = (_risk, _winddown, _checkin, _habit, _insight, _study)


def plan_companion(ctx: CompanionContext) -> list[PushMessage]:
    """At most ONE message per run (the next run, 5 minutes on, picks up anything still due)."""
    prefs = ctx.prefs
    if not prefs.push_enabled or not prefs.companion_enabled or ctx.paused:
        return []
    local = ctx.now.astimezone(ctx.tz)
    mine = [r for r in ctx.ledger if r.kind in COMPANION_KINDS]
    if sum(1 for r in mine if r.local_date == local.date()) >= MAX_PER_DAY:
        return []
    if any(ctx.now - r.sent_at < MIN_SPACING for r in mine):
        return []
    sent_keys = {r.key for r in ctx.ledger}
    quiet = in_quiet_hours(local.time(), prefs.quiet_start, prefs.quiet_end)

    ready: list[PushMessage] = []
    for build in _BUILDERS:
        msg = build(ctx, local)
        if msg is None or msg.key in sent_keys:
            continue
        own_plan = msg.kind in PLAN_CUE_KINDS and msg.args.get("has_plan") == "1"
        if quiet and not (own_plan and prefs.plan_cues_in_quiet):
            continue
        if is_muted(ctx.ledger, msg.kind, ctx.now, ctx.confirmed_dates):
            continue
        ready.append(msg)
    ready.sort(key=lambda m: -m.priority)
    return ready[:1]


def median_bedtime(times: list[time], minimum: int = 5) -> time | None:
    """Typical bedtime from REAL sleep logs. Bedtimes straddle midnight (23:30 and 00:30 are an hour apart), so the
    clock is measured from noon: 12:00 = 0 ... 11:59 next day = 1439. Needs `minimum` logs or returns None."""
    if len(times) < minimum:
        return None
    shifted = sorted((t.hour * 60 + t.minute - 12 * 60) % 1440 for t in times)
    mid = shifted[len(shifted) // 2] if len(shifted) % 2 else (shifted[len(shifted) // 2 - 1] + shifted[len(shifted) // 2]) // 2
    minutes = (mid + 12 * 60) % 1440
    return time(minutes // 60, minutes % 60)
