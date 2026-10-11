from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.deps import get_pause_shortcuts_service, get_profile_service
from app.ratelimit import rate_limit
from app.routers.pauses import _out as pause_out
from app.schemas_friction import PauseOut
from app.schemas_pause_shortcuts import (
    HabitPauseRowOut,
    PauseOverviewOut,
    PauseShortcutOut,
    QuickPauseRequest,
    ResumeOut,
    ResumeRequest,
)
from app.security import get_current_user_id
from app.services.pause_shortcuts_service import PauseShortcutsService
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/pauses", tags=["pause-shortcuts"], dependencies=[Depends(rate_limit("api"))])


@router.get("/shortcuts", response_model=list[PauseShortcutOut])
async def pause_shortcuts(
    user_id: UUID = Depends(get_current_user_id),
    service: PauseShortcutsService = Depends(get_pause_shortcuts_service),
) -> list[PauseShortcutOut]:
    """Preset buttons with their dates, computed from your local today (Just today, 3 days, Until Sunday...)."""
    return [
        PauseShortcutOut(key=s.key, label=s.label, start_date=s.start_date, end_date=s.end_date, days=s.days)
        for s in await service.shortcuts(user_id)
    ]


@router.get("/habits", response_model=PauseOverviewOut)
async def pause_overview(
    user_id: UUID = Depends(get_current_user_id),
    service: PauseShortcutsService = Depends(get_pause_shortcuts_service),
) -> PauseOverviewOut:
    """Every active habit's pause state in one call: the whole habit page, no N+1."""
    o = await service.overview(user_id)
    wrap = lambda p: pause_out(p, o.today) if p else None  # noqa: E731
    return PauseOverviewOut(
        today=o.today,
        global_pause=wrap(o.global_pause),
        habits=[
            HabitPauseRowOut(
                habit_id=r.habit_id,
                name=r.name,
                state=r.state,
                effective_paused=r.effective_paused,
                paused_by=r.paused_by,
                pause=wrap(r.pause),
            )
            for r in o.habits
        ],
    )


@router.post("/quick", response_model=PauseOut)
async def quick_pause(
    body: QuickPauseRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: PauseShortcutsService = Depends(get_pause_shortcuts_service),
    profiles: ProfileService = Depends(get_profile_service),
) -> PauseOut:
    """One tap. Tapping a longer preset while paused EXTENDS the running pause; a shorter one changes nothing."""
    pause = await service.quick(user_id, body.preset, body.habit_id)
    return pause_out(pause, await profiles.today(user_id))


@router.post("/resume", response_model=ResumeOut)
async def resume_pause(
    body: ResumeRequest,
    user_id: UUID = Depends(get_current_user_id),
    service: PauseShortcutsService = Depends(get_pause_shortcuts_service),
) -> ResumeOut:
    """Count today again. still_paused_by_all=true means a global pause is still covering this habit."""
    resumed, still_all = await service.resume(user_id, body.habit_id)
    return ResumeOut(resumed=resumed, still_paused_by_all=still_all)
