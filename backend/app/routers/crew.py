from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.deps import get_crew_service
from app.ratelimit import rate_limit
from app.schemas_crew import (
    BoostIn, CheerIn, CloseWeekIn, CodeIn, CrewCreateIn, JoinIn, QuietIn, RespondIn, ShareIn, UsernameIn,
)
from app.security import get_current_user_id
from app.schemas_crew import BuddyIn, DuelIn, GoalIn
from app.services.crew_service import CrewService

router = APIRouter(prefix="/crew", tags=["crew"], dependencies=[Depends(rate_limit("api"))])

# Exact-username lookups and code guesses are the only enumeration surface: keep them tight.
_lookup = Depends(rate_limit("crew_lookup", limit_setting="rate_limit_crew_lookup_per_hour", window_seconds=3600))
_code = Depends(rate_limit("crew_code", limit_setting="rate_limit_crew_code_per_hour", window_seconds=3600))


@router.get("/overview")
async def overview(service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.overview()


@router.put("/username", dependencies=[_lookup])
async def set_username(body: UsernameIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.set_username(body.username)


@router.put("/share")
async def set_share(body: ShareIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.set_share(body.model_dump())


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_crew(body: CrewCreateIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.create(body.name)


@router.post("/join", dependencies=[_code])
async def join(body: JoinIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.join(body.code)


@router.post("/blocks", dependencies=[_lookup])
async def block(body: UsernameIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.block(body.username)


@router.delete("/blocks/{username}")
async def unblock(username: str, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.unblock(username)


@router.get("/week")
async def week(user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.week_info(user_id)


@router.post("/week/close")
async def close_week(
    body: CloseWeekIn, user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.close_week(user_id, body.proud, body.focus, body.habits)


@router.get("/inbox")
async def inbox(service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.inbox()


@router.post("/inbox/seen")
async def inbox_seen(service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.inbox_seen()


@router.post("/{crew_id}/invite", dependencies=[_lookup])
async def invite(crew_id: UUID, body: UsernameIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.invite(crew_id, body.username)


@router.post("/{crew_id}/respond")
async def respond(crew_id: UUID, body: RespondIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.respond(crew_id, body.accept)


@router.post("/{crew_id}/code")
async def make_code(crew_id: UUID, body: CodeIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.make_code(crew_id, body.revoke)


@router.post("/{crew_id}/leave")
async def leave(crew_id: UUID, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.leave(crew_id)


@router.put("/{crew_id}/quiet")
async def quiet(crew_id: UUID, body: QuietIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.set_quiet(crew_id, body.quiet)


@router.get("/{crew_id}/card")
async def card(
    crew_id: UUID, week: date | None = Query(None),
    user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.card(user_id, crew_id, week)


@router.post("/{crew_id}/cheer")
async def cheer(crew_id: UUID, body: CheerIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.send_cheer(crew_id, body.to, body.kind)


@router.post("/{crew_id}/boost")
async def boost(crew_id: UUID, body: BoostIn, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.send_boost(crew_id, body.to)


# ---- crew goal
@router.get("/{crew_id}/goal")
async def get_goal(
    crew_id: UUID, user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.next_goal(user_id, crew_id)


@router.put("/{crew_id}/goal")
async def put_goal(
    crew_id: UUID, body: GoalIn, user_id: UUID = Depends(get_current_user_id),
    service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.set_goal(user_id, crew_id, body.hours)


# ---- buddy deals
@router.get("/buddy")
async def buddy_overview(
    user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.buddy_overview(user_id)


@router.post("/buddy", dependencies=[_lookup])
async def buddy_propose(
    body: BuddyIn, user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.buddy_propose(user_id, body.crew_id, body.to, body.threshold, body.message, body.auto_send)


@router.post("/buddy/{deal_id}/respond")
async def buddy_respond(
    deal_id: UUID, body: RespondIn, user_id: UUID = Depends(get_current_user_id),
    service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.buddy_respond(user_id, deal_id, body.accept)


@router.post("/buddy/{deal_id}/send")
async def buddy_send(
    deal_id: UUID, user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.buddy_send(user_id, deal_id)


@router.post("/buddy/{deal_id}/hold")
async def buddy_hold(
    deal_id: UUID, user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.buddy_hold(user_id, deal_id)


@router.delete("/buddy/{deal_id}")
async def buddy_cancel(deal_id: UUID, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.buddy_cancel(deal_id)


# ---- duels
@router.get("/duels")
async def duels(service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.duel_list()


@router.post("/duels", dependencies=[_lookup])
async def duel_propose(
    body: DuelIn, user_id: UUID = Depends(get_current_user_id), service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.duel_propose(user_id, body.crew_id, body.to)


@router.post("/duels/{duel_id}/respond")
async def duel_respond(
    duel_id: UUID, body: RespondIn, user_id: UUID = Depends(get_current_user_id),
    service: CrewService = Depends(get_crew_service),
) -> dict:
    return await service.duel_respond(user_id, duel_id, body.accept)


@router.delete("/duels/{duel_id}")
async def duel_cancel(duel_id: UUID, service: CrewService = Depends(get_crew_service)) -> dict:
    return await service.duel_cancel(duel_id)
