"""
Delivers a note-to-future-self at the person's usual slip time. Called by jobs/future_self_tick.py.

  * One note a day, picked from the active ones that are due (stable per day, so a retry never swaps it).
  * Due = within WINDOW_MIN after the note's own time, else after the start of their strongest LIVE urge window
    (from their own urge log, see risk_windows), else 23:00.
  * The person scheduled it, so it deliberately ignores quiet hours and the daily cap (it still counts toward the
    day's push counter). It still honours: push switched off, no device, and a global pause.
  * The push body never carries the note itself: lock screens are public. The note opens inside the app.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.dates import Clock, utc_now
from app.services.nudge_policy import PushMessage
from app.services.risk_windows import LOOKBACK_DAYS, find_windows
from app.services.growth_service import slip_minute
from app.services.task_time import zone

WINDOW_MIN = 60


@dataclass(slots=True)
class TickResult:
    sent: bool
    reason: str | None = None


class FutureSelfDispatcher:
    def __init__(self, repo, urges, notifications, notif_repo, pauses, profiles, sender, clock: Clock = utc_now):
        self._repo, self._urges, self._notifications = repo, urges, notifications
        self._notif_repo, self._pauses, self._profiles = notif_repo, pauses, profiles
        self._sender, self._clock = sender, clock

    async def tick(self, user_id: UUID) -> TickResult:
        if not self._sender.configured:
            return TickResult(False, "push not configured")
        prefs = await self._notif_repo.get_prefs(user_id)
        if not prefs.push_enabled:
            return TickResult(False, "push disabled by user")
        if not await self._notif_repo.list_subscriptions(user_id):
            return TickResult(False, "no subscriptions")

        now = self._clock()
        tz = zone((await self._profiles.get(user_id)).timezone)
        local = now.astimezone(tz)
        today = local.date()
        local_minute = local.hour * 60 + local.minute

        notes = await self._repo.list_active_future(user_id)
        if not notes or any(n.last_sent_on == today for n in notes):
            return TickResult(False, "nothing to send")
        if await self._pauses.list_overlapping(user_id, today, today, global_only=True):
            return TickResult(False, "paused")

        windows: list = []
        if any(n.send_at is None for n in notes):
            logs = await self._urges.list_in_range(user_id, (now - timedelta(days=LOOKBACK_DAYS)).date(), today)
            windows = find_windows([u.occurred_at for u in logs], tz, now)
        due = [n for n in notes if 0 <= local_minute - slip_minute(n.send_at, windows) <= WINDOW_MIN]
        if not due:
            return TickResult(False, "not time yet")

        note = random.Random(f"{today.isoformat()}:{user_id}").choice(sorted(due, key=lambda n: str(n.id)))
        body = "You left yourself a voice note for right now. Tap to hear it." if note.audio_encrypted is not None \
            else "You left yourself a note for right now. Tap to read it."
        msg = PushMessage(
            task_ids=(), title="A note from you, to you", body=body, tag="future-self", digest=False,
            kind="future", url=f"/?a=future&id={note.id}",
        )
        if not await self._notifications.deliver_text(user_id, msg):
            return TickResult(False, "not delivered")   # not marked: the next run retries inside the window
        await self._repo.mark_future_sent(user_id, note.id, today, now)
        if prefs.pushes_sent_day != today:
            prefs.pushes_sent_day, prefs.pushes_sent = today, 0
        prefs.pushes_sent += 1
        await self._notif_repo.save_prefs(prefs, now)
        return TickResult(True)
