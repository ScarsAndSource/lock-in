from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from app.deps import get_checkins_service, get_media_service, get_profile_service
from app.ratelimit import rate_limit
from app.routers.mappers import (
    bounce_out, entry_out, mood_out, screen_out, screen_proposal_out, sleep_out, sleep_proposal_out,
)
from app.safety import is_crisis, support_payload
from app.schemas import (
    CheckinConfirmOut, CheckinConfirmRequest, CheckinViewOut, JournalOut,
    ScreenTimeSectionOut, SleepSectionOut,
)
from app.schemas_media import (
    CheckinParseRequest, CheckinProposalOut, ParsedHabitOut, ParsedMoodOut, ParsedSleepOut,
)
from app.security import get_current_user_id
from app.services.media_service import MAX_AUDIO_BYTES, CheckinProposal, MediaService
from app.services.checkins_service import CheckinsService, ScreenTimeInput, SleepInput
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/checkins", tags=["checkins"], dependencies=[Depends(rate_limit("api"))])
_media_minute = rate_limit("media_minute", limit_setting="rate_limit_media_per_minute")
_media_hour = rate_limit("media_hour", limit_setting="rate_limit_media_per_hour", window_seconds=3600)


def _proposal_out(p: CheckinProposal) -> CheckinProposalOut:
    c = p.parsed
    return CheckinProposalOut(
        transcript=p.transcript,
        habits=[ParsedHabitOut(habit_id=h, status=s.value) for h, s in c.habits.items()],
        sleep=ParsedSleepOut(time_to_bed=c.sleep.time_to_bed, time_woke=c.sleep.time_woke,
                             self_rated_quality=c.sleep.quality) if c.sleep else None,
        screen_time_minutes=c.screen_time_minutes,
        mood=ParsedMoodOut(valence=c.mood.valence, energy=c.mood.energy) if c.mood else None,
        journal=c.journal, empty=c.is_empty, support=p.support,
    )


@router.post("/parse", response_model=CheckinProposalOut, dependencies=[Depends(_media_minute), Depends(_media_hour)])
async def parse_typed_checkin(
    body: CheckinParseRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: MediaService = Depends(get_media_service),
) -> CheckinProposalOut:
    """Typed (or dictated-by-the-keyboard) check-in -> a proposal. Saves nothing."""
    return _proposal_out(await service.parse_text(user_id, body.text))


@router.post("/voice", response_model=CheckinProposalOut, dependencies=[Depends(_media_minute), Depends(_media_hour)])
async def parse_voice_checkin(
    audio: UploadFile = File(...),
    user_id: UUID = Depends(get_current_user_id),
    service: MediaService = Depends(get_media_service),
) -> CheckinProposalOut:
    """A short recording -> transcript -> proposal. The audio is read (capped), used once and never stored."""
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    return _proposal_out(await service.parse_audio(user_id, data, audio.content_type or ""))



@router.get("/{checkin_date}/defaults", response_model=CheckinViewOut)
async def get_checkin_defaults(
    checkin_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
    profiles: ProfileService = Depends(get_profile_service),
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
        bounce=bounce_out(view.bounce, (await profiles.get(user_id)).tone_preference),
        mood=mood_out(view.mood_log),
    )


@router.post("/{checkin_date}/confirm", response_model=CheckinConfirmOut)
async def confirm_checkin(
    checkin_date: date,
    body: CheckinConfirmRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
    profiles: ProfileService = Depends(get_profile_service),
) -> CheckinConfirmOut:
    result = await service.confirm(
        user_id,
        checkin_date,
        overrides={o.habit_id: (o.status, o.note) for o in body.overrides},
        journal_text=body.journal_text,
        sleep=SleepInput(body.sleep.time_to_bed, body.sleep.time_woke, body.sleep.self_rated_quality)
        if body.sleep
        else None,
        screen_time=ScreenTimeInput(
            body.screen_time.total_minutes, body.screen_time.source, body.screen_time.category_breakdown
        )
        if body.screen_time
        else None,
        mood=(body.mood.valence, body.mood.energy) if body.mood else None,
        accept_sleep_default=body.accept_sleep_default,
        accept_screen_time_default=body.accept_screen_time_default,
    )
    texts = [body.journal_text, *(o.note for o in body.overrides)]
    support = None
    if any(t and is_crisis(t) for t in texts):
        support = support_payload((await profiles.get(user_id)).timezone)
    # the save already went through
    return CheckinConfirmOut(
        checkin_date=checkin_date,
        confirmed_at=result.confirmed_at,
        entries=[entry_out(e) for e in result.entries],
        sleep=sleep_out(result.sleep_log),
        screen_time=screen_out(result.screen_log),
        mood=mood_out(result.mood_log),
        support=support,
    )



@router.get("/{checkin_date}/journal", response_model=JournalOut)
async def get_journal(
    checkin_date: date,
    user_id: UUID = Depends(get_current_user_id),
    service: CheckinsService = Depends(get_checkins_service),
) -> JournalOut:
    return JournalOut(checkin_date=checkin_date, journal_text=await service.get_journal(user_id, checkin_date))
