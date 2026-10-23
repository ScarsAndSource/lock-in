"""
Notification prefs, push subscriptions and the dispatch step the cron job runs.

dispatch() is the only place pushes are sent. Order of business:
  prefs/subscriptions/sender present? -> daily cap left? -> nudge_policy.plan_pushes() decides WHAT about tasks and
  the (optional) companion planner decides WHAT about habits / check-in / risk windows / sleep / study ->
  ONE shared daily budget, highest priority first -> send ->
  only a push that actually reached a device counts toward the cap and advances a task's backoff.
A failed send changes nothing about the task, so the next run simply retries it.

Actionable pushes: a message with a `key` is written to the push ledger BEFORE it is sent (the unique key is the
idempotency gate, so overlapping cron runs can never double-send a moment), and when it has `actions` it carries ONE
signed, single-use, short-lived token the service worker can POST back without a session (see push_actions.py).
Without a ledger / secret (older wiring, tests) pushes are exactly what they were: plain text, click opens the app.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import CompanionPush, NotificationPrefs, PushSubscription
from app.exceptions import ValidationError
from app.repositories.notification_repository import NotificationRepository
from app.repositories.task_repository import TaskRepository
from app.services import push_actions
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
        *, ledger=None, companion=None, action_secret: bytes | None = None, api_url: str = "",
    ):
        self._repo, self._tasks, self._pauses, self._profiles = repo, tasks, pauses, profiles
        self._sender, self._allowed_hosts, self._clock = sender, allowed_hosts, clock
        self._ledger, self._companion = ledger, companion
        self._secret, self._api_url = action_secret, api_url.rstrip("/")

    # ---------------------------------------------------------------- prefs
    async def get_prefs(self, user_id: UUID) -> NotificationPrefs:
        return await self._repo.get_prefs(user_id)

    async def update_prefs(self, user_id: UUID, changes: dict) -> NotificationPrefs:
        prefs = await self._repo.get_prefs(user_id)
        for key in (
            "push_enabled", "quiet_start", "quiet_end", "nudge_hour", "max_per_day",
            "companion_enabled", "checkin_hour", "plan_cues_in_quiet", "discreet_push",
        ):
            if key in changes and changes[key] is not None:
                setattr(prefs, key, changes[key])
        if not 0 <= prefs.nudge_hour <= 23:
            raise ValidationError("Nudge hour must be 0-23.")
        if not 0 <= prefs.checkin_hour <= 23:
            raise ValidationError("Check-in hour must be 0-23.")
        if not 1 <= prefs.max_per_day <= 20:
            raise ValidationError("Max notifications per day must be 1-20.")
        if in_quiet_hours(time(prefs.nudge_hour), prefs.quiet_start, prefs.quiet_end):
            raise ValidationError("Your nudge hour falls inside your quiet hours. Move one of them.")
        if in_quiet_hours(time(prefs.checkin_hour), prefs.quiet_start, prefs.quiet_end):
            raise ValidationError("Your check-in hour falls inside your quiet hours. Move one of them.")
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
            if self._ledger is not None:   # first run of the local day: drop ledger rows older than a month
                await self._ledger.prune(user_id, now - timedelta(days=30))
        remaining = prefs.max_per_day - prefs.pushes_sent
        if remaining <= 0:
            return DispatchResult(0, "daily cap reached")

        open_tasks = await self._tasks.list(user_id, "open")
        paused = bool(await self._pauses.list_overlapping(user_id, today, today, global_only=True))
        plan = plan_pushes(open_tasks, now, prefs, tz, paused=paused)
        if self._companion is not None:
            plan += await self._companion.plan(user_id, now, prefs, tz, paused)
        plan = sorted(plan, key=lambda m: -m.priority)[:remaining]   # ONE budget for tasks and companion pushes
        if not plan:
            return DispatchResult(0, None)

        by_id = {t.id: t for t in open_tasks}
        live = list(subs)
        sent = 0
        for msg in plan:
            if not live:
                break
            outcome = await self._send(user_id, msg, live, today, now)
            if outcome == "dup":
                # This exact moment already went out (a crash lost the task's counter): advance it, don't resend.
                for tid in msg.task_ids:
                    await self._advance(by_id.get(tid), now)
                continue
            if outcome == "sent":
                sent += 1
                prefs.pushes_sent += 1
                for tid in msg.task_ids:
                    await self._advance(by_id.get(tid), now)
        if sent or prefs.pushes_sent_day == today:
            await self._repo.save_prefs(prefs, now)
        return DispatchResult(sent, None)

    async def _advance(self, task, now: datetime) -> None:
        if task is None:
            return
        task.nudge_count += 1
        task.last_nudged_at = now
        await self._tasks.save(task, now)

    async def _send(
        self, user_id: UUID, msg: PushMessage, live: list[PushSubscription], today: date, now: datetime,
    ) -> str:
        """sent | failed | dup. Reserves the ledger row first so the same moment can never go out twice."""
        push_id: UUID | None = None
        if msg.key and self._ledger is not None:
            push_id = uuid4()
            reserved = await self._ledger.reserve(CompanionPush(
                id=push_id, user_id=user_id, kind=msg.kind, key=msg.key, local_date=today, sent_at=now,
            ))
            if not reserved:
                return "dup"
        delivered = await self._deliver_payload(user_id, self._payload(msg, user_id, push_id, now), live)
        if not delivered and push_id is not None:
            await self._ledger.release(user_id, push_id)   # nothing reached a device: let the next run retry
        return "sent" if delivered else "failed"

    def _payload(self, msg: PushMessage, user_id: UUID, push_id: UUID | None, now: datetime) -> dict:
        payload: dict = {
            "title": msg.title, "body": msg.body, "tag": msg.tag, "url": msg.url, "digest": msg.digest,
            "kind": msg.kind,
        }
        if push_id is not None and self._secret:
            # Every tracked push carries a token, buttons or not: the service worker needs it to report a tap ("open")
            # and a swipe-away ("dismiss"). Like "open", "dismiss" is always accepted, so `allowed` stays exactly the
            # list of real actions (the buttons).
            if msg.actions:
                payload["actions"] = [{"action": a, "title": label} for a, label in msg.actions]
            payload["token"] = push_actions.mint(
                self._secret, user_id=user_id, push_id=push_id, kind=msg.kind,
                args={k: str(v) for k, v in msg.args.items()},
                allowed=tuple(a for a, _ in msg.actions), expires_at=now + timedelta(minutes=msg.ttl_minutes),
            )
            payload["api"] = self._api_url
        return payload

    async def deliver_text(self, user_id: UUID, msg: PushMessage) -> bool:
        """Push one non-task message (the companion's moments) to the person's devices. True if one device got it.
        The caller owns the daily budget; dead subscriptions are cleaned up exactly as for task nudges."""
        live = list(await self._repo.list_subscriptions(user_id))
        return bool(live) and await self._deliver(user_id, msg, live)

    async def _deliver(self, user_id: UUID, msg: PushMessage, live: list[PushSubscription]) -> bool:
        return await self._deliver_payload(user_id, self._payload(msg, user_id, None, self._clock()), live)

    async def _deliver_payload(self, user_id: UUID, payload: dict, live: list[PushSubscription]) -> bool:
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
            elif outcome is PushOutcome.ERROR:
                continue  # our misconfiguration or a local error: never punish the user's subscription
            else:
                sub.fail_count += 1
                if sub.fail_count >= MAX_FAILS_BEFORE_DROP:
                    await self._repo.delete_subscription_by_id(user_id, sub.id)
                    live.remove(sub)
                else:
                    await self._repo.set_fail_count(user_id, sub.id, sub.fail_count)
        return delivered
