from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_account_service, get_profile_service
from app.ratelimit import rate_limit
from app.schemas import DeleteAccountRequest, ProfileOut, ProfilePatchRequest
from app.security import get_current_user_id
from app.services.account_service import AccountService
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/me", tags=["account"], dependencies=[Depends(rate_limit("api"))])
_heavy_limit = rate_limit("heavy", limit_setting="rate_limit_export_per_hour", window_seconds=3600)


async def _profile_out(service: ProfileService, user_id: UUID) -> ProfileOut:
    profile = await service.get(user_id)
    return ProfileOut(timezone=profile.timezone, tone_preference=profile.tone_preference, today=await service.today(user_id))


@router.get("", response_model=ProfileOut)
async def get_me(
    user_id: UUID = Depends(get_current_user_id),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileOut:
    """Clients should use `today` (the user's local date) instead of guessing from the device clock."""
    return await _profile_out(service, user_id)


@router.patch("", response_model=ProfileOut)
async def patch_me(
    body: ProfilePatchRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: ProfileService = Depends(get_profile_service),
) -> ProfileOut:
    await service.set_timezone(user_id, body.timezone)
    return await _profile_out(service, user_id)


@router.get("/export", dependencies=[Depends(_heavy_limit)])
async def export_my_data(
    user_id: UUID = Depends(get_current_user_id),
    service: AccountService = Depends(get_account_service),
) -> dict:
    """Everything stored about you, journals decrypted."""
    return await service.export(user_id)


@router.delete("", dependencies=[Depends(_heavy_limit)])
async def delete_my_data(
    body: DeleteAccountRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: AccountService = Depends(get_account_service),
) -> dict:
    """
    Irreversibly deletes all app data (body must be {"confirm": "DELETE MY DATA"}).
    The Supabase login itself lives in auth.users and needs the Supabase admin
    API/dashboard -- this app deliberately holds no service-role key.
    """
    return {"deleted": await service.delete_everything(user_id)}
