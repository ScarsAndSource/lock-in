"""
SQLAlchemy ORM models. These exist purely for persistence — application
logic operates on app.domain dataclasses, and repositories translate
between the two. Keeping this boundary means the ORM never leaks into
services, routers, or tests that don't need a real database.

Column definitions must stay in lockstep with
migrations/001_init_habit_and_checkin.sql. There is no migration-generation
tool wired up in this slice (e.g. Alembic) — flagging that as a deliberate
gap, not an oversight: for a two-migration-file project it would be
premature machinery, but it should be added before this schema grows much
further, or the SQL and the ORM will drift silently.
"""
from __future__ import annotations

import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, LargeBinary, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
