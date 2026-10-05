from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_checkins_service
from app.ratelimit import rate_limit
from app.routers.mappers import (
    entry_out, screen_out, screen_proposal_out, sleep_out, sleep_proposal_out,
)
from app.schemas import (
    CheckinConfirmOut, CheckinConfirmRequest, CheckinViewOut, JournalOut,
    ScreenTimeSectionOut, SleepSectionOut,
)
from app.security import get_current_user_id
from app.services.checkins_service import CheckinsService, ScreenTimeInput, SleepInput

router = APIRouter(prefix="/checkins", tags=["checkins"], dependencies=[Depends(rate_limit("api"))])


@router.get("/{checkin_date}/defaults", response_model=CheckinViewOut)
async def get_checkin_defaults(
    checkin_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
) -> CheckinViewOut:
    view = await service.get_view(user_id, checkin_date)
    return CheckinViewOut(
        checkin_date=checkin_date,
        already_confirmed=view.already_confirmed,
        entries=[entry_out(e) for e in view.entries],
        sleep=SleepSectionOut(logged=sleep_out(view.sleep_log), proposal=sleep_proposal_out(view.sleep_proposal)),
        screen_time=ScreenTimeSectionOut(
            logged=screen_out(view.screen_log), proposal=screen_proposal_out(view.screen_proposal)
        ),
    )


@router.post("/{checkin_date}/confirm", response_model=CheckinConfirmOut)
async def confirm_checkin(
    checkin_date: date,
    body: CheckinConfirmRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
) -> CheckinConfirmOut:
    result = await service.confirm(
        user_id, checkin_date,
        overrides={o.habit_id: (o.status, o.note) for o in body.overrides},
        journal_text=body.journal_text,
        sleep=SleepInput(body.sleep.time_to_bed, body.sleep.time_woke, body.sleep.self_rated_quality)
        if body.sleep else None,
        screen_time=ScreenTimeInput(body.screen_time.total_minutes, body.screen_time.source, body.screen_time.category_breakdown)
        if body.screen_time else None,
        accept_sleep_default=body.accept_sleep_default,
        accept_screen_time_default=body.accept_screen_time_default,
    )
    return CheckinConfirmOut(
        checkin_date=checkin_date,
        confirmed_at=result.confirmed_at,
        entries=[entry_out(e) for e in result.entries],
        sleep=sleep_out(result.sleep_log),
        screen_time=screen_out(result.screen_log),
    )


@router.get("/{checkin_date}/journal", response_model=JournalOut)
async def get_journal(
    checkin_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
) -> JournalOut:
    return JournalOut(checkin_date=checkin_date, journal_text=await service.get_journal(user_id, checkin_date))
