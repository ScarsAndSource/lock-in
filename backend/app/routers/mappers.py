from __future__ import annotations

from app.domain import HabitDefinition, Mission, ScreenTimeLog, ScreenTimeProposal, SleepLog, SleepProposal
from app.schemas import (
    BounceOut, CheckinEntryOut, HabitConsistencyOut, HabitOut, MissionOut,
    ScreenTimeLogOut, ScreenTimeProposalOut, SleepLogOut, SleepProposalOut,
)
from app.services.bounce_back import BounceState, bounce_copy
from app.services.checkins_service import CheckinEntry
from app.services.consistency_service import HabitConsistency
from app.services.tone import resolve_tone


def habit_out(h: HabitDefinition) -> HabitOut:
    return HabitOut(
        id=h.id, name=h.name, target_frequency=h.target_frequency.to_dict(), archived_at=h.archived_at,
        floor_text=h.floor_text, stretch_text=h.stretch_text,
    )


def entry_out(e: CheckinEntry) -> CheckinEntryOut:
    return CheckinEntryOut(
        habit_id=e.habit_id, habit_name=e.habit_name, status=e.status, is_default=e.is_default,
        is_low_confidence=e.is_low_confidence, reason=e.reason, is_scheduled=e.is_scheduled,
        floor_text=e.floor_text, stretch_text=e.stretch_text,
    )


def sleep_out(log: SleepLog | None) -> SleepLogOut | None:
    if log is None:
        return None
    return SleepLogOut(
        log_date=log.log_date, time_to_bed=log.time_to_bed, time_woke=log.time_woke,
        self_rated_quality=log.self_rated_quality, duration_minutes=log.duration_minutes,
        is_default=log.is_default,
    )


def screen_out(log: ScreenTimeLog | None) -> ScreenTimeLogOut | None:
    if log is None:
        return None
    return ScreenTimeLogOut(
        log_date=log.log_date, total_minutes=log.total_minutes, source=log.source,
        category_breakdown=log.category_breakdown, is_default=log.is_default,
    )


def sleep_proposal_out(p: SleepProposal | None) -> SleepProposalOut | None:
    if p is None:
        return None
    return SleepProposalOut(
        time_to_bed=p.time_to_bed, time_woke=p.time_woke, self_rated_quality=p.self_rated_quality,
        based_on_count=p.based_on_count, is_low_confidence=p.is_low_confidence, reason=p.reason,
    )


def screen_proposal_out(p: ScreenTimeProposal | None) -> ScreenTimeProposalOut | None:
    if p is None:
        return None
    return ScreenTimeProposalOut(
        total_minutes=p.total_minutes, based_on_count=p.based_on_count,
        is_low_confidence=p.is_low_confidence, reason=p.reason,
    )


def mission_out(m: Mission) -> MissionOut:
    return MissionOut(id=m.id, title=m.title, start_date=m.start_date, end_date=m.end_date, status=m.status, ended_at=m.ended_at)


def consistency_out(c: HabitConsistency) -> HabitConsistencyOut:
    return HabitConsistencyOut(
        habit_id=c.habit_id, habit_name=c.habit_name, consistency_pct=c.consistency_pct,
        coverage_pct=c.coverage_pct, longest_run=c.longest_run, current_run=c.current_run,
        run_unit=c.run_unit, comeback_rate=c.comeback_rate,
    )


def bounce_out(state: BounceState, tone_preference: str) -> BounceOut:
    tone = resolve_tone(tone_preference, state.slip_streak)
    copy = bounce_copy(state, tone)
    return BounceOut(
        active=state.active, slip_streak=state.slip_streak, tone=tone,
        title=copy[0] if copy else None, message=copy[1] if copy else None,
    )
