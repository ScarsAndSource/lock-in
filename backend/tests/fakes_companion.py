"""In-memory fakes for the companion layer (tasks, notification prefs/subscriptions, push ledger)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from app.domain import CompanionPush, NotificationPrefs, PushSubscription, Task
from app.exceptions import ConflictError


class InMemoryTaskRepository:
    def __init__(self):
        self.rows: dict[UUID, Task] = {}

    async def create(self, t):
        self.rows[t.id] = replace(t)
        return t

    async def get(self, user_id, task_id):
        t = self.rows.get(task_id)
        return replace(t) if t and t.user_id == user_id else None

    async def list(self, user_id, status=None, limit=500):
        return [replace(t) for t in self.rows.values() if t.user_id == user_id and (status is None or t.status == status)]

    async def count_open(self, user_id):
        return len(await self.list(user_id, "open"))

    async def save(self, t, now):
        if t.id not in self.rows:
            return None
        self.rows[t.id] = replace(t)
        return replace(t)

    async def delete(self, user_id, task_id):
        t = self.rows.get(task_id)
        if t and t.user_id == user_id:
            del self.rows[task_id]
            return True
        return False


class InMemoryNotificationRepository:
    def __init__(self, prefs: NotificationPrefs | None = None):
        self.prefs: dict[UUID, NotificationPrefs] = {}
        self._default = prefs
        self.subs: list[PushSubscription] = []
        self.conflict = False

    async def get_prefs(self, user_id):
        return replace(self.prefs.get(user_id) or self._default or NotificationPrefs(user_id=user_id), user_id=user_id)

    async def save_prefs(self, p, now):
        self.prefs[p.user_id] = replace(p)
        return p

    async def list_subscriptions(self, user_id):
        return [replace(s) for s in self.subs if s.user_id == user_id]

    async def upsert_subscription(self, sub):
        if self.conflict:
            raise ConflictError("other account")
        self.subs = [s for s in self.subs if s.endpoint != sub.endpoint] + [sub]
        return sub

    async def delete_subscription(self, user_id, endpoint):
        n = len(self.subs)
        self.subs = [s for s in self.subs if s.endpoint != endpoint]
        return len(self.subs) < n

    async def delete_subscription_by_id(self, user_id, sub_id):
        self.subs = [s for s in self.subs if s.id != sub_id]

    async def set_fail_count(self, user_id, sub_id, fail_count):
        for s in self.subs:
            if s.id == sub_id:
                s.fail_count = fail_count


class InMemoryCompanionRepository:
    def __init__(self):
        self.rows: dict[UUID, CompanionPush] = {}

    async def reserve(self, push: CompanionPush) -> bool:
        if any(r.user_id == push.user_id and r.key == push.key for r in self.rows.values()):
            return False
        self.rows[push.id] = replace(push)
        return True

    async def release(self, user_id, push_id):
        r = self.rows.get(push_id)
        if r and r.user_id == user_id:
            del self.rows[push_id]

    async def list_since(self, user_id, since: datetime):
        return sorted(
            (replace(r) for r in self.rows.values() if r.user_id == user_id and r.sent_at >= since),
            key=lambda r: r.sent_at,
        )

    async def mark_acted(self, user_id, push_id, action, now):
        r = self.rows.get(push_id)
        if r is None or r.user_id != user_id or r.acted_at is not None:
            return None
        r.acted_at, r.action = now, action
        return replace(r)

    async def prune(self, user_id, before):
        old = [i for i, r in self.rows.items() if r.user_id == user_id and r.sent_at < before]
        for i in old:
            del self.rows[i]
        return len(old)
