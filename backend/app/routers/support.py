from __future__ import annotations

from fastapi import APIRouter, Query

from app.safety import support_payload
from app.schemas_chat import SupportOut

router = APIRouter(prefix="/support", tags=["support"])


@router.get("/resources", response_model=SupportOut)
async def support_resources(
    region: str | None = Query(None, pattern="^[A-Za-z]{2}$", description="ISO country code, e.g. IN"),
    timezone: str | None = Query(None, max_length=64, description="IANA name, e.g. Asia/Kolkata; picks the region when none is given"),
) -> SupportOut:
    """No auth, no user data: static resources, safe to call from anywhere in the app."""
    return SupportOut.model_validate(support_payload(timezone=timezone, region=region))
