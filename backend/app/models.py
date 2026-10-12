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
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, LargeBinary,
    SmallInteger, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
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


class WeeklyRetroORM(Base):
    __tablename__ = "weekly_retros"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="weekly_retros_user_week_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    week_start: Mapped[date_] = mapped_column(Date, nullable=False)
    week_end: Mapped[date_] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    narrated: Mapped[bool] = mapped_column(default=False)
    voice_version: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PatternInsightORM(Base):
    __tablename__ = "pattern_insights"
    __table_args__ = (
        UniqueConstraint("user_id", "pattern_key", "generated_on", name="pattern_insights_user_key_day"),
        CheckConstraint("user_feedback in ('accurate', 'not_quite', 'unsure')", name="pattern_insights_feedback_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_on: Mapped[date_] = mapped_column(Date, nullable=False)
    pattern_key: Mapped[str] = mapped_column(Text, nullable=False)
    insight_text: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    source_domains: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    evidence_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    narrated: Mapped[bool] = mapped_column(default=False)
    voice_version: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SubjectORM(Base):
    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StudySessionORM(Base):
    __tablename__ = "study_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"))
    log_date: Mapped[date_] = mapped_column(Date, nullable=False)
    planned_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UrgeLogORM(Base):
    __tablename__ = "urge_logs"
    __table_args__ = (CheckConstraint("outcome in ('resisted', 'relapsed')", name="urge_logs_outcome_check"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    log_date: Mapped[date_] = mapped_column(Date, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    intensity: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    trigger_context_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    coping_strategy_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    note_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoalORM(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IntentionORM(Base):
    __tablename__ = "implementation_intentions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    linked_domain: Mapped[str] = mapped_column(Text, nullable=False)
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    cue: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LlmUsageORM(Base):
    __tablename__ = "llm_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", "feature", name="llm_usage_user_day_feature"),
        CheckConstraint("feature in ('chat', 'retro', 'insight', 'tasks')", name="llm_usage_feature_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    usage_date: Mapped[date_] = mapped_column(Date, nullable=False)
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
class PauseORM(Base):
    __tablename__ = "pauses"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    start_date: Mapped[date_] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_] = mapped_column(Date, nullable=False)
    habit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("habit_definitions.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TaskORM(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_has_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repeat_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nudge_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_nudged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    done_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_parsed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationPrefsORM(Base):
    __tablename__ = "notification_prefs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True
    )
    push_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiet_start: Mapped[time_] = mapped_column(Time, nullable=False)
    quiet_end: Mapped[time_] = mapped_column(Time, nullable=False)
    nudge_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=18)
    max_per_day: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=4)
    pushes_sent_day: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    pushes_sent: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PushSubscriptionORM(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint", name="push_subscriptions_endpoint_key"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    fail_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class ChatThreadORM(Base):
    __tablename__ = "chat_threads"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    title_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatMessageORM(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"))
    thread_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("chat_threads.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    next_step_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)





