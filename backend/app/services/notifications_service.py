"""
Notification prefs, push subscriptions and the dispatch step the cron job runs.

dispatch() is the only place pushes are sent. Order of business:
  prefs/subscriptions/sender present? -> daily cap left? -> nudge_policy.plan_pushes() decides WHAT -> send ->
  only a push that actually reached a device counts toward the cap and advances a task's backoff.
A failed send changes nothing about the task, so the next run simply retries it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import time
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import NotificationPrefs, PushSubscription
from app.exceptions import ValidationError
from app.repositories.notification_repository import NotificationRepository
from app.repositories.task_repository import TaskRepository
from app.services.nudge_policy import PushMessage, in_quiet_hours, plan_pushes
from app.services.profile_service import ProfileService
from app.services.push import PushOutcome, PushSender, validate_endpoint
from app.services.task_time import zone

logger = logging.getLogger("lockin.notifications")

MAX_FAILS_BEFORE_DROP = 5
MAX_SUBSCRIPTIONS = 10


@dataclass(slots=True)
class DispatchResult:
    sent: int = 0
    reason: str | None = None   # why nothing was sent, when that's worth knowing


class NotificationsService:
    def __init__(
        self, repo: NotificationRepository, tasks: TaskRepository, pauses, profiles: ProfileService,
        sender: PushSender, allowed_hosts: list[str], clock: Clock = utc_now,
    ):
        self._repo, self._tasks, self._pauses, self._profiles = repo, tasks, pauses, profiles
        self._sender, self._allowed_hosts, self._clock = sender, allowed_hosts, clock

    # ---------------------------------------------------------------- prefs
    async def get_prefs(self, user_id: UUID) -> NotificationPrefs:
        return await self._repo.get_prefs(user_id)

    async def update_prefs(self, user_id: UUID, changes: dict) -> NotificationPrefs:
        prefs = await self._repo.get_prefs(user_id)
        for key in ("push_enabled", "quiet_start", "quiet_end", "nudge_hour", "max_per_day"):
            if key in changes and changes[key] is not None:
                setattr(prefs, key, changes[key])
        if not 0 <= prefs.nudge_hour <= 23:
            raise ValidationError("Nudge hour must be 0-23.")
        if not 1 <= prefs.max_per_day <= 20:
            raise ValidationError("Max notifications per day must be 1-20.")
        if in_quiet_hours(time(prefs.nudge_hour), prefs.quiet_start, prefs.quiet_end):
            raise ValidationError("Your nudge hour falls inside your quiet hours. Move one of them.")
        return await self._repo.save_prefs(prefs, self._clock())

    async def status(self, user_id: UUID) -> tuple[NotificationPrefs, int, bool]:
        prefs = await self._repo.get_prefs(user_id)
        subs = await self._repo.list_subscriptions(user_id)
        return prefs, len(subs), self._sender.configured

    # ---------------------------------------------------------------- subscriptions
    async def subscribe(
        self, user_id: UUID, endpoint: str, p256dh: str, auth: str, user_agent: str | None,
    ) -> None:
        validate_endpoint(endpoint, self._allowed_hosts)
        existing = await self._repo.list_subscriptions(user_id)
        if len(existing) >= MAX_SUBSCRIPTIONS and all(s.endpoint != endpoint for s in existing):
            raise ValidationError(f"At most {MAX_SUBSCRIPTIONS} devices per account.")
        await self._repo.upsert_subscription(PushSubscription(
            id=uuid4(), user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth,
            created_at=self._clock(), user_agent=(user_agent or "")[:300] or None,
        ))

    async def unsubscribe(self, user_id: UUID, endpoint: str) -> None:
        await self._repo.delete_subscription(user_id, endpoint)

    async def send_test(self, user_id: UUID) -> int:
        if not self._sender.configured:
            raise ValidationError("Push isn't set up on the server yet.")
        subs = await self._repo.list_subscriptions(user_id)
        if not subs:
            raise ValidationError("No device is registered for notifications yet.")
        delivered = 0
        for sub in subs:
            outcome = await self._sender.send(
                sub, {"title": "Lock'in", "body": "Notifications are working.", "tag": "test", "url": "/"}
            )
            delivered += outcome is PushOutcome.OK
            if outcome is PushOutcome.GONE:
                await self._repo.delete_subscription_by_id(user_id, sub.id)
        return delivered

    # ---------------------------------------------------------------- dispatch (cron)
    async def dispatch(self, user_id: UUID) -> DispatchResult:
        if not self._sender.configured:
            return DispatchResult(0, "push not configured")
        prefs = await self._repo.get_prefs(user_id)
        if not prefs.push_enabled:
            return DispatchResult(0, "push disabled by user")
        subs = await self._repo.list_subscriptions(user_id)
        if not subs:
            return DispatchResult(0, "no subscriptions")

        now = self._clock()
        tz = zone((await self._profiles.get(user_id)).timezone)
        today = now.astimezone(tz).date()
        if prefs.pushes_sent_day != today:
            prefs.pushes_sent_day, prefs.pushes_sent = today, 0
        remaining = prefs.max_per_day - prefs.pushes_sent
        if remaining <= 0:
            return DispatchResult(0, "daily cap reached")

        open_tasks = await self._tasks.list(user_id, "open")
        paused = bool(await self._pauses.list_overlapping(user_id, today, today, global_only=True))
        plan = plan_pushes(open_tasks, now, prefs, tz, paused=paused)[:remaining]
        if not plan:
            return DispatchResult(0, None)

        by_id = {t.id: t for t in open_tasks}
        live = list(subs)
        sent = 0
        for msg in plan:
            if not live:
                break
            if await self._deliver(user_id, msg, live):
                sent += 1
                prefs.pushes_sent += 1
                for tid in msg.task_ids:
                    task = by_id[tid]
                    task.nudge_count += 1
                    task.last_nudged_at = now
                    await self._tasks.save(task, now)
        if sent or prefs.pushes_sent_day == today:
            await self._repo.save_prefs(prefs, now)
        return DispatchResult(sent, None)

    async def _deliver(self, user_id: UUID, msg: PushMessage, live: list[PushSubscription]) -> bool:
        payload = {"title": msg.title, "body": msg.body, "tag": msg.tag, "url": "/", "digest": msg.digest}
        delivered = False
        for sub in list(live):
            outcome = await self._sender.send(sub, payload)
            if outcome is PushOutcome.OK:
                delivered = True
                if sub.fail_count:
                    sub.fail_count = 0
                    await self._repo.set_fail_count(user_id, sub.id, 0)
            elif outcome is PushOutcome.GONE:
                await self._repo.delete_subscription_by_id(user_id, sub.id)
                live.remove(sub)
            else:
                sub.fail_count += 1
                if sub.fail_count >= MAX_FAILS_BEFORE_DROP:
                    await self._repo.delete_subscription_by_id(user_id, sub.id)
                    live.remove(sub)
                else:
                    await self._repo.set_fail_count(user_id, sub.id, sub.fail_count)
        return delivered
