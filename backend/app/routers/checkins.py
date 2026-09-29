from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_checkins_service
from app.exceptions import NotFoundError
from app.schemas import (
    CheckinConfirmOut,
    CheckinConfirmRequest,
    CheckinEntryOut,
    CheckinViewOut,
)
from app.security import get_current_user_id
from app.services.checkins_service import CheckinsService

router = APIRouter(prefix="/checkins", tags=["checkins"])


@router.get("/{checkin_date}/defaults", response_model=CheckinViewOut)
async def get_checkin_defaults(
    checkin_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
) -> CheckinViewOut:
    entries, already_confirmed = await service.get_view(user_id, checkin_date)
    return CheckinViewOut(
        checkin_date=checkin_date,
        already_confirmed=already_confirmed,
        entries=[
            CheckinEntryOut(
                habit_id=e.habit_id, habit_name=e.habit_name, status=e.status,
                is_default=e.is_default, is_low_confidence=e.is_low_confidence,
                reason=e.reason,
            )
            for e in entries
        ],
    )


@router.post("/{checkin_date}/confirm", response_model=CheckinConfirmOut)
async def confirm_checkin(
    checkin_date: date,
    body: CheckinConfirmRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
) -> CheckinConfirmOut:
    overrides = {o.habit_id: (o.status, o.note) for o in body.overrides}

    try:
        entries = await service.confirm(user_id, checkin_date, overrides, body.journal_text)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return CheckinConfirmOut(
        checkin_date=checkin_date,
        confirmed_at=datetime.now(timezone.utc),
        entries=[
            CheckinEntryOut(
                habit_id=e.habit_id, habit_name=e.habit_name, status=e.status,
                is_default=e.is_default, is_low_confidence=e.is_low_confidence,
                reason=e.reason,
            )
            for e in entries
        ],
    )
