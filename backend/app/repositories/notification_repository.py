from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotificationPrefs, PushSubscription
from app.exceptions import ConflictError
from app.models import NotificationPrefsORM, PushSubscriptionORM


class NotificationRepository(Protocol):
    async def get_prefs(self, user_id: UUID) -> NotificationPrefs: ...          # defaults when no row yet
    async def save_prefs(self, prefs: NotificationPrefs, now: datetime) -> NotificationPrefs: ...
    async def list_subscriptions(self, user_id: UUID) -> list[PushSubscription]: ...
    async def upsert_subscription(self, sub: PushSubscription) -> PushSubscription: ...
    async def delete_subscription(self, user_id: UUID, endpoint: str) -> bool: ...
    async def delete_subscription_by_id(self, user_id: UUID, sub_id: UUID) -> None: ...
    async def set_fail_count(self, user_id: UUID, sub_id: UUID, fail_count: int) -> None: ...


def _prefs(row: NotificationPrefsORM) -> NotificationPrefs:
    return NotificationPrefs(
        user_id=row.user_id, push_enabled=row.push_enabled, quiet_start=row.quiet_start, quiet_end=row.quiet_end,
        nudge_hour=row.nudge_hour, max_per_day=row.max_per_day, pushes_sent_day=row.pushes_sent_day,
        pushes_sent=row.pushes_sent,
    )


def _sub(row: PushSubscriptionORM) -> PushSubscription:
    return PushSubscription(
        id=row.id, user_id=row.user_id, endpoint=row.endpoint, p256dh=row.p256dh, auth=row.auth,
        created_at=row.created_at, user_agent=row.user_agent, fail_count=row.fail_count,
    )


class SqlAlchemyNotificationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_prefs(self, user_id: UUID) -> NotificationPrefs:
        row = (await self._session.execute(
            select(NotificationPrefsORM).where(NotificationPrefsORM.user_id == user_id)
        )).scalar_one_or_none()
        return _prefs(row) if row else NotificationPrefs(user_id=user_id)

    async def save_prefs(self, prefs: NotificationPrefs, now: datetime) -> NotificationPrefs:
        values = dict(
            push_enabled=prefs.push_enabled, quiet_start=prefs.quiet_start, quiet_end=prefs.quiet_end,
            nudge_hour=prefs.nudge_hour, max_per_day=prefs.max_per_day, pushes_sent_day=prefs.pushes_sent_day,
            pushes_sent=prefs.pushes_sent, updated_at=now,
        )
        stmt = pg_insert(NotificationPrefsORM).values(user_id=prefs.user_id, **values).on_conflict_do_update(
            index_elements=[NotificationPrefsORM.user_id], set_=values,
        )
        await self._session.execute(stmt)
        return prefs

    async def list_subscriptions(self, user_id: UUID) -> list[PushSubscription]:
        stmt = select(PushSubscriptionORM).where(PushSubscriptionORM.user_id == user_id).order_by(
            PushSubscriptionORM.created_at
        )
        return [_sub(r) for r in (await self._session.execute(stmt)).scalars().all()]

    async def upsert_subscription(self, sub: PushSubscription) -> PushSubscription:
        """One row per endpoint. RLS stops a different user from taking over someone else's endpoint row."""
        values = dict(p256dh=sub.p256dh, auth=sub.auth, user_agent=sub.user_agent, fail_count=0)
        stmt = pg_insert(PushSubscriptionORM).values(
            id=sub.id, user_id=sub.user_id, endpoint=sub.endpoint, created_at=sub.created_at, **values,
        ).on_conflict_do_update(constraint="push_subscriptions_endpoint_key", set_=values)
        try:
            await self._session.execute(stmt)
        except DBAPIError as exc:  # the endpoint row belongs to another account on this browser (RLS refuses it)
            raise ConflictError(
                "This browser is already registered for another account. Turn notifications off there first."
            ) from exc
        return sub

    async def delete_subscription(self, user_id: UUID, endpoint: str) -> bool:
        result = await self._session.execute(
            delete(PushSubscriptionORM).where(
                PushSubscriptionORM.user_id == user_id, PushSubscriptionORM.endpoint == endpoint
            )
        )
        return (result.rowcount or 0) > 0

    async def delete_subscription_by_id(self, user_id: UUID, sub_id: UUID) -> None:
        await self._session.execute(
            delete(PushSubscriptionORM).where(
                PushSubscriptionORM.user_id == user_id, PushSubscriptionORM.id == sub_id
            )
        )

    async def set_fail_count(self, user_id: UUID, sub_id: UUID, fail_count: int) -> None:
        row = (await self._session.execute(
            select(PushSubscriptionORM).where(
                PushSubscriptionORM.user_id == user_id, PushSubscriptionORM.id == sub_id
            )
        )).scalar_one_or_none()
        if row is not None:
            row.fail_count = fail_count
            await self._session.flush()
