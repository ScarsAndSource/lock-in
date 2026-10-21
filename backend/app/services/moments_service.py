"""
Moments: the companion speaks first, at most twice a day, at times learned from the person's own day.

  morning  a little after they usually wake      only when there is one concrete thing worth saying
  evening  a little before they usually close    only when the day isn't closed yet

Respectful by construction: it shares the SAME daily push budget and quiet hours as task nudges, honours a global
pause, never repeats within a day (companion_moments), and a moment with nothing to say is recorded as skipped
rather than retried. A late cron run can't fire a morning moment in the afternoon (WINDOW_MIN).

Cron note: schedule this job at an OFFSET from send_nudges (e.g. minutes 2,7,12,...). Both read and update the
person's daily push counter, and running them in the same minute could lose one increment.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.dates import Clock, utc_now
from app.repositories.companion_repository import CompanionRepository
from app.repositories.notification_repository import NotificationRepository
from app.services.companion_service import CompanionService
from app.services.companion_voice import moment_copy
from app.services.next_action import CONCRETE_KINDS
from app.services.notifications_service import NotificationsService
from app.services.nudge_policy import PushMessage, in_quiet_hours
from app.services.profile_service import ProfileService
from app.services.push import PushSender
from app.services.rhythm import moment_times
from app.services.task_time import zone

WINDOW_MIN = 90
MOMENTS = ("morning", "evening")
URLS = {"morning": "/", "evening": "/?shortcut=checkin"}


@dataclass(slots=True)
class TickResult:
    sent: bool
    reason: str | None = None
    moment: str | None = None


def _minute(t) -> int:
    return t.hour * 60 + t.minute


class MomentsService:
    def __init__(
        self, repo: CompanionRepository, companion: CompanionService, notifications: NotificationsService,
        notif_repo: NotificationRepository, pauses, profiles: ProfileService, sender: PushSender,
        clock: Clock = utc_now,
    ):
        self._repo, self._companion, self._notifications = repo, companion, notifications
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
        if prefs.pushes_sent_day != today:
            prefs.pushes_sent_day, prefs.pushes_sent = today, 0
        if prefs.max_per_day - prefs.pushes_sent <= 0:
            return TickResult(False, "daily cap reached")
        if in_quiet_hours(local.time(), prefs.quiet_start, prefs.quiet_end):
            return TickResult(False, "quiet hours")
        handled = await self._repo.moments_today(user_id, today)
        if len(handled) >= len(MOMENTS):
            return TickResult(False, "moments done for today")
        if await self._pauses.list_overlapping(user_id, today, today, global_only=True):
            return TickResult(False, "paused")

        data = await self._companion.now(user_id)
        times = moment_times(data.rhythm, _minute(prefs.quiet_start), _minute(prefs.quiet_end))
        due = next(
            (m for m in MOMENTS if m not in handled and 0 <= data.local_minute - times[m] <= WINDOW_MIN), None,
        )
        if due is None:
            return TickResult(False, "no moment due")

        if (due == "morning" and data.action.kind not in CONCRETE_KINDS) or (due == "evening" and data.confirmed):
            # Nothing worth saying: record it so we don't recompute every five minutes, and stay quiet.
            await self._repo.mark_moment(user_id, today, due, "skipped", now)
            return TickResult(False, "nothing to say", due)

        title, body = moment_copy(due, data.tone, data.seed, data.action.kind, data.action.title)
        msg = PushMessage(
            task_ids=(), title=title, body=body, tag=f"moment-{due}", digest=False, url=URLS[due],
        )
        if not await self._notifications.deliver_text(user_id, msg):
            return TickResult(False, "not delivered", due)   # not recorded: the next run retries inside the window
        await self._repo.mark_moment(user_id, today, due, "sent", now)
        prefs.pushes_sent += 1
        await self._notif_repo.save_prefs(prefs, now)
        return TickResult(True, None, due)
