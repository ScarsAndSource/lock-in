from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from app.domain import GoalStatus, HabitStatus, ScreenTimeSource, UrgeOutcome
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.checkins_service import CheckinsService
from app.services.goals_service import GoalsService
from app.services.intentions_service import IntentionsService
from app.services.study_service import StudyService
from app.services.urges_service import UrgesService


@pytest.mark.asyncio
async def test_subject_lifecycle(world, user_a, user_b):
    study = StudyService(world.subject_repo, world.study_repo, clock=world._clock)

    # User A creates a subject
    s1 = await study.create_subject(user_a, "Math")
    assert s1.name == "Math"

    # User B can create same subject name (isolation)
    sb = await study.create_subject(user_b, "Math")
    assert sb.id != s1.id

    # User A archives Math
    archived = await study.update_subject(user_a, s1.id, name=None, archived=True)
    assert archived.archived_at is not None

    # User A renames a new subject
    s2 = await study.create_subject(user_a, "Physics")
    updated = await study.update_subject(user_a, s2.id, name="Advanced Physics", archived=None)
    assert updated.name == "Advanced Physics"


@pytest.mark.asyncio
async def test_study_sessions_logging_and_deletion(world, user_a, user_b):
    study = StudyService(world.subject_repo, world.study_repo, clock=world._clock)
    subj = await study.create_subject(user_a, "Physics")

    d = date(2026, 12, 1)
    session = await study.log_session(user_a, log_date=d, subject_id=subj.id, subject_name=None, planned_minutes=60, actual_minutes=45)
    assert session.actual_minutes == 45
    assert session.planned_minutes == 60

    # User B cannot log for User A's subject
    with pytest.raises(NotFoundError):
        await study.log_session(user_b, log_date=d, subject_id=subj.id, subject_name=None, planned_minutes=60, actual_minutes=45)

    # Delete session
    await study.delete_session(user_a, session.id)
    with pytest.raises(NotFoundError):
        await study.delete_session(user_a, session.id)


@pytest.mark.asyncio
async def test_urge_logs_and_encryption(world, user_a):
    urges = UrgesService(world.urge_repo, world.encryptor, world.profile_repo, clock=world._clock)

    dt = datetime(2026, 12, 1, 14, 30, tzinfo=timezone.utc)
    view = await urges.capture(
        user_a, outcome=UrgeOutcome.RESISTED, occurred_at=dt, intensity=7,
        trigger_context="Stress at work", coping_strategy="Deep breathing", note="Felt tough"
    )
    assert view.log.outcome == UrgeOutcome.RESISTED
    assert view.log.intensity == 7
    assert view.trigger_context == "Stress at work"
    assert view.coping_strategy == "Deep breathing"
    assert view.note == "Felt tough"

    # Encrypted in storage
    raw = world.urge_repo._logs[view.log.id]
    assert raw.trigger_context_encrypted != b"Stress at work"

    # Delete
    await urges.delete(user_a, view.log.id)
    with pytest.raises(NotFoundError):
        await urges.delete(user_a, view.log.id)


@pytest.mark.asyncio
async def test_goals_and_intentions_lifecycle(world, user_a):
    goals_svc = GoalsService(
        world.goal_repo, world.habit_repo, world.sleep_repo, world.screen_time_repo,
        None, world.study_repo, world.urge_repo, world.profile_repo, clock=world._clock
    )
    intentions_svc = IntentionsService(
        world.intention_repo, world.habit_repo, world.subject_repo, None, world.profile_repo, clock=world._clock
    )

    g = await goals_svc.create(
        user_a, "sleep", "Sleep 8h nightly",
        {"min_minutes_per_night": 480, "min_nights_pct": 80, "window_days": 30, "bedtime": "23:00", "wake": "07:00"}
    )
    assert g.domain == "sleep"
    assert g.status == GoalStatus.ACTIVE

    active = await goals_svc.list(user_a, GoalStatus.ACTIVE)
    assert len(active) == 1

    ii = await intentions_svc.create(
        user_a, "sleep", None,
        cue="When it turns 10:30 PM",
        action="I will turn off screens and prepare for bed",
    )
    assert ii.linked_domain == "sleep"

    intentions = await intentions_svc.list(user_a, domain="sleep")
    assert len(intentions) == 1

    # Update status / delete
    updated = await goals_svc.update(user_a, g.id, None, GoalStatus.ARCHIVED, None)
    assert updated.status == GoalStatus.ARCHIVED


@pytest.mark.asyncio
async def test_checkin_proposals_fallback_to_goals(world, user_a):
    goals_svc = GoalsService(
        world.goal_repo, world.habit_repo, world.sleep_repo, world.screen_time_repo,
        None, world.study_repo, world.urge_repo, world.profile_repo, clock=world._clock
    )
    checkins_svc = CheckinsService(
        world.habit_repo, world.checkin_repo, world.encryptor,
        world.sleep_repo, world.screen_time_repo, clock=world._clock,
        goals=world.goal_repo,
    )

    # Set sleep goal
    await goals_svc.create(
        user_a, "sleep", "Sleep 8h nightly",
        {"min_minutes_per_night": 480, "min_nights_pct": 80, "window_days": 30, "bedtime": "23:00", "wake": "07:00"}
    )

    # Get checkin view with empty sleep history
    view = await checkins_svc.get_view(user_a, date(2026, 12, 1))
    assert view.sleep_proposal is not None
    assert str(view.sleep_proposal.time_to_bed) == "23:00:00"
    assert str(view.sleep_proposal.time_woke) == "07:00:00"
