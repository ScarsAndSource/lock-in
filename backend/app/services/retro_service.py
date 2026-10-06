"""
Weekly retro: gather -> deterministic chain -> LLM narration (validated) -> store.

Same trust pipeline as insights: the model only narrates what retro_engine already
established, citing dates from the facts; anything that fails validation, or an LLM
outage, falls back to the deterministic chain text (narrated=False). The summary
stored with the retro is exactly the facts the model saw.

Closing the feedback loop: retro detail surfaces last week's UNRATED insights;
complete() marks the retro done and THEN attempts the insight refresh, so the user's
ratings are in before new insights are generated. A soft gate in InsightsService.refresh
skips with rate_previous_first when 3+ insights older than 7 days are still unrated.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import UUID, uuid4

from app.dates import Clock, utc_now
from app.domain import PatternInsight, WeeklyRetro
from app.exceptions import NotFoundError, ValidationError
from app.repositories.retro_repository import RetroRepository
from app.services.insights_service import InsightsService, RefreshResult
from app.services.llm import LLMClient, LLMError
from app.services.missions_service import MissionsService
from app.services.narration import narrate_structured, sanitize_user_text
from app.services.profile_service import ProfileService
from app.services.retro_engine import build_summary, fallback_narrative, week_bounds
from app.services.stats_service import StatsService
from app.services.study_service import StudyService
from app.services.urges_service import UrgesService
from app.voice_config import VOICE_VERSION, retro_system_prompt


class RetroService:
    def __init__(
        self,
        repo: RetroRepository,
        stats: StatsService,
        study: StudyService,
        urges: UrgesService,
        missions: MissionsService,
        insights: InsightsService,
        profiles: ProfileService,
        llm: LLMClient,
        clock: Clock = utc_now,
    ):
        self._repo = repo
        self._stats = stats
        self._study = study
        self._urges = urges
        self._missions = missions
        self._insights = insights
        self._profiles = profiles
        self._llm = llm
        self._clock = clock

    async def generate(self, user_id: UUID, week_start: date | None) -> tuple[WeeklyRetro, bool]:
        """(retro, created). Idempotent: an existing retro for that week is returned untouched."""
        today = await self._profiles.today(user_id)
        try:
            start, end = week_bounds(today, week_start)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        existing = await self._repo.get_by_week(user_id, start)
        if existing is not None:
            return existing, False

        summary = await self._gather(user_id, start, end)
        narration = await self._narrate(summary)
        if narration is not None:
            text, step, cited, narrated, model = (
                narration.observation, narration.next_step, narration.cited_days, True, self._llm.model,
            )
        else:
            text, step, cited = fallback_narrative(summary)
            narrated, model = False, None

        retro = WeeklyRetro(
            id=uuid4(), user_id=user_id, week_start=start, week_end=end, generated_at=self._clock(),
            narrative=text, next_step=step, summary=summary,
            evidence_refs={
                "cited_days": cited,
                "chain_dates": [c["slip_date"] for c in summary["chains"]],
                "unexplained_dates": [u["date"] for u in summary["unexplained_slips"]],
                "clean_days": [c["date"] for c in summary["clean_days"]],
            },
            narrated=narrated, voice_version=VOICE_VERSION, model=model,
        )
        saved = await self._repo.create(retro)
        if saved is None:  # lost a race with another generator
            return await self._repo.get_by_week(user_id, start), False
        return saved, True

    async def get(self, user_id: UUID, week_start: date | None) -> WeeklyRetro:
        retro = await (
            self._repo.latest(user_id) if week_start is None
            else self._repo.get_by_week(user_id, week_start)
        )
        if retro is None:
            raise NotFoundError("No retro for that week yet.")
        return retro

    async def list(self, user_id: UUID, limit: int = 12) -> list[WeeklyRetro]:
        return await self._repo.list(user_id, limit)

    async def pending_ratings(self, user_id: UUID, week_end: date) -> list[PatternInsight]:
        """Insights from before this week's end that the user never rated."""
        unrated = await self._insights.list(user_id, 100, True)
        return [i for i in unrated if i.generated_on <= week_end][:10]

    async def complete(self, user_id: UUID, week_start: date) -> tuple[WeeklyRetro, RefreshResult]:
        retro = await self.get(user_id, week_start)
        if retro.completed_at is not None:
            return retro, RefreshResult([], "already_completed")
        done = await self._repo.mark_completed(user_id, retro.id, self._clock())
        refresh = await self._insights.refresh(user_id)  # ratings are in; new insights respect them
        return done or retro, refresh

    # ------------------------------------------------------------------
    async def _gather(self, user_id: UUID, start: date, end: date) -> dict:
        prev_end = start - timedelta(days=1)
        _, days8 = await self._stats.chain(user_id, end, 8)
        _, prev_days = await self._stats.chain(user_id, prev_end, 7)
        _, habits_now, overall_now = await self._stats.consistency(user_id, end, 7)
        _, habits_prev, overall_prev = await self._stats.consistency(user_id, prev_end, 7)
        _, patterns = await self._stats.patterns(user_id, end, 30)
        study_now = await self._study.summary(user_id, start, end)
        study_prev = await self._study.summary(user_id, start - timedelta(days=7), prev_end)
        _, urge_now, urge_prev_rate = await self._urges.summary(user_id, end, 7)

        try:
            mission, progress, pct, _ = await self._missions.get_active_detail(user_id)
            mission_facts = {
                "title": sanitize_user_text(mission.title, 60, single_line=True),
                "day_number": progress.day_number, "days_total": progress.days_total,
                "phase": progress.phase, "consistency_pct": pct,
            }
        except NotFoundError:
            mission_facts = None

        return build_summary(
            week_start=start, week_end=end, days8=days8, prev_days=prev_days,
            habit_now=habits_now, habit_prev=habits_prev, overall_now=overall_now, overall_prev=overall_prev,
            pattern_keys=[p.key for p in patterns], study_now=study_now, study_prev=study_prev,
            urge_now=urge_now, urge_prev_rate=urge_prev_rate, mission=mission_facts,
            label=lambda text: sanitize_user_text(text, 40, single_line=True),
        )

    async def _narrate(self, summary: dict):
        facts_json = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
        require_dates = bool(summary["chains"] or summary["unexplained_slips"] or summary["clean_days"])
        messages = [
            {"role": "system", "content": retro_system_prompt()},
            {"role": "user", "content": f"<facts>\n{facts_json}\n</facts>"},
        ]
        try:
            narration, _ = await narrate_structured(
                self._llm, messages, facts_json=facts_json, require_dates=require_dates,
                max_observation=450, max_tokens=450, temperature=0.3,
            )
        except LLMError:
            return None
        return narration
