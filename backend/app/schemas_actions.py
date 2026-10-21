from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TokenActionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32, pattern=r"^[a-z_]+$")


class InAppActionRequest(BaseModel):
    kind: Literal["task", "checkin", "habit", "risk", "winddown", "study", "insight"]
    action: str = Field(min_length=1, max_length=32, pattern=r"^[a-z_]+$")
    args: dict[str, str] = Field(default_factory=dict, max_length=6)


class ActionOut(BaseModel):
    status: Literal["done", "already", "failed"]
    message: str
