"""
ORM models for the journey layer. Column definitions must stay in lockstep with migrations/027_journey.sql
(app/schema_check.py verifies that at startup). Kept out of models.py so that file is untouched.
"""
from __future__ import annotations

import uuid
from datetime import date as date_
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, LargeBinary, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


def _user_fk() -> ForeignKey:
    return ForeignKey("auth.users.id", ondelete="CASCADE")


class SeasonORM(Base):
    __tablename__ = "seasons"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), _user_fk())
    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date_] = mapped_column(Date, nullable=False)
    slots: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    focus_habit_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list)
    closed_on: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecallSetORM(Base):
    __tablename__ = "recall_sets"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), _user_fk())
    label: Mapped[str] = mapped_column(Text, nullable=False)
    topics_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    exam_date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecallReviewORM(Base):
    __tablename__ = "recall_reviews"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), _user_fk())
    set_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("recall_sets.id", ondelete="CASCADE"))
    step: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    due_date: Mapped[date_] = mapped_column(Date, nullable=False)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LifeSnapshotORM(Base):
    __tablename__ = "life_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), _user_fk())
    taken_on: Mapped[date_] = mapped_column(Date, nullable=False)
    wellbeing: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sleep: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    focus: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    becoming: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    automatic: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    custom_label_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    custom_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HabitGraduationORM(Base):
    __tablename__ = "habit_graduations"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), _user_fk())
    habit_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("habit_definitions.id", ondelete="CASCADE"))
    graduated_on: Mapped[date_] = mapped_column(Date, nullable=False)
    check30_on: Mapped[date_] = mapped_column(Date, nullable=False)
    check90_on: Mapped[date_] = mapped_column(Date, nullable=False)
    check30_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    check90_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    revived_on: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    