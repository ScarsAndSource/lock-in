from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.deps import get_stats_service
from app.ratelimit import rate_limit
from app.routers.mappers import consistency_out
from app.schemas import ChainDayOut, ChainOut, ConsistencyOut, PatternOut, PatternsOut
from app.security import get_current_user_id
from app.services.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(rate_limit("api"))])


@router.get("/consistency", response_model=ConsistencyOut)
async def get_consistency(
    end_date: date | None = Query(None, description="Defaults to today in the user's timezone."),
    window_days: int = Query(30, ge=7, le=90),
    user_id: UUID = Depends(get_current_user_id),
    service: StatsService = Depends(get_stats_service),
) -> ConsistencyOut:
    end, items, overall = await service.consistency(user_id, end_date, window_days)
    return ConsistencyOut(
        end_date=end, window_days=window_days, overall_pct=overall,
        habits=[consistency_out(i) for i in items],
    )


@router.get("/chain", response_model=ChainOut)
async def get_chain(
    end_date: date | None = Query(None),
    days: int = Query(14, ge=3, le=60),
    user_id: UUID = Depends(get_current_user_id),
    service: StatsService = Depends(get_stats_service),
) -> ChainOut:
    end, chain = await service.chain(user_id, end_date, days)
    return ChainOut(end_date=end, days=[
        ChainDayOut(
            day=d.day, habits=d.habits, sleep=d.sleep, screen_time=d.screen_time, habit_ratio=d.habit_ratio,
            sleep_minutes=d.sleep_minutes, screen_minutes=d.screen_minutes,
            sleep_defaulted=d.sleep_defaulted, screen_time_defaulted=d.screen_time_defaulted,
        ) for d in chain
    ])


@router.get("/patterns", response_model=PatternsOut)
async def get_patterns(
    end_date: date | None = Query(None),
    days: int = Query(30, ge=14, le=90),
    user_id: UUID = Depends(get_current_user_id),
    service: StatsService = Depends(get_stats_service),
) -> PatternsOut:
    end, patterns = await service.patterns(user_id, end_date, days)
    return PatternsOut(end_date=end, days=days, patterns=[
        PatternOut(
            key=p.key, trigger=p.trigger, outcome=p.outcome, lag_days=p.lag_days,
            trigger_days=p.trigger_days, hits=p.hits, rate_after_trigger=p.rate_after_trigger,
            baseline_days=p.baseline_days, baseline_rate=p.baseline_rate,
            evidence_dates=p.evidence_dates, statement=p.statement,
        ) for p in patterns
    ])
