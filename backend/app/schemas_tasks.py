from __future__ import annotations

from datetime import datetime, time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

LocalWhen = Annotated[str, Field(min_length=10, max_length=16)]  # "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM", local time


class TaskCaptureRequest(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=1000)]


class TaskCreateRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    notes: Annotated[str | None, Field(max_length=500)] = None
    importance: Annotated[int, Field(ge=1, le=3)] = 2
    due: LocalWhen | None = None
    remind: LocalWhen | None = None
    repeat_days: Annotated[int | None, Field(ge=1, le=365)] = None


class TaskPatchRequest(BaseModel):
    """Only fields you send are changed. Send null for notes/due/remind/repeat_days to clear them."""
    title: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    notes: Annotated[str | None, Field(max_length=500)] = None
    importance: Annotated[int | None, Field(ge=1, le=3)] = None
    due: LocalWhen | None = None
    remind: LocalWhen | None = None
    repeat_days: Annotated[int | None, Field(ge=1, le=365)] = None
    status: Literal["open", "dropped"] | None = None

    @model_validator(mode="after")
    def _something(self) -> "TaskPatchRequest":
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        return self


class TaskSnoozeRequest(BaseModel):
    minutes: Annotated[int, Field(ge=5, le=10080)]


class TaskOut(BaseModel):
    id: UUID
    title: str
    notes: str | None
    importance: int
    status: str
    state: str                       # backlog | upcoming | due | stale | snoozed | done | dropped
    due: str | None                  # local "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM"
    due_has_time: bool
    remind: str | None
    repeat_days: int | None
    snoozed_until: datetime | None
    nudge_count: int
    last_done_at: datetime | None
    done_count: int
    ai_parsed: bool
    created_at: datetime


class CaptureOut(BaseModel):
    mode: Literal["parsed", "fallback", "support"]
    tasks: list[TaskOut]
    skipped_duplicates: int
    support: dict | None = None


class FocusOut(BaseModel):
    now: list[TaskOut]
    small: list[TaskOut]
    later_today: list[TaskOut]
    stale: list[TaskOut]
    hidden_now: int
    backlog_count: int


# ---------------------------------------------------------------- notifications
class NotificationPrefsOut(BaseModel):
    push_enabled: bool
    quiet_start: time
    quiet_end: time
    nudge_hour: int
    max_per_day: int
    devices: int
    push_available: bool            # false until VAPID keys are set on the server
    companion_enabled: bool = True
    checkin_hour: int = 21
    plan_cues_in_quiet: bool = False
    discreet_push: bool = True


class NotificationPrefsPatch(BaseModel):
    push_enabled: bool | None = None
    quiet_start: time | None = None
    quiet_end: time | None = None
    nudge_hour: Annotated[int | None, Field(ge=0, le=23)] = None
    max_per_day: Annotated[int | None, Field(ge=1, le=20)] = None
    companion_enabled: bool | None = None
    checkin_hour: Annotated[int | None, Field(ge=0, le=23)] = None
    plan_cues_in_quiet: bool | None = None
    discreet_push: bool | None = None

    @model_validator(mode="after")
    def _something(self) -> "NotificationPrefsPatch":
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        return self


class PushKeys(BaseModel):
    p256dh: Annotated[str, Field(min_length=20, max_length=200)]
    auth: Annotated[str, Field(min_length=8, max_length=100)]


class PushSubscribeRequest(BaseModel):
    endpoint: Annotated[str, Field(min_length=20, max_length=2000)]
    keys: PushKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: Annotated[str, Field(min_length=20, max_length=2000)]


class VapidKeyOut(BaseModel):
    public_key: str | None


class PushTestOut(BaseModel):
    delivered: int
