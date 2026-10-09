from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.domain import GoalStatus, UrgeOutcome

Domain = Literal["habit", "screen_time", "urge", "study", "sleep"]


# ---------------------------------------------------------------- study
class SubjectCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]


class SubjectBulkRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=2000)]   # "ADS, AISC, CN"


class SubjectPatchRequest(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=80)] = None
    archived: bool | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "SubjectPatchRequest":
        if self.name is None and self.archived is None:
            raise ValueError("Provide at least one of: name, archived")
        return self


class SubjectOut(BaseModel):
    id: UUID
    name: str
    archived_at: datetime | None


class StudySessionRequest(BaseModel):
    log_date: date
    subject_id: UUID | None = None
    subject_name: Annotated[str | None, Field(min_length=1, max_length=80)] = None
    planned_minutes: Annotated[int | None, Field(ge=1, le=1440)] = None
    actual_minutes: Annotated[int, Field(ge=0, le=1440)]

    @model_validator(mode="after")
    def _one_subject_ref(self) -> "StudySessionRequest":
        if (self.subject_id is None) == (self.subject_name is None):
            raise ValueError("Give exactly one of subject_id or subject_name")
        return self


class StudySessionOut(BaseModel):
    id: UUID
    log_date: date
    subject_id: UUID
    subject_name: str
    planned_minutes: int | None
    actual_minutes: int


class SubjectMinutesOut(BaseModel):
    subject_id: UUID
    name: str
    minutes: int


class StudySummaryOut(BaseModel):
    start_date: date
    end_date: date
    total_actual: int
    total_planned: int
    follow_through_pct: float | None
    days_studied: int
    by_subject: list[SubjectMinutesOut]


# ---------------------------------------------------------------- urges
class UrgeCaptureRequest(BaseModel):
    """{"outcome": "resisted"} alone is a complete, valid log."""
    outcome: UrgeOutcome
    occurred_at: datetime | None = None
    intensity: Annotated[int | None, Field(ge=1, le=10)] = None
    trigger_context: Annotated[str | None, Field(max_length=500)] = None
    coping_strategy: Annotated[str | None, Field(max_length=300)] = None
    note: Annotated[str | None, Field(max_length=2000)] = None


class UrgeDetailRequest(BaseModel):
    """PATCH: only fields actually sent are applied. null or "" clears a field."""
    intensity: Annotated[int | None, Field(ge=1, le=10)] = None
    trigger_context: Annotated[str | None, Field(max_length=500)] = None
    coping_strategy: Annotated[str | None, Field(max_length=300)] = None
    note: Annotated[str | None, Field(max_length=2000)] = None

    @model_validator(mode="after")
    def _something_sent(self) -> "UrgeDetailRequest":
        if not self.model_fields_set:
            raise ValueError("Send at least one field")
        return self


class UrgeOut(BaseModel):
    id: UUID
    occurred_at: datetime
    log_date: date
    outcome: UrgeOutcome
    intensity: int | None
    has_detail: bool
    trigger_context: str | None = None   # only filled when details were requested / just written
    coping_strategy: str | None = None
    note: str | None = None


class UrgeSummaryOut(BaseModel):
    end_date: date
    window_days: int
    total: int
    resisted: int
    relapsed: int
    resist_rate_pct: float | None
    relapse_free_days_pct: float | None
    prev_resist_rate_pct: float | None


# ---------------------------------------------------------------- goals / intentions
class GoalCreateRequest(BaseModel):
    domain: Domain
    definition: Annotated[str, Field(min_length=1, max_length=200)]
    target: dict   # shape per domain, validated in services/goal_targets.py


class GoalPatchRequest(BaseModel):
    definition: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    status: GoalStatus | None = None
    target: dict | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "GoalPatchRequest":
        if self.definition is None and self.status is None and self.target is None:
            raise ValueError("Provide at least one of: definition, status, target")
        return self


class GoalOut(BaseModel):
    id: UUID
    domain: str
    definition: str
    target: dict
    status: GoalStatus
    created_at: datetime


class GoalProgressOut(BaseModel):
    goal: GoalOut
    current: float | None
    target_value: float
    unit: str
    on_track: bool | None
    detail: str


class IntentionCreateRequest(BaseModel):
    linked_domain: Domain
    linked_entity_id: UUID | None = None
    cue: Annotated[str, Field(min_length=1, max_length=200)]
    action: Annotated[str, Field(min_length=1, max_length=200)]


class IntentionPatchRequest(BaseModel):
    cue: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    action: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    active: bool | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "IntentionPatchRequest":
        if self.cue is None and self.action is None and self.active is None:
            raise ValueError("Provide at least one of: cue, action, active")
        return self


class IntentionOut(BaseModel):
    id: UUID
    linked_domain: str
    linked_entity_id: UUID | None
    cue: str
    action: str
    active: bool
    created_at: datetime


class DueIntentionOut(BaseModel):
    intention: IntentionOut
    level: Literal["full", "light"]
    reason: str
