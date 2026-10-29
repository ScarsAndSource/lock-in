from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SupportResourceOut(BaseModel):
    name: str
    contact: str
    detail: str


class SupportOut(BaseModel):
    region: str
    message: str
    resources: list[SupportResourceOut]
    verified_on: str


class ActionCardOut(BaseModel):
    """What the agent did (applied + signed undo token) or wants to do (pending + signed confirm token). Live replies only.
    The raw args / undo payload never leave the server: the client sends back the token and nothing else."""
    id: str
    tool: str
    status: Literal["applied", "pending", "failed"]
    summary: str
    reason: str | None = None
    token: str | None = None          # pending: POST to /chat/actions/confirm
    undo_token: str | None = None     # applied: POST to /chat/actions/undo


class ConfirmActionRequest(BaseModel):
    token: str = Field(min_length=1, max_length=8000)


class UndoActionRequest(BaseModel):
    token: str = Field(min_length=1, max_length=8000)


class UndoOut(BaseModel):
    message: str
