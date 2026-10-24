"""
The journey layer in one service: seasons (focus cap + easy week), exam radar (topic names that will come in the
exam, revisited at 1/3/7/14 days and re-planned around everything else), the monthly life snapshot, and the
"Done Becoming" graduation shelf. Every rule lives in the pure modules next to this file.

Safe by construction:
  - nothing is ever deleted or auto-archived by the cap; it only refuses NEW habits,
  - a low wellbeing score returns the support payload, never coaching,
  - all text the person writes is encrypted at rest (topics, custom snapshot label).
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from uuid import UUID

from app.dates import Clock, utc_now
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.safety import is_crisis, support_payload
from app.security import FieldEncryptor
from app.services import graduation_rules as gr
from app.services import recall_plan as rp
from app.services import season as sn
from app.services import snapshot_math as sm
from app.services.pause_days import expand_pause_days
from app.services.unlock import stage_for

logger = logging.getLogger("lockin.journey")

MAX_ACTIVE_SETS = 12
LOOKAHEAD_DAYS = 60
MAX_LABEL_LEN = 40


class JourneyService:
    def __init__(self, repo, encryptor: FieldEncryptor, profiles, stats, habit_repo, habits, pauses, calendar,
                 clock: Clock = utc_now):
        self._repo = repo
        self._enc = encryptor
        self._profiles = profiles
        self._stats = stats
        self._habit_repo = habit_repo
        self._habits = habits
        self._pauses = pauses
        self._calendar = calendar
        self._clock = clock

    # ------------------------------------------------------------------ state + seasons
    async def state(self, user_id: UUID) -> dict:
        today = await self._profiles.today(user_id)
        created = await self._repo.profile_created_on(user_id)
        confirmed = await self._repo.count_confirmed(user_id)
        active = await self._habit_repo.list_active_habits(user_id)
        active_ids = [h.id for h in active]
        row = await self._repo.get_open_season(user_id)
        slots = sn.slots_for(len(active_ids))
        out: dict = {
            "stage": stage_for(created, today, confirmed), "season": None,
            "focus_ids": active_ids, "benched_ids": [], "slots": slots,
            "free_slots": max(0, slots - len(active_ids)),
        }
        if row is not None:
            ph = sn.phase(row.start_date, today)
            focus = sn.live_focus(row.focus_habit_ids, active_ids)
            keep = set(focus)
            out.update(
                season={
                    "id": row.id, "name": row.name, "start_date": row.start_date,
                    "phase": ph.kind, "week": ph.week, "days_left": ph.days_left,
                },
                focus_ids=focus, benched_ids=[i for i in active_ids if i not in keep], slots=row.slots,
                free_slots=sn.free_slots(row.slots, row.focus_habit_ids, active_ids),
            )
        return out

    async def gate_new_habit(self, user_id: UUID) -> None:
        """Called BEFORE a habit is created. Starts the first season lazily (existing habits are grandfathered)."""
        today = await self._profiles.today(user_id)
        now = self._clock()
        active = await self._habit_repo.list_active_habits(user_id)
        active_ids = [h.id for h in active]
        row = await self._repo.get_open_season(user_id)
        if row is None:
            row = await self._repo.create_season(
                user_id, "Season 1", today, sn.slots_for(len(active_ids)), active_ids, now,
            )
        if sn.free_slots(row.slots, row.focus_habit_ids, active_ids) <= 0:
            keep = set(sn.live_focus(row.focus_habit_ids, active_ids))
            raise ConflictError(sn.not_yet_message([h.name for h in active if h.id in keep]))

    async def adopt_habit(self, user_id: UUID, habit_id: UUID) -> None:
        """Called right AFTER a habit is created: it takes a focus slot."""
        row = await self._repo.get_open_season(user_id)
        if row is not None and habit_id not in row.focus_habit_ids:
            await self._repo.set_focus(row, [*row.focus_habit_ids, habit_id], self._clock())

    async def start_season(self, user_id: UUID, name: str | None, focus_ids: list[UUID]) -> dict:
        today = await self._profiles.today(user_id)
        now = self._clock()
        active_ids = [h.id for h in await self._habit_repo.list_active_habits(user_id)]
        focus = sn.validate_focus(focus_ids, sn.DEFAULT_SLOTS, active_ids)
        if active_ids and not focus:
            raise ValidationError("Pick at least one habit to focus on.")
        count = await self._repo.count_seasons(user_id)
        row = await self._repo.get_open_season(user_id)
        if row is not None:
            await self._repo.close_season(row, today, now)
        await self._repo.create_season(
            user_id, sn.clean_name(name, f"Season {count + 1}"), today, sn.DEFAULT_SLOTS, focus, now,
        )
        return await self.state(user_id)

    async def set_focus(self, user_id: UUID, focus_ids: list[UUID]) -> dict:
        row = await self._repo.get_open_season(user_id)
        if row is None:
            raise ConflictError("Start a Season first.")
        active_ids = [h.id for h in await self._habit_repo.list_active_habits(user_id)]
        await self._repo.set_focus(row, sn.validate_focus(focus_ids, row.slots, active_ids), self._clock())
        return await self.state(user_id)

    # ------------------------------------------------------------------ exam radar
    def _topics(self, row) -> list[str]:
        return [t for t in (self._enc.decrypt(row.topics_encrypted) or "").split("\n") if t]

    async def _exams(self, user_id: UUID, today: date) -> list:
        try:
            return await self._calendar.upcoming_exams(user_id, today)
        except Exception:  # noqa: BLE001 -- the radar still works without the calendar
            logger.warning("exam lookup failed", exc_info=True)
            return []

    async def _blocked(self, user_id: UUID, today: date, exams: list) -> frozenset[date]:
        end = today + timedelta(days=LOOKAHEAD_DAYS)
        blocked: set[date] = {e.day for e in exams}
        row = await self._repo.get_open_season(user_id)
        if row is not None:
            blocked |= {d for d in sn.rest_days(row.start_date) if today <= d <= end}
        pauses = [p for p in await self._pauses.list(user_id) if p.habit_id is None]
        blocked |= set(expand_pause_days(pauses, today, end))
        return frozenset(blocked)

    async def create_recall(self, user_id: UUID, label: str, topics_raw: str, exam_date: date | None) -> list[dict]:
        today = await self._profiles.today(user_id)
        now = self._clock()
        label = sn.clean_name(label, "")[:60]
        if not label:
            raise ValidationError("Give it a subject name.")
        topics = rp.parse_topics(topics_raw)
        if len(await self._repo.list_sets(user_id)) >= MAX_ACTIVE_SETS:
            raise ValidationError(f"You can track at most {MAX_ACTIVE_SETS} subjects at once.")
        if exam_date is not None and exam_date <= today:
            raise ValidationError("The exam date has to be after today.")
        exams = await self._exams(user_id, today)
        exam = exam_date
        if exam is None:
            hits = [e.day for e in exams if e.day > today and label.lower() in e.title.lower()]
            exam = min(hits) if hits else None
        blocked = await self._blocked(user_id, today, exams)
        load = Counter(r.due_date for r, _ in await self._repo.pending_reviews(user_id))
        plan = rp.build_plan(today, exam, blocked, dict(load))
        row = await self._repo.add_set(user_id, label, self._enc.encrypt("\n".join(topics)) or b"", exam, now)
        for step, due in plan:
            await self._repo.add_review(user_id, row.id, step, due, now)
        return await self.list_recall(user_id)

    async def list_recall(self, user_id: UUID) -> list[dict]:
        sets = await self._repo.list_sets(user_id)
        pending = await self._repo.pending_reviews(user_id)
        done = await self._repo.done_counts(user_id)
        nxt: dict[UUID, date] = {}
        left: Counter = Counter()
        for r, s in pending:
            nxt.setdefault(s.id, r.due_date)
            left[s.id] += 1
        return [
            {
                "id": s.id, "label": s.label, "topics": self._topics(s), "exam_date": s.exam_date,
                "next_due": nxt.get(s.id), "reviews_left": left.get(s.id, 0), "reviews_done": done.get(s.id, 0),
            }
            for s in sets
        ]

    async def due_recall(self, user_id: UUID) -> list[dict]:
        """Today's reviews. Also the 'resume plan' step: finished exams are retired, missed or blocked reviews move."""
        today = await self._profiles.today(user_id)
        now = self._clock()
        for s in await self._repo.list_sets(user_id):
            if s.exam_date is not None and s.exam_date < today:
                await self._repo.archive_set(s, now)
        pending = await self._repo.pending_reviews(user_id)
        if not pending:
            return []
        exams = await self._exams(user_id, today)
        blocked = await self._blocked(user_id, today, exams)
        load: dict[date, int] = {}
        for r, _ in pending:
            if r.due_date >= today and r.due_date not in blocked:
                load[r.due_date] = load.get(r.due_date, 0) + 1
        moves = rp.reflow([(r.id, r.due_date, s.exam_date) for r, s in pending], today, blocked, load)
        kept: list[tuple] = []
        for r, s in pending:
            if r.id in moves:
                new_due = moves[r.id]
                if new_due is None:
                    await self._repo.delete_review(r)
                    continue
                r.due_date = new_due
                await self._repo.save(r, now)
            kept.append((r, s))
        return [
            {
                "review_id": r.id, "set_id": s.id, "label": s.label, "topics": self._topics(s), "step": r.step,
                "exam_date": s.exam_date,
                "days_to_exam": (s.exam_date - today).days if s.exam_date is not None else None,
            }
            for r, s in kept if r.due_date <= today
        ]

    async def mark_review_done(self, user_id: UUID, review_id: UUID, extra_topics: str | None) -> None:
        now = self._clock()
        review = await self._repo.get_review(user_id, review_id)
        if review is None:
            raise NotFoundError("No review like that.")
        if review.done_at is None:
            review.done_at = now
            await self._repo.save(review, now)
        if extra_topics and extra_topics.strip():
            s = await self._repo.get_set(user_id, review.set_id)
            if s is not None:
                merged = rp.merge_topics(self._topics(s), rp.parse_topics(extra_topics))
                s.topics_encrypted = self._enc.encrypt("\n".join(merged)) or b""
                await self._repo.save(s, now)

    async def archive_recall(self, user_id: UUID, set_id: UUID) -> None:
        s = await self._repo.get_set(user_id, set_id)
        if s is None:
            raise NotFoundError("No subject like that.")
        if s.archived_at is None:
            await self._repo.archive_set(s, self._clock())

    # ------------------------------------------------------------------ monthly life snapshot
    def _to_snap(self, row) -> sm.Snap:
        return sm.Snap(
            row.taken_on, {m: getattr(row, m) for m in sm.METRICS},
            self._enc.decrypt(row.custom_label_encrypted) if row.custom_label_encrypted else None, row.custom_value,
        )

    async def snapshot_view(self, user_id: UUID) -> dict:
        today = await self._profiles.today(user_id)
        rows = await self._repo.list_snapshots(user_id)
        last = rows[-1] if rows else None
        prev = rows[-2] if len(rows) > 1 else None
        latest = None
        support = None
        if last is not None:
            snap = self._to_snap(last)
            latest = {
                "taken_on": last.taken_on, **snap.scores,
                "custom_label": snap.custom_label, "custom_value": snap.custom_value,
            }
            fresh = (today - last.taken_on).days < sm.DUE_EVERY_DAYS
            if fresh and sm.needs_support(last.wellbeing, prev.wellbeing if prev else None):
                support = support_payload((await self._profiles.get(user_id)).timezone)
        return {
            "due": sm.is_due(last.taken_on if last else None, today), "latest": latest,
            "deltas": sm.deltas([self._to_snap(r) for r in rows]), "support": support,
        }

    async def submit_snapshot(self, user_id: UUID, body) -> dict:
        today = await self._profiles.today(user_id)
        rows = await self._repo.list_snapshots(user_id)
        if rows and rows[-1].taken_on >= today:
            raise ConflictError("You already did today's snapshot.")
        label = " ".join((body.custom_label or "").replace("<", "").replace(">", "").split())[:MAX_LABEL_LEN] or None
        if (label is None) != (body.custom_value is None):
            raise ValidationError("Add both the label and the number, or neither.")
        scores = {m: getattr(body, m) for m in sm.METRICS}
        await self._repo.add_snapshot(
            user_id, today, scores, self._enc.encrypt(label) if label else None, body.custom_value, self._clock(),
        )
        view = await self.snapshot_view(user_id)
        if is_crisis(label):
            view["support"] = support_payload((await self._profiles.get(user_id)).timezone)
        return view

    # ------------------------------------------------------------------ graduation shelf
    async def shelf(self, user_id: UUID, with_offers: bool = True) -> dict:
        today = await self._profiles.today(user_id)
        habits = {h.id: h for h in await self._habit_repo.list_habits(user_id, include_archived=True)}
        grads = await self._repo.list_graduations(user_id)
        open_ids = {g.habit_id for g in grads if g.revived_on is None}
        items: list[dict] = []
        checkin = None
        for g in grads:
            if g.revived_on is not None:
                continue
            h = habits.get(g.habit_id)
            name = h.name if h is not None else "A habit"
            which = gr.due_check(g.check30_on, g.check90_on, g.check30_result, g.check90_result, today)
            items.append({
                "id": g.id, "habit_id": g.habit_id, "name": name, "graduated_on": g.graduated_on,
                "days_on_shelf": (today - g.graduated_on).days, "check_due": which,
            })
            if which is not None and checkin is None:
                checkin = {"graduation_id": g.id, "habit_name": name, "which": which}
        offers: list[dict] = []
        if with_offers:
            offers = await self._offers(user_id, today, habits, open_ids)
        return {"offers": offers, "shelf": items, "checkin": checkin}

    async def _offers(self, user_id: UUID, today: date, habits: dict, open_ids: set[UUID]) -> list[dict]:
        active = {i: h for i, h in habits.items() if h.is_active and i not in open_ids}
        if not active:
            return []
        snaps = await self._repo.list_snapshots(user_id)
        automatic = snaps[-1].automatic if snaps else None
        _, items, _ = await self._stats.consistency(user_id, today, gr.WINDOW_DAYS)
        now = self._clock()
        found = [
            {"habit_id": c.habit_id, "name": active[c.habit_id].name, "consistency_pct": float(c.consistency_pct)}
            for c in items
            if c.habit_id in active
            and gr.offer(c.consistency_pct, c.expected, (now - active[c.habit_id].created_at).days, automatic)
        ]
        found.sort(key=lambda o: -o["consistency_pct"])
        return found[: gr.MAX_OFFERS]

    async def graduate(self, user_id: UUID, habit_id: UUID) -> dict:
        today = await self._profiles.today(user_id)
        now = self._clock()
        habit = await self._habit_repo.get_habit(user_id, habit_id)
        if habit is None or not habit.is_active:
            raise NotFoundError("That habit isn't active.")
        if any(g.habit_id == habit_id and g.revived_on is None for g in await self._repo.list_graduations(user_id)):
            raise ConflictError("That habit is already on the shelf.")
        await self._habits.update_habit(user_id, habit_id, None, True)
        c30, c90 = gr.check_dates(today)
        await self._repo.add_graduation(user_id, habit_id, today, c30, c90, now)
        row = await self._repo.get_open_season(user_id)
        if row is not None and habit_id in row.focus_habit_ids:
            await self._repo.set_focus(row, [i for i in row.focus_habit_ids if i != habit_id], now)
        return {"message": f"“{habit.name}” is on your Done Becoming shelf. I'll check in at 30 and 90 days."}

    async def shelf_check(self, user_id: UUID, grad_id: UUID, holding: bool) -> dict:
        today = await self._profiles.today(user_id)
        row = await self._repo.get_graduation(user_id, grad_id)
        if row is None or row.revived_on is not None:
            raise NotFoundError("No shelf habit like that.")
        which = gr.due_check(row.check30_on, row.check90_on, row.check30_result, row.check90_result, today)
        if which is None:
            raise ConflictError("No check-in is due for this one.")
        result = "holding" if holding else "slipping"
        if which == 90:
            row.check90_result = result
        else:
            row.check30_result = result
        await self._repo.save(row, self._clock())
        message = (
            "Still holding. That's the proof it worked." if holding
            else "Okay, that happens. You can bring it back from the shelf whenever you want."
        )
        return {"message": message, "which": which}

    async def revive(self, user_id: UUID, grad_id: UUID) -> dict:
        today = await self._profiles.today(user_id)
        now = self._clock()
        row = await self._repo.get_graduation(user_id, grad_id)
        if row is None:
            raise NotFoundError("No shelf habit like that.")
        if row.revived_on is not None:
            raise ConflictError("That habit is already back.")
        await self._habits.update_habit(user_id, row.habit_id, None, False)
        row.revived_on = today
        await self._repo.save(row, now)
        season = await self._repo.get_open_season(user_id)
        active_ids = [h.id for h in await self._habit_repo.list_active_habits(user_id)]
        if season is not None and sn.free_slots(season.slots, season.focus_habit_ids, active_ids) > 0:
            await self._repo.set_focus(season, [*season.focus_habit_ids, row.habit_id], now)
            return {"message": "Back in your lineup.", "benched": False}
        return {"message": "Back, and benched until a focus slot opens.", "benched": season is not None}

    # ------------------------------------------------------------------ the one nudge on Now
    async def nudge(self, user_id: UUID) -> dict | None:
        due = await self.due_recall(user_id)
        if due:
            return {"kind": "recall", "count": len(due), "label": due[0]["label"]}
        shelf = await self.shelf(user_id, with_offers=False)
        if shelf["checkin"] is not None:
            return {"kind": "shelf_check", **shelf["checkin"]}
        st = (await self.state(user_id))["stage"]
        if st >= 3:
            snaps = await self._repo.list_snapshots(user_id)
            today = await self._profiles.today(user_id)
            if sm.is_due(snaps[-1].taken_on if snaps else None, today):
                return {"kind": "snapshot"}
            offers = (await self.shelf(user_id))["offers"]
            if offers:
                return {"kind": "graduate", "habit_id": offers[0]["habit_id"], "name": offers[0]["name"]}
        return None