from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app.application.planned_session_rescheduling import (
    ManualStrengthLinkInvalidError,
    ManualStrengthLinkNotFoundError,
    PlannedSessionRescheduling,
    SessionRescheduleOutsideWeekError,
    SessionReschedulePlanNotEditableError,
)
from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.db.models import (
    ManualStrengthSession,
    PlannedSessionManualStrengthLink,
    PlannedSessionScheduleChange,
    PlannedTrainingSession,
    StructuredWorkout,
    TrainingPlan,
    User,
)
from tests.test_execution_evidence import workout as interval_workout
from tests.test_planned_session_activity_matching import athlete, db, planned


def user(db, suffix="owner"):
    row = User(
        email=f"{suffix}@example.invalid",
        normalized_email=f"{suffix}@example.invalid",
        auth_subject=f"auth-{suffix}",
        timezone="Europe/Madrid",
    )
    db.add(row)
    db.flush()
    return row


def training_plan(db, owner, status="active"):
    row = TrainingPlan(
        athlete_profile_id=owner.id,
        title="Plan",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 27),
        status=status,
        origin="ai",
    )
    db.add(row)
    db.flush()
    return row


def planned_in_plan(db, owner, plan, day=date(2026, 9, 21), sport="running"):
    row = planned(db, owner, day=day, sport=sport, duration=2400, distance=None)
    row.training_plan_id = plan.id
    return row


def strength_manual(db, owner, *, day=22, hour=15, minutes=60):
    row = ManualStrengthSession(
        athlete_id=owner.id,
        started_at=datetime(2026, 9, day, hour, 42, tzinfo=timezone.utc),
        timezone_name="Europe/Madrid",
        duration_minutes=minutes,
        body_regions=["full_body"],
        perceived_exertion=9,
    )
    db.add(row)
    db.flush()
    return row


def test_reschedules_inside_same_week_preserves_workout_and_writes_history(db):
    owner = athlete(db)
    actor = user(db)
    plan = training_plan(db, owner)
    session = planned_in_plan(db, owner, plan)
    definition = interval_workout().model_dump(mode="json", exclude_none=True)
    workout = StructuredWorkout(planned_training_session_id=session.id, schema_version=1, definition=definition)
    db.add(workout)
    db.flush()
    persisted_definition = workout.definition

    result = PlannedSessionRescheduling(db).reschedule(
        athlete_id=owner.id,
        session_id=session.id,
        new_date=date(2026, 9, 23),
        user_id=actor.id,
        reason="athlete_request",
    )

    assert result.id == session.id
    assert result.scheduled_date == date(2026, 9, 23)
    assert db.get(StructuredWorkout, workout.id).definition == persisted_definition
    change = db.scalar(select(PlannedSessionScheduleChange))
    assert change.previous_scheduled_date == date(2026, 9, 21)
    assert change.new_scheduled_date == date(2026, 9, 23)
    assert change.changed_by_user_id == actor.id


def test_reschedule_rejects_outside_week_and_non_editable_plan(db):
    owner = athlete(db)
    actor = user(db)
    plan = training_plan(db, owner)
    session = planned_in_plan(db, owner, plan)
    service = PlannedSessionRescheduling(db)

    with pytest.raises(SessionRescheduleOutsideWeekError):
        service.reschedule(athlete_id=owner.id, session_id=session.id, new_date=date(2026, 9, 28), user_id=actor.id)
    assert session.scheduled_date == date(2026, 9, 21)

    plan.status = "completed"
    with pytest.raises(SessionReschedulePlanNotEditableError):
        service.reschedule(athlete_id=owner.id, session_id=session.id, new_date=date(2026, 9, 22), user_id=actor.id)
    assert db.scalar(select(func.count()).select_from(PlannedSessionScheduleChange)) == 0


def test_manual_strength_cross_day_link_is_explicit_idempotent_and_c1_duration_evidence(db):
    owner = athlete(db)
    actor = user(db)
    plan = training_plan(db, owner)
    session = planned_in_plan(db, owner, plan, day=date(2026, 9, 21), sport="strength")
    manual = strength_manual(db, owner, day=22, minutes=60)

    first = PlannedSessionRescheduling(db).link_manual_strength(
        athlete_id=owner.id,
        session_id=session.id,
        manual_strength_session_id=manual.id,
        user_id=actor.id,
    )
    second = PlannedSessionRescheduling(db).link_manual_strength(
        athlete_id=owner.id,
        session_id=session.id,
        manual_strength_session_id=manual.id,
        user_id=actor.id,
    )
    context = PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=owner.id, as_of_date=date(2026, 9, 23))

    assert second.id == first.id
    assert db.scalar(select(func.count()).select_from(PlannedSessionManualStrengthLink)) == 1
    assert context.sessions[0].planned_session_id == session.id
    assert context.sessions[0].source_activity_ids == (manual.id,)
    assert context.sessions[0].actual_duration_seconds == 3600
    assert context.sessions[0].completion_status == "OVER_DURATION"
    assert context.sessions[0].target_comparison is None


def test_manual_strength_link_requires_same_athlete_strength_and_same_week(db):
    owner = athlete(db)
    other = athlete(db, "Other")
    actor = user(db)
    plan = training_plan(db, owner)
    running = planned_in_plan(db, owner, plan, sport="running")
    strength = planned_in_plan(db, owner, plan, sport="strength")
    foreign = strength_manual(db, other)
    outside_week = strength_manual(db, owner, day=28)
    service = PlannedSessionRescheduling(db)

    with pytest.raises(ManualStrengthLinkInvalidError):
        service.link_manual_strength(athlete_id=owner.id, session_id=running.id, manual_strength_session_id=outside_week.id, user_id=actor.id)
    with pytest.raises(ManualStrengthLinkNotFoundError):
        service.link_manual_strength(athlete_id=owner.id, session_id=strength.id, manual_strength_session_id=foreign.id, user_id=actor.id)
    with pytest.raises(ManualStrengthLinkInvalidError):
        service.link_manual_strength(athlete_id=owner.id, session_id=strength.id, manual_strength_session_id=outside_week.id, user_id=actor.id)
