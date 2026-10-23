"""
ORM models for the growth layer. Column definitions must stay in lockstep with migrations/023_growth.sql
(app/schema_check.py verifies that at startup). Kept out of models.py so that file is untouched.
"""
from __future__ import annotations

import uuid
from datetime import date as date_
from datetime import datetime
from datetime import time as time_

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, LargeBinary, SmallInteger, Text, Time
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class IdentityProfileORM(Base):
    __tablename__ = "identity_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True,
    )
    matters_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    why_now_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sentence_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HabitAutopsyORM(Base):
    __tablename__ = "habit_autopsies"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    habit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("habit_definitions.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    consistency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_on: Mapped[date_] = mapped_column(Date, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cooldown_until: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FutureMessageORM(Base):
    __tablename__ = "future_messages"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    text_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    audio_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    audio_mime: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_s: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    send_at: Mapped[time_ | None] = mapped_column(Time, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sent_on: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JournalStickerORM(Base):
    __tablename__ = "journal_stickers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True,
    )
    entry_date: Mapped[date_] = mapped_column(Date, primary_key=True)
    sticker: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
