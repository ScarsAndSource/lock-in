"""
SQLAlchemy ORM models (persistence only). Column definitions must stay in
lockstep with migrations/*.sql -- app/schema_check.py verifies that at startup.
"""
from __future__ import annotations

import uuid
from datetime import date as date_
from datetime import datetime
from datetime import time as time_

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary,
    SmallInteger, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuthUserORM(Base):
    """
    Stub of Supabase's auth.users. It exists ONLY so ForeignKey("auth.users.id")
    resolves in SQLAlchemy's metadata (otherwise flushes can raise
    NoReferencedTableError). This app never creates, reads, or writes it.
    """
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)


class ProfileORM(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="UTC")
    tone_preference: Mapped[str] = mapped_column(Text, nullable=False, default="direct")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HabitDefinitionORM(Base):
    __tablename__ = "habit_definitions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    target_frequency: Mapped[dict] = mapped_column(JSONB, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HabitLogORM(Base):
    __tablename__ = "habit_logs"
    __table_args__ = (
        UniqueConstraint("habit_id", "log_date", name="habit_logs_habit_id_log_date_key"),
        CheckConstraint("status in ('done', 'skipped', 'partial')", name="habit_logs_status_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    habit_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("habit_definitions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    log_date: Mapped[date_] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DailyCheckinORM(Base):
    __tablename__ = "daily_checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "checkin_date", name="daily_checkins_user_id_checkin_date_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    checkin_date: Mapped[date_] = mapped_column(Date, nullable=False)
    journal_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    defaults_applied: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SleepLogORM(Base):
    __tablename__ = "sleep_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "log_date", name="sleep_logs_user_id_log_date_key"),
        CheckConstraint("self_rated_quality between 1 and 5", name="sleep_logs_quality_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    log_date: Mapped[date_] = mapped_column(Date, nullable=False)
    time_to_bed: Mapped[time_ | None] = mapped_column(Time, nullable=True)
    time_woke: Mapped[time_ | None] = mapped_column(Time, nullable=True)
    self_rated_quality: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScreenTimeLogORM(Base):
    __tablename__ = "screen_time_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "log_date", name="screen_time_logs_user_id_log_date_key"),
        CheckConstraint("source in ('manual', 'extension')", name="screen_time_logs_source_check"),
        CheckConstraint("total_minutes >= 0", name="screen_time_logs_minutes_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    log_date: Mapped[date_] = mapped_column(Date, nullable=False)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    category_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MissionORM(Base):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint("status in ('active', 'completed', 'ended_early')", name="missions_status_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date_] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
