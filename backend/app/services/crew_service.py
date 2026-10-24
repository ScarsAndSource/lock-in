"""Crew: validation, error mapping, and the weekly numbers. The privacy rules live in the SQL functions
(migrations 024/025); the rules about what counts as 'showing up' live here.

Showing up, per day: at least one REAL (not auto-filled) habit log that is not 'skipped'. A floor-version day
counts fully. Planned days: weekday habits give their scheduled, un-paused days; n-per-week habits give their
count. Paused days shrink the plan instead of becoming misses. The shown number is capped at the plan, so
over-doing it never looks better than hitting it. Study hours are capped per day so nobody trades sleep for a total.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from uuid import UUID

from app.dates import Clock
from app.domain import HabitStatus
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.safety import is_crisis, support_payload
from app.services.pause_days import split_pause_days
from app.services.schedule import week_start

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,19}$")
CODE_RE = re.compile(r"^[0-9a-f]{24}$")
CHEERS = frozenset({"showed_up", "proud", "hard_week", "rooting"})
DAILY_STUDY_CAP_MIN = 300
MAX_TEXT = 120
MAX_WEEKS_BACK = 28  # days

_ERRORS: dict[str, tuple[type[Exception], str]] = {
    "unauthorized": (NotFoundError, "Not found."),
    "forbidden": (NotFoundError, "Not found."),
    "not_found": (NotFoundError, "Not found."),
    "invalid": (ValidationError, "That doesn't look right."),
    "reserved": (ValidationError, "That username is reserved."),
    "taken": (ConflictError, "That username is taken."),
    "need_username": (ValidationError, "Pick a username first."),
    "self": (ValidationError, "That's you."),
    "already": (ConflictError, "They're already in this crew or have a pending invite."),
    "crew_limit": (ConflictError, "You can be in at most 3 crews."),
    "crew_full": (ConflictError, "That crew is full (6 people max)."),
    "already_today": (ConflictError, "You already cheered them today."),
    "too_many": (ConflictError, "That's the limit for today. Try again tomorrow."),
    "nobody": (ValidationError, "There's no one else in the crew yet."),
    "deal_limit": (ConflictError, "That's the limit: two buddy deals at a time."),
    "duel_limit": (ConflictError, "That's the limit: two duels at a time."),
}


def _raise(res: dict, not_found: str | None = None) -> dict:
    code = res.get("error")
    if code:
        exc, msg = _ERRORS.get(code, (ValidationError, "Request failed."))
        if code == "not_found" and not_found:
            msg = not_found
        raise exc(msg)
    return res


def _handle(value: str) -> str:
    return value.strip().lstrip("@").lower()


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    s = " ".join(re.sub(r"[\x00-\x1f\x7f]+", " ", value).split())
    return s[:MAX_TEXT] or None


def target_week(today: date) -> date:
    """The week the Crew card is about: the one ending today (Sunday) or, any other day, the one that just ended."""
    ws = week_start(today)
    return ws if today.weekday() == 6 else ws - timedelta(days=7)


def _line(value: str | None, limit: int) -> str:
    return " ".join(re.sub(r"[\x00-\x1f\x7f]+", " ", value or "").split())[:limit]


class CrewService:
    def __init__(self, repo, habits, pauses, study, profiles, clock: Clock):
        self._repo = repo
        self._habits = habits
        self._pauses = pauses
        self._study = study
        self._profiles = profiles
        self._clock = clock

    # ---- identity, crews, invites
    async def overview(self) -> dict:
        return _raise(await self._repo.overview())

    async def set_username(self, username: str) -> dict:
        name = _handle(username)
        if not USERNAME_RE.match(name):
            raise ValidationError("Usernames are 3-20 characters: lowercase letters, numbers or _, starting with a letter.")
        return _raise(await self._repo.set_username(name))

    async def set_share(self, share: dict[str, bool]) -> dict:
        return _raise(await self._repo.set_share(share))

    async def create(self, name: str) -> dict:
        return _raise(await self._repo.create(name.strip()))

    async def invite(self, crew_id: UUID, username: str) -> dict:
        name = _handle(username)
        if not USERNAME_RE.match(name):
            raise NotFoundError("No one has that username.")
        return _raise(await self._repo.invite(crew_id, name), not_found="No one has that username.")

    async def respond(self, crew_id: UUID, accept: bool) -> dict:
        return _raise(await self._repo.respond(crew_id, accept), not_found="That invite is gone.")

    async def join(self, code: str) -> dict:
        key = code.strip().lower()
        if not CODE_RE.match(key):
            raise NotFoundError("That code didn't work. It may have expired.")
        return _raise(await self._repo.join(key), not_found="That code didn't work. It may have expired.")

    async def make_code(self, crew_id: UUID, revoke: bool) -> dict:
        return _raise(await self._repo.make_code(crew_id, revoke))

    async def leave(self, crew_id: UUID) -> dict:
        return _raise(await self._repo.leave(crew_id))

    async def set_quiet(self, crew_id: UUID, quiet: bool) -> dict:
        return _raise(await self._repo.set_quiet(crew_id, quiet))

    async def block(self, username: str) -> dict:
        name = _handle(username)
        if not USERNAME_RE.match(name):
            raise NotFoundError("No one has that username.")
        return _raise(await self._repo.block(name), not_found="No one has that username.")

    async def unblock(self, username: str) -> dict:
        return _raise(await self._repo.unblock(_handle(username)))

    # ---- the week
    async def week_info(self, user_id: UUID) -> dict:
        ws = target_week(await self._profiles.today(user_id))
        return {
            "week_start": ws,
            "week_end": ws + timedelta(days=6),
            "closed": await self._repo.snapshot_exists(user_id, ws),
            "preview": await self._compute(user_id, ws),
        }

    async def close_week(self, user_id: UUID, proud: str | None, focus: str | None, picks: list[str]) -> dict:
        ov = _raise(await self._repo.overview())
        if not ov.get("username"):
            raise ValidationError("Pick a username first.")
        share = ov.get("share") or {}
        ws = target_week(await self._profiles.today(user_id))
        stats = await self._compute(user_id, ws)

        p = _clean(proud) if share.get("proud") else None
        f = _clean(focus) if share.get("focus") else None
        support = None
        if (p and is_crisis(p)) or (f and is_crisis(f)):  # never put that line in front of a crew
            p = f = None
            support = support_payload((await self._profiles.get(user_id)).timezone)

        chosen: list[str] | None = None
        if share.get("habits"):
            wanted = dict.fromkeys(c for c in (_clean(x) for x in picks) if c and c in stats["habit_names"])
            chosen = list(wanted)[:5] or None

        created = await self._repo.close_week(
            user_id, ws,
            days_showed=stats["days_showed"] if share.get("days") else None,
            days_planned=stats["days_planned"] if share.get("days") else None,
            marks=stats["marks"] if share.get("days") else None,
            study_minutes=stats["study_minutes"] if share.get("hours") else None,
            proud=p, focus=f, habits=chosen,
        )
        await self._submit_scores(user_id)   # closing your week is what scores your duels
        return {"week_start": ws, "closed": True, "created": created, "support": support}

    async def card(self, user_id: UUID, crew_id: UUID, week: date | None) -> dict:
        tw = target_week(await self._profiles.today(user_id))
        ws = week or tw
        if ws.weekday() != 0 or ws > tw or ws < tw - timedelta(days=MAX_WEEKS_BACK):
            raise ValidationError("That week isn't available.")
        res = _raise(await self._repo.card(crew_id, ws))
        if res.get("locked"):
            return res
        # No 1st/2nd/last: a per-week, per-crew shuffle, not alphabetical and not by anything they did.
        res["members"].sort(key=lambda m: hashlib.md5(f"{ws}:{crew_id}:{m['username']}".encode()).hexdigest())
        res["week_end"] = ws + timedelta(days=6)
        target = (await self._repo.goal(crew_id, ws)).get("target_minutes")
        if target:
            got = res.get("study_minutes")
            res["goal"] = {"target_minutes": target, "met": None if got is None else got >= target}
        return res

    # ---- cheers, boosts, inbox
    async def send_cheer(self, crew_id: UUID, to: str, kind: str) -> dict:
        if kind not in CHEERS:
            raise ValidationError("Pick one of the preset cheers.")
        return _raise(await self._repo.send_cheer(crew_id, _handle(to), kind))

    async def send_boost(self, crew_id: UUID, to: str | None) -> dict:
        return _raise(await self._repo.send_boost(crew_id, _handle(to) if to else None))

    async def inbox(self) -> dict:
        return _raise(await self._repo.inbox())

    async def inbox_seen(self) -> dict:
        return _raise(await self._repo.inbox_seen())

    # ---- numbers for one week (own data, own RLS context)
    async def _compute(self, user_id: UUID, ws: date) -> dict:
        end = ws + timedelta(days=6)
        habits = await self._habits.list_active_habits(user_id)
        names = {h.id: h.name for h in habits}
        logs = await self._habits.get_logs_in_range(user_id, list(names), ws, end)

        showed: set[date] = set()
        habit_names: set[str] = set()
        for lg in logs:
            if lg.is_default or lg.status == HabitStatus.SKIPPED:  # guessed days never count
                continue
            showed.add(lg.log_date)
            habit_names.add(names[lg.habit_id])

        pauses = await self._pauses.list_overlapping(user_id, ws, end)
        global_days, by_habit = split_pause_days(pauses, ws, end)
        planned_days: set[date] = set()
        n_target = 0
        for h in habits:
            f = h.target_frequency
            paused = by_habit.get(h.id, frozenset())
            if f.type == "weekdays":
                for i in range(7):
                    d = ws + timedelta(days=i)
                    if d.weekday() in f.days and d not in global_days and d not in paused:
                        planned_days.add(d)
            else:
                n_target = max(n_target, min(f.count or 0, 7 - len(global_days | paused)))

        planned = min(max(len(planned_days), n_target), max(7 - len(global_days), 0))
        ordered = sorted(showed)
        if planned == 0 and ordered:
            planned = len(ordered)
        n = min(len(ordered), planned)
        marks = sum(1 << (d - ws).days for d in ordered[:n])

        per_day: dict[date, int] = {}
        for s in await self._study.list_in_range(user_id, ws, end):
            per_day[s.log_date] = per_day.get(s.log_date, 0) + s.actual_minutes
        minutes = sum(min(v, DAILY_STUDY_CAP_MIN) for v in per_day.values())

        return {
            "days_showed": n, "days_planned": planned, "marks": marks,
            "study_minutes": minutes, "habit_names": sorted(habit_names),
        }

    # ---- crew goal (cooperative: next week's study hours, set by the owner)
    async def next_goal(self, user_id: UUID, crew_id: UUID) -> dict:
        ws = target_week(await self._profiles.today(user_id)) + timedelta(days=7)
        res = _raise(await self._repo.goal(crew_id, ws))
        return {"week_start": ws, "target_minutes": res.get("target_minutes")}

    async def set_goal(self, user_id: UUID, crew_id: UUID, hours: int | None) -> dict:
        ws = target_week(await self._profiles.today(user_id)) + timedelta(days=7)
        return _raise(await self._repo.set_goal(crew_id, ws, hours))

    # ---- buddy deals ("if I go quiet, I'll message X" -- the owner's tap, never automatic by default)
    async def miss_streak(self, user_id: UUID, today: date, since: date) -> int:
        """Planned weekday-habit days with no real log, counted back from yesterday until a day they showed up.
        Paused days and days with nothing scheduled neither add nor break the run. n-per-week habits have no
        day-level miss, so they never add to it (showing up on any day still ends the run)."""
        lo, hi = max(since, today - timedelta(days=14)), today - timedelta(days=1)
        if lo > hi:
            return 0
        habits = await self._habits.list_active_habits(user_id)
        if not habits:
            return 0
        logs = await self._habits.get_logs_in_range(user_id, [h.id for h in habits], lo, hi)
        showed = {lg.log_date for lg in logs if not lg.is_default and lg.status != HabitStatus.SKIPPED}
        global_days, by_habit = split_pause_days(await self._pauses.list_overlapping(user_id, lo, hi), lo, hi)
        misses, day = 0, hi
        while day >= lo:
            if day in showed:
                break
            if any(
                h.target_frequency.type == "weekdays" and day.weekday() in h.target_frequency.days
                and day not in global_days and day not in by_habit.get(h.id, frozenset())
                for h in habits
            ):
                misses += 1
            day -= timedelta(days=1)
        return misses

    async def buddy_overview(self, user_id: UUID) -> dict:
        res = _raise(await self._repo.buddy_list())
        today = await self._profiles.today(user_id)
        for d in res["deals"]:
            d["misses"], d["due"] = None, False
            if d["role"] == "owner" and d["status"] == "active":
                since = date.fromisoformat(d["armed_from"]) if d.get("armed_from") else today
                d["misses"] = await self.miss_streak(user_id, today, since)
                d["due"] = d["misses"] >= d["threshold"]
        return res

    async def buddy_propose(
        self, user_id: UUID, crew_id: UUID, to: str, threshold: int, message: str, auto_send: bool,
    ) -> dict:
        msg = _line(message, 140)
        if not msg:
            raise ValidationError("Write the message you'd send.")
        if is_crisis(msg):   # never park that line in a friend's inbox; show real resources instead
            return {"ok": False, "support": support_payload((await self._profiles.get(user_id)).timezone)}
        res = _raise(
            await self._repo.buddy_propose(crew_id, _handle(to), threshold, msg, auto_send),
            not_found="No one in this crew has that username.",
        )
        return {**res, "support": None}

    async def buddy_respond(self, user_id: UUID, deal_id: UUID, accept: bool) -> dict:
        today = await self._profiles.today(user_id)
        return _raise(await self._repo.buddy_respond(deal_id, accept, today), not_found="That deal is gone.")

    async def buddy_send(self, user_id: UUID, deal_id: UUID) -> dict:
        today = await self._profiles.today(user_id)
        return _raise(await self._repo.buddy_send(deal_id, today), not_found="That deal isn't active.")

    async def buddy_hold(self, user_id: UUID, deal_id: UUID) -> dict:
        today = await self._profiles.today(user_id)
        return _raise(await self._repo.buddy_dismiss(deal_id, today))

    async def buddy_cancel(self, deal_id: UUID) -> dict:
        return _raise(await self._repo.buddy_cancel(deal_id))

    # ---- handicapped duels (vs your own last four weeks, not vs each other's hours)
    async def duel_propose(self, user_id: UUID, crew_id: UUID, to: str) -> dict:
        ws = target_week(await self._profiles.today(user_id)) + timedelta(days=7)
        return _raise(
            await self._repo.duel_propose(crew_id, _handle(to), ws),
            not_found="No one in this crew has that username.",
        )

    async def duel_respond(self, user_id: UUID, duel_id: UUID, accept: bool) -> dict:
        res = _raise(await self._repo.duel_respond(duel_id, accept), not_found="That duel is gone.")
        if accept:
            await self._submit_scores(user_id)   # already closed that week? score it now
        return res

    async def duel_cancel(self, duel_id: UUID) -> dict:
        return _raise(await self._repo.duel_cancel(duel_id))

    async def duel_list(self) -> dict:
        return _raise(await self._repo.duel_list())

    async def _submit_scores(self, user_id: UUID) -> None:
        for d in (await self._repo.duel_list()).get("duels", []):
            if d["status"] != "active" or d["my_scored"]:
                continue
            ws = date.fromisoformat(d["week_start"])
            if not await self._repo.snapshot_exists(user_id, ws):   # only after YOU closed that week
                continue
            ratio, baseline = await self._duel_numbers(user_id, ws)
            await self._repo.duel_score(UUID(d["id"]), ratio, baseline)

    async def _duel_numbers(self, user_id: UUID, ws: date) -> tuple[int, int]:
        """(this week's ratio, mean ratio of the 4 weeks before it), in thousandths. Past weeks are measured with
        today's habit set, which is an approximation if habits changed. A week with nothing planned (rest) scores
        exactly your baseline: resting never costs you."""
        prev = []
        for i in range(1, 5):
            s = await self._compute(user_id, ws - timedelta(days=7 * i))
            if s["days_planned"]:
                prev.append(s["days_showed"] / s["days_planned"])
        baseline = round(1000 * sum(prev) / len(prev)) if prev else 0
        cur = await self._compute(user_id, ws)
        ratio = round(1000 * cur["days_showed"] / cur["days_planned"]) if cur["days_planned"] else baseline
        return min(ratio, 1000), min(baseline, 1000)
