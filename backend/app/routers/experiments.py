from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from app.deps import get_experiments_service
from app.domain_experiments import METRICS, ExperimentView
from app.ratelimit import rate_limit
from app.schemas_experiments import (
    ExperimentFinishIn, ExperimentOut, ExperimentStartIn, MetricOut, PointOut, VerdictOut,
)
from app.security import get_current_user_id
from app.services.experiments_service import ExperimentsService

router = APIRouter(prefix="/experiments", tags=["experiments"], dependencies=[Depends(rate_limit("api"))])


def _out(view: ExperimentView) -> ExperimentOut:
    e = view.experiment
    spec = METRICS[e.metric]
    verdict = None
    if view.verdict is not None:
        v = view.verdict
        verdict = VerdictOut(
            kind=v.kind, sentence=v.sentence, n_baseline=v.n_baseline, n_treatment=v.n_treatment,
            baseline_mean=v.baseline_mean, treatment_mean=v.treatment_mean, delta=v.delta,
            p_value=v.p_value, effect_size=v.effect_size, caveats=list(v.caveats),
        )
    return ExperimentOut(
        id=str(e.id), title=e.title, change=e.change, metric=e.metric, metric_label=spec.label, unit=spec.unit,
        direction=e.direction, status=e.status, start_date=e.start_date, end_date=e.end_date,
        baseline_days=e.baseline_days, treatment_days=e.treatment_days, phase=view.phase,
        day_number=view.day_number, days_left=view.days_left, provisional=view.provisional, verdict=verdict,
        points=[
            PointOut(day=p.day, value=round(p.value, 2) if p.value is not None else None, phase=p.phase)
            for p in view.points
        ],
    )


# Fixed paths first so "/metrics" and "/active" are never read as an experiment id.
@router.get("/metrics", response_model=list[MetricOut])
async def list_metrics(
    user_id: UUID = Depends(get_current_user_id),
    service: ExperimentsService = Depends(get_experiments_service),
) -> list[MetricOut]:
    return [
        MetricOut(key=s.key, label=s.label, unit=s.unit, better=s.better, usable_days=n)
        for s, n in await service.metrics(user_id)
    ]


@router.get("/active", response_model=ExperimentOut | None)
async def get_active(
    user_id: UUID = Depends(get_current_user_id),
    service: ExperimentsService = Depends(get_experiments_service),
) -> ExperimentOut | None:
    view = await service.get_active(user_id)
    return _out(view) if view else None


@router.get("", response_model=list[ExperimentOut])
async def list_experiments(
    limit: int = Query(20, ge=1, le=50),
    user_id: UUID = Depends(get_current_user_id),
    service: ExperimentsService = Depends(get_experiments_service),
) -> list[ExperimentOut]:
    return [_out(v) for v in await service.list_recent(user_id, limit)]


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
async def start_experiment(
    body: ExperimentStartIn,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperimentsService = Depends(get_experiments_service),
) -> ExperimentOut:
    view = await service.start(
        user_id, title=body.title, change=body.change, metric=body.metric, direction=body.direction,
        baseline_days=body.baseline_days, treatment_days=body.treatment_days, start=body.start,
    )
    return _out(view)


@router.get("/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(
    experiment_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperimentsService = Depends(get_experiments_service),
) -> ExperimentOut:
    return _out(await service.get(user_id, experiment_id))


@router.post("/{experiment_id}/finish", response_model=ExperimentOut)
async def finish_experiment(
    experiment_id: UUID,
    body: ExperimentFinishIn,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperimentsService = Depends(get_experiments_service),
) -> ExperimentOut:
    return _out(await service.finish(user_id, experiment_id, body.adherence))


@router.post("/{experiment_id}/abandon", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def abandon_experiment(
    experiment_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    service: ExperimentsService = Depends(get_experiments_service),
) -> Response:
    await service.abandon(user_id, experiment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
