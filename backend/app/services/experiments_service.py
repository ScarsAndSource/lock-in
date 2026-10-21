from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain_experiments import METRICS, Experiment, ExperimentView, MetricSpec, Verdict
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories.experiment_repository import ExperimentRepository
from app.services.chain_service import ChainDay
from app.services.experiments import (
    MIN_BASELINE, build_points, evaluate, metric_value, progress, values,
)
from app.services.profile_service import ProfileService
from app.services.stats_service import StatsService

_AVAILABILITY_DAYS = 30


class ExperimentsService:
    def __init__(
        self, repo: ExperimentRepository, stats: StatsService, profiles: ProfileService, clock: Clock = utc_now
    ):
        self._repo = repo
        self._stats = stats
        self._profiles = profiles
        self._clock = clock

    # ---- reads
    async def metrics(self, user_id: UUID) -> list[tuple[MetricSpec, int]]:
        """Each metric with how many real readings the last 30 days hold, so the UI can grey out the empty ones."""
        today = await self._profiles.today(user_id)
        days = await self._chain(user_id, today - timedelta(days=_AVAILABILITY_DAYS - 1), today)
        return [
            (spec, sum(1 for d in days if metric_value(d, spec.key) is not None)) for spec in METRICS.values()
        ]

    async def get_active(self, user_id: UUID) -> ExperimentView | None:
        exp = await self._repo.get_active(user_id)
        if exp is None:
            return None
        return await self._view(user_id, exp, await self._profiles.today(user_id), with_points=True)

    async def get(self, user_id: UUID, exp_id: UUID) -> ExperimentView:
        exp = await self._repo.get(user_id, exp_id)
        if exp is None:
            raise NotFoundError("No such experiment.")
        return await self._view(user_id, exp, await self._profiles.today(user_id), with_points=True)

    async def list_recent(self, user_id: UUID, limit: int = 20) -> list[ExperimentView]:
        today = await self._profiles.today(user_id)
        exps = await self._repo.list_recent(user_id, max(1, min(limit, 50)))
        return [await self._view(user_id, e, today, with_points=False) for e in exps]

    # ---- writes
    async def start(
        self,
        user_id: UUID,
        *,
        title: str,
        change: str,
        metric: str,
        direction: str | None,
        baseline_days: int,
        treatment_days: int,
        start: str,
    ) -> ExperimentView:
        spec = METRICS.get(metric)
        if spec is None:
            raise ValidationError("Unknown metric.")
        title, change = title.strip(), change.strip()
        if not title or not change:
            raise ValidationError("Say what you're changing.")
        if start not in ("today", "tomorrow"):
            raise ValidationError("start must be 'today' or 'tomorrow'.")
        if await self._repo.get_active(user_id) is not None:
            raise ConflictError("You already have an experiment running. Finish it or drop it first.")

        today = await self._profiles.today(user_id)
        start_date = today if start == "today" else today + timedelta(days=1)

        # Honesty gate: with nothing to compare against, a verdict later would be noise dressed up as a result.
        baseline_start = start_date - timedelta(days=baseline_days)
        days = await self._chain(user_id, baseline_start, start_date - timedelta(days=1))
        usable = sum(1 for d in days if metric_value(d, metric) is not None)
        if usable < MIN_BASELINE:
            raise ValidationError(
                f"Only {usable} days of {spec.label.lower()} logged in the last {baseline_days}. "
                f"Log at least {MIN_BASELINE} so there's something to compare against."
            )

        now = self._clock()
        exp = Experiment(
            id=uuid4(), user_id=user_id, title=title, change=change, metric=metric,
            direction=direction or spec.better, baseline_days=baseline_days, treatment_days=treatment_days,
            start_date=start_date, status="active", result=None, created_at=now, updated_at=now,
        )
        created = await self._repo.create(exp)
        return await self._view(user_id, created, today, with_points=True)

    async def finish(self, user_id: UUID, exp_id: UUID, adherence: str) -> ExperimentView:
        if adherence not in ("mostly", "partly", "barely"):
            raise ValidationError("adherence must be mostly, partly or barely.")
        exp = await self._repo.get(user_id, exp_id)
        if exp is None:
            raise NotFoundError("No such experiment.")
        if exp.status != "active":
            raise ConflictError("This experiment is already closed.")
        today = await self._profiles.today(user_id)
        if today < exp.start_date:
            raise ValidationError("It hasn't started yet. Drop it instead.")

        points = await self._points(user_id, exp, today)
        verdict = self._verdict(exp, points, adherence)
        result = verdict.to_dict()
        result["adherence"] = adherence
        result["finished_on"] = today.isoformat()

        closed = await self._repo.close(user_id, exp_id, "done", result, self._clock())
        if closed is None:
            raise ConflictError("This experiment is already closed.")
        return await self._view(user_id, closed, today, with_points=True)

    async def abandon(self, user_id: UUID, exp_id: UUID) -> None:
        exp = await self._repo.get(user_id, exp_id)
        if exp is None:
            raise NotFoundError("No such experiment.")
        if await self._repo.close(user_id, exp_id, "abandoned", None, self._clock()) is None:
            raise ConflictError("This experiment is already closed.")

    # ---- internals
    async def _chain(self, user_id: UUID, start: date, end: date) -> list[ChainDay]:
        if end < start:
            return []
        _, days = await self._stats.chain(user_id, end, (end - start).days + 1)
        return days

    async def _points(self, user_id: UUID, exp: Experiment, today: date):
        last = min(today, exp.end_date)
        if last < exp.baseline_start:
            return []
        days = await self._chain(user_id, exp.baseline_start, last)
        return build_points(days, exp.metric, exp.baseline_start, exp.start_date, exp.end_date)

    @staticmethod
    def _verdict(exp: Experiment, points, adherence: str | None = None) -> Verdict:
        return evaluate(
            exp.metric, exp.direction, values(points, "baseline"), values(points, "test"),
            adherence=adherence, seed=exp.id.int & 0xFFFFFFFF,
        )

    async def _view(self, user_id: UUID, exp: Experiment, today: date, *, with_points: bool) -> ExperimentView:
        phase, day_number, days_left = progress(exp.start_date, exp.treatment_days, today)

        if exp.status == "abandoned":
            return ExperimentView(exp, phase, day_number, days_left)

        if exp.status == "done":
            verdict = Verdict.from_dict(exp.result) if exp.result else None
            points = await self._points(user_id, exp, today) if with_points else []
            return ExperimentView(exp, "complete", exp.treatment_days, 0, points, verdict, provisional=False)

        # active: a live preview, labelled provisional until the test window is over
        if phase == "waiting":
            points = await self._points(user_id, exp, today) if with_points else []
            return ExperimentView(exp, phase, day_number, days_left, points, None, provisional=True)
        if not with_points:
            return ExperimentView(exp, phase, day_number, days_left)
        points = await self._points(user_id, exp, today)
        return ExperimentView(
            exp, phase, day_number, days_left, points, self._verdict(exp, points), provisional=phase != "complete"
        )
