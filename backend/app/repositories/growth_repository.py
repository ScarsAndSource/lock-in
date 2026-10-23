from __future__ import annotations

import uuid
from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyCheckinORM
from app.models_growth import FutureMessageORM, HabitAutopsyORM, IdentityProfileORM, JournalStickerORM


class SqlAlchemyGrowthRepository:
    """Persistence for the growth layer. Returns ORM rows; GrowthService owns every rule and all decryption."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ---- identity
    async def get_identity(self, user_id: UUID) -> IdentityProfileORM | None:
        stmt = select(IdentityProfileORM).where(IdentityProfileORM.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert_identity(
        self, user_id: UUID, matters: bytes, why_now: bytes, importance: int, confidence: int, sentence: bytes,
        now: datetime,
    ) -> None:
        stmt = (
            pg_insert(IdentityProfileORM)
            .values(
                user_id=user_id, matters_encrypted=matters, why_now_encrypted=why_now, importance=importance,
                confidence=confidence, sentence_encrypted=sentence, created_at=now, updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "matters_encrypted": matters, "why_now_encrypted": why_now, "importance": importance,
                    "confidence": confidence, "sentence_encrypted": sentence, "updated_at": now,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def delete_identity(self, user_id: UUID) -> bool:
        result = await self._session.execute(delete(IdentityProfileORM).where(IdentityProfileORM.user_id == user_id))
        return (result.rowcount or 0) > 0

    # ---- check-ins (votes) and the journal that lives on them
    async def count_confirmed(self, user_id: UUID, start: date | None, end: date | None) -> int:
        stmt = select(func.count()).select_from(DailyCheckinORM).where(
            DailyCheckinORM.user_id == user_id, DailyCheckinORM.confirmed_at.is_not(None),
        )
        if start is not None:
            stmt = stmt.where(DailyCheckinORM.checkin_date >= start)
        if end is not None:
            stmt = stmt.where(DailyCheckinORM.checkin_date <= end)
        return int((await self._session.execute(stmt)).scalar_one())

    async def journal_rows(self, user_id: UUID, start: date, end: date) -> list[tuple[date, bytes]]:
        stmt = select(DailyCheckinORM.checkin_date, DailyCheckinORM.journal_encrypted).where(
            DailyCheckinORM.user_id == user_id,
            DailyCheckinORM.checkin_date >= start,
            DailyCheckinORM.checkin_date <= end,
            DailyCheckinORM.journal_encrypted.is_not(None),
        )
        return [(d, b) for d, b in (await self._session.execute(stmt)).all()]

    async def upsert_journal(self, user_id: UUID, day: date, blob: bytes | None, now: datetime) -> None:
        """Touches ONLY the journal. A row created here has confirmed_at NULL, so it never counts as a confirmed
        check-in; the real check-in later keeps this text (journal_text=None means 'keep')."""
        stmt = (
            pg_insert(DailyCheckinORM)
            .values(
                user_id=user_id, checkin_date=day, journal_encrypted=blob, defaults_applied={},
                confirmed_at=None, created_at=now, updated_at=now,
            )
            .on_conflict_do_update(
                constraint="daily_checkins_user_id_checkin_date_key",
                set_={"journal_encrypted": blob, "updated_at": now},
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def stickers(self, user_id: UUID, start: date, end: date) -> dict[date, str]:
        stmt = select(JournalStickerORM.entry_date, JournalStickerORM.sticker).where(
            JournalStickerORM.user_id == user_id,
            JournalStickerORM.entry_date >= start,
            JournalStickerORM.entry_date <= end,
        )
        return {d: s for d, s in (await self._session.execute(stmt)).all()}

    async def upsert_sticker(self, user_id: UUID, day: date, sticker: str, now: datetime) -> None:
        stmt = (
            pg_insert(JournalStickerORM)
            .values(user_id=user_id, entry_date=day, sticker=sticker, created_at=now, updated_at=now)
            .on_conflict_do_update(index_elements=["user_id", "entry_date"], set_={"sticker": sticker, "updated_at": now})
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def delete_sticker(self, user_id: UUID, day: date) -> None:
        await self._session.execute(
            delete(JournalStickerORM).where(JournalStickerORM.user_id == user_id, JournalStickerORM.entry_date == day)
        )

    # ---- habit check-ups
    async def get_open_autopsy(self, user_id: UUID) -> HabitAutopsyORM | None:
        stmt = (
            select(HabitAutopsyORM)
            .where(HabitAutopsyORM.user_id == user_id, HabitAutopsyORM.status == "open")
            .order_by(HabitAutopsyORM.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_autopsy(self, user_id: UUID, autopsy_id: UUID) -> HabitAutopsyORM | None:
        stmt = select(HabitAutopsyORM).where(HabitAutopsyORM.id == autopsy_id, HabitAutopsyORM.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def cooldown_habits(self, user_id: UUID, today: date) -> set[UUID]:
        stmt = select(HabitAutopsyORM.habit_id).where(
            HabitAutopsyORM.user_id == user_id,
            HabitAutopsyORM.cooldown_until.is_not(None),
            HabitAutopsyORM.cooldown_until > today,
        )
        return set((await self._session.execute(stmt)).scalars().all())

    async def open_autopsy(
        self, user_id: UUID, habit_id: UUID, consistency_pct: float, today: date, now: datetime,
    ) -> None:
        """Race-safe: two parallel requests can't open two check-ups for one habit (partial unique index)."""
        stmt = (
            pg_insert(HabitAutopsyORM)
            .values(
                id=uuid.uuid4(), user_id=user_id, habit_id=habit_id, status="open", fix={},
                consistency_pct=consistency_pct, opened_on=today, created_at=now, updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["habit_id"], index_where=HabitAutopsyORM.status == "open")
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def resolve_autopsy(
        self, row: HabitAutopsyORM, status: str, reason: str | None, fix: dict, cooldown_until: date, now: datetime,
    ) -> None:
        row.status, row.reason, row.fix = status, reason, fix
        row.cooldown_until, row.resolved_at, row.updated_at = cooldown_until, now, now
        await self._session.flush()

    # ---- notes to future self
    async def list_future(self, user_id: UUID) -> list[FutureMessageORM]:
        stmt = select(FutureMessageORM).where(FutureMessageORM.user_id == user_id).order_by(FutureMessageORM.created_at)
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_active_future(self, user_id: UUID) -> list[FutureMessageORM]:
        stmt = select(FutureMessageORM).where(
            FutureMessageORM.user_id == user_id, FutureMessageORM.active.is_(True),
        ).order_by(FutureMessageORM.created_at)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_future(self, user_id: UUID, message_id: UUID) -> FutureMessageORM | None:
        stmt = select(FutureMessageORM).where(FutureMessageORM.id == message_id, FutureMessageORM.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_active_future(self, user_id: UUID) -> int:
        stmt = select(func.count()).select_from(FutureMessageORM).where(
            FutureMessageORM.user_id == user_id, FutureMessageORM.active.is_(True),
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def add_future(
        self, user_id: UUID, text_enc: bytes | None, audio_enc: bytes | None, mime: str | None,
        duration_s: int | None, send_at: time | None, now: datetime,
    ) -> FutureMessageORM:
        row = FutureMessageORM(
            id=uuid.uuid4(), user_id=user_id, text_encrypted=text_enc, audio_encrypted=audio_enc, audio_mime=mime,
            duration_s=duration_s, send_at=send_at, active=True, created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def set_future_active(self, user_id: UUID, message_id: UUID, active: bool, now: datetime) -> bool:
        result = await self._session.execute(
            update(FutureMessageORM)
            .where(FutureMessageORM.id == message_id, FutureMessageORM.user_id == user_id)
            .values(active=active, updated_at=now)
        )
        return (result.rowcount or 0) > 0

    async def delete_future(self, user_id: UUID, message_id: UUID) -> bool:
        result = await self._session.execute(
            delete(FutureMessageORM).where(FutureMessageORM.id == message_id, FutureMessageORM.user_id == user_id)
        )
        return (result.rowcount or 0) > 0

    async def mark_future_sent(self, user_id: UUID, message_id: UUID, day: date, now: datetime) -> None:
        await self._session.execute(
            update(FutureMessageORM)
            .where(FutureMessageORM.id == message_id, FutureMessageORM.user_id == user_id)
            .values(last_sent_on=day, updated_at=now)
        )

    async def mark_future_played(self, user_id: UUID, message_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(FutureMessageORM)
            .where(FutureMessageORM.id == message_id, FutureMessageORM.user_id == user_id)
            .values(last_played_at=now, updated_at=now)
        )
