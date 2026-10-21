from __future__ import annotations

from datetime import date as Date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class IngestTokenCreate(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=40)]


class IngestTokenOut(BaseModel):
    id: UUID
    label: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class IngestTokenCreated(IngestTokenOut):
    token: str   # shown once. Put it in the automation's Authorization header: "Bearer <token>"


class IngestEvent(BaseModel):
    kind: Literal["sleep_start", "sleep_end", "screen_time"]
    at: datetime | None = None                       # when it happened (with offset); default: now
    minutes: Annotated[int | None, Field(ge=0, le=1440)] = None
    date: Date | None = None                         # screen_time only: which day the total is for


class IngestOut(BaseModel):
    ok: bool = True
    kind: str
    date: Date
    message: str
