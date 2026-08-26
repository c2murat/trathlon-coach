from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.planning_context import (
    PlanningContextAssembler,
    PlanningGoalAthleteMismatchError,
)
from app.db.base import Base
from app.db.models import (
    ActivityTrainingLoad,
    AthleteDailyTrainingLoad,
    AthleteDailyTrainingStatus,
    AthletePerformanceProfileVersion,
    AthletePerformanceReference,
    AthleteProfile,
    CompetitionGoal,
    CompetitionGoalSegment,
    CompletedActivity,
    User,
)
from app.domains.planning.contracts import (
    AvailabilitySlot,
    PlanningPreferences,
    PlanningRequest,
    context_fingerprint,
)


PLANNING_DATE = date(2026, 8, 25)
LOAD_VERSION = "load-test-1"
AGGREGATION_VERSION = "aggregation-test-1"
STRENGTH_VERSION = "strength-test-1"
STATUS_VERSION = "status-test-1"


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def assembler(session):
    return PlanningContextAssembler(
        session,
        training_load_algorithm_version=LOAD_VERSION,
        load_aggregation_algorithm_version=AGGREGATION_VERSION,
        manual_strength_algorithm_version=STRENGTH_VERSION,
        training_status_algorithm_version=STATUS_VERSION,
    )


def make_request(athlete, goal):
    return PlanningRequest(
        athlete_id=athlete.id,
        planning_date=PLANNING_DATE,
        timezone_name="Europe/Madrid",
        goal_ids=(goal.id,),
        start_date=PLANNING_DATE,
        preferences=PlanningPreferences(
            availability_slots=(AvailabilitySlot(weekday=1, available_minutes=60, max_sessions=1),),
            max_sessions_per_day=1,
            max_sessions_per_week=6,
            preferred_rest_days=(0,),
            strength_sessions_per_week=1,
        ),
        algorithm_version="planning-test-1",
        configuration_version="config-test-1",
    )


def seed_identity_goal(session, *, athlete_name="A"):
    user = User(email=f"{athlete_name.lower()}@test", normalized_email=f"{athlete_name.lower()}@test", auth_subject=athlete_name, account_plan="athlete")
    athlete = AthleteProfile(display_name=athlete_name, timezone="Europe/Madrid", unit_system="metric")
    session.add_all([user, athlete])
    session.flush()
    goal = CompetitionGoal(
        athlete_profile_id=athlete.id,
        name="10K",
        event_date=date(2026, 10, 1),
        timezone="Europe/Madrid",
        event_category="running",
        event_format="10k",
        priority="A",
        target_finish_time_seconds=2700,
        status="active",
        created_by_user_id=user.id,
        segments=[CompetitionGoalSegment(position=1, sport="run", distance_m=10000)],
    )
    session.add(goal)
    session.flush()
    return athlete, goal


def add_activity(session, athlete, *, days_before, sport, duration, distance, load):
    local_day = PLANNING_DATE - timedelta(days=days_before)
    activity = CompletedActivity(
        athlete_id=athlete.id,
        source_summary="manual",
        sport=sport,
        name=sport,
        start_at=datetime(local_day.year, local_day.month, local_day.day, 10, tzinfo=timezone.utc),
        timezone="Europe/Madrid",
        elapsed_time_s=duration,
        moving_time_s=duration,
        distance_m=distance,
    )
    session.add(activity)
    session.flush()
    if load is not None:
        session.add(ActivityTrainingLoad(
            completed_activity_id=activity.id,
            load_value=load,
            method="test",
            unit="points",
            coverage="complete",
            quality="high",
            algorithm_version=LOAD_VERSION,
            duration_seconds=duration,
            source_metrics={},
            warnings=[],
            calculated_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        ))
    session.flush()
    return activity


def add_daily_load(session, athlete, local_date, total, endurance):
    session.add(AthleteDailyTrainingLoad(
        athlete_profile_id=athlete.id,
        local_date=local_date,
        timezone_name="Europe/Madrid",
        source_load_algorithm_version=LOAD_VERSION,
        manual_strength_algorithm_version=STRENGTH_VERSION,
        aggregation_algorithm_version=AGGREGATION_VERSION,
        total_load=total,
        endurance_load=endurance,
        strength_load=0,
        strength_session_count=0,
        activity_count=1,
        loaded_activity_count=1,
        null_load_activity_count=0,
        total_duration_seconds=3600,
        coverage="complete",
        quality="high",
        warnings=[],
        activity_ids=[],
        calculated_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    ))


def test_assembler_builds_windows_sports_cutoff_status_and_stable_fingerprint(db):
    athlete, goal = seed_identity_goal(db)
    db.add(AthletePerformanceProfileVersion(
        athlete_profile_id=athlete.id,
        effective_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
        data_origin="manual",
        algorithm_version="profile-test-1",
        cycling_ftp_watts=Decimal("250"),
    ))
    for days_before, sport, duration, distance, load in (
        (1, "running", 3600, 12000, 80),
        (7, "cycling", 7200, 60000, 120),
        (28, "swimming", 1800, 2000, 30),
        (42, "strength", 2400, None, None),
        (90, "running", 1000, 3000, 10),
        (0, "running", 9999, 99999, 999),
    ):
        add_activity(db, athlete, days_before=days_before, sport=sport, duration=duration, distance=distance, load=load)
    add_daily_load(db, athlete, PLANNING_DATE - timedelta(days=1), Decimal("80"), Decimal("80"))
    db.add(AthleteDailyTrainingStatus(
        athlete_profile_id=athlete.id,
        local_date=PLANNING_DATE - timedelta(days=1),
        timezone_name="Europe/Madrid",
        training_load_algorithm_version=LOAD_VERSION,
        manual_strength_algorithm_version=STRENGTH_VERSION,
        training_status_algorithm_version=STATUS_VERSION,
        total_load=Decimal("80"), fitness=Decimal("20"), fatigue=Decimal("25"), form=Decimal("-5"),
        history_day_number=50, is_warmup=False,
        calculated_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    ))
    db.add(AthleteDailyTrainingStatus(
        athlete_profile_id=athlete.id,
        local_date=PLANNING_DATE,
        timezone_name="Europe/Madrid",
        training_load_algorithm_version=LOAD_VERSION,
        manual_strength_algorithm_version=STRENGTH_VERSION,
        training_status_algorithm_version=STATUS_VERSION,
        total_load=Decimal("999"), fitness=Decimal("999"), fatigue=Decimal("1"), form=Decimal("998"),
        history_day_number=52, is_warmup=False,
        calculated_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
    ))
    db.commit()

    first = assembler(db).assemble(make_request(athlete, goal))
    second = assembler(db).assemble(make_request(athlete, goal))

    assert first.fingerprint == second.fingerprint
    fingerprint_payload = {
        "request": first.request,
        "goals": first.goals,
        "performance": first.performance,
        "training": first.training,
        "training_status": first.training_status,
        "versions": first.versions,
        "warnings": first.warnings,
    }
    assert first.fingerprint == context_fingerprint(fingerprint_payload)
    assert "fingerprint" not in fingerprint_payload
    assert first.training.observation_end == PLANNING_DATE - timedelta(days=1)
    assert [window.days for window in first.training.windows] == [7, 28, 42, 90]
    assert [window.activity_count for window in first.training.windows] == [2, 3, 4, 5]
    window_90 = first.training.windows[-1]
    by_sport = {item.sport: item for item in window_90.sports}
    assert by_sport["running"].activity_count == 2
    assert by_sport["running"].longest_distance_m == Decimal("12000.0")
    assert by_sport["cycling"].training_load == Decimal("120.0")
    assert by_sport["swimming"].duration_seconds == 1800
    assert by_sport["strength"].distance_m is None
    assert by_sport["strength"].missing_load_activity_count == 1
    assert first.training_status.local_date == PLANNING_DATE - timedelta(days=1)
    assert first.performance.cycling_ftp_watts == Decimal("250.00")


def test_empty_history_partial_profile_and_missing_load_status_are_non_blocking(db):
    athlete, goal = seed_identity_goal(db)
    db.add(AthletePerformanceProfileVersion(
        athlete_profile_id=athlete.id,
        effective_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
        data_origin="manual",
        algorithm_version="profile-test-1",
        running_threshold_pace_seconds_per_km=Decimal("300"),
    ))
    db.commit()
    context = assembler(db).assemble(make_request(athlete, goal))
    assert context.training.activities_available is False
    assert context.training_status is None
    assert context.performance.cycling_ftp_watts is None
    assert {warning.code for warning in context.warnings} == {
        "NO_TRAINING_HISTORY", "TRAINING_STATUS_UNAVAILABLE"
    }


def test_goal_from_another_athlete_is_rejected_without_data_leak(db):
    athlete_a, _ = seed_identity_goal(db, athlete_name="A")
    _, goal_b = seed_identity_goal(db, athlete_name="B")
    db.commit()
    with pytest.raises(PlanningGoalAthleteMismatchError):
        assembler(db).assemble(make_request(athlete_a, goal_b))


def test_future_profile_is_excluded(db):
    athlete, goal = seed_identity_goal(db)
    db.add(AthletePerformanceProfileVersion(
        athlete_profile_id=athlete.id,
        effective_from=datetime(2026, 8, 26, tzinfo=timezone.utc),
        data_origin="manual",
        algorithm_version="future",
        cycling_ftp_watts=Decimal("999"),
    ))
    db.commit()
    context = assembler(db).assemble(make_request(athlete, goal))
    assert context.performance.profile_version_id is None


@pytest.mark.parametrize("effective_day", [date(2026, 8, 24), date(2026, 8, 25)])
def test_profile_effective_before_or_on_planning_date_is_used(db, effective_day):
    athlete, goal = seed_identity_goal(db)
    profile = AthletePerformanceProfileVersion(
        athlete_profile_id=athlete.id,
        effective_from=datetime(effective_day.year, effective_day.month, effective_day.day, 10, tzinfo=timezone.utc),
        data_origin="manual",
        algorithm_version="profile-as-of-test",
        cycling_ftp_watts=Decimal("250"),
    )
    db.add(profile)
    db.commit()
    context = assembler(db).assemble(make_request(athlete, goal))
    assert context.performance.profile_version_id == profile.id
    assert context.performance.cycling_ftp_watts == Decimal("250.00")


def test_ftp_reference_effective_on_planning_date_is_used(db):
    athlete, goal = seed_identity_goal(db)
    reference = AthletePerformanceReference(
        athlete_profile_id=athlete.id,
        sport="cycling",
        metric_type="power",
        value=Decimal("250"),
        unit="W",
        data_origin="manual",
        quality_level="confirmed",
        effective_from=datetime(2026, 8, 25, 10, tzinfo=timezone.utc),
        algorithm_version="reference-as-of-test",
    )
    db.add(reference)
    db.commit()
    context = assembler(db).assemble(make_request(athlete, goal))
    assert tuple(item.reference_id for item in context.performance.references) == (reference.id,)


def test_same_day_ftp_change_changes_fingerprint(db):
    athlete, goal = seed_identity_goal(db)
    profile = AthletePerformanceProfileVersion(
        athlete_profile_id=athlete.id,
        effective_from=datetime(2026, 8, 25, 10, tzinfo=timezone.utc),
        data_origin="manual",
        algorithm_version="profile-as-of-test",
        cycling_ftp_watts=Decimal("250"),
    )
    db.add(profile)
    db.commit()
    first = assembler(db).assemble(make_request(athlete, goal))
    profile.cycling_ftp_watts = Decimal("260")
    db.commit()
    second = assembler(db).assemble(make_request(athlete, goal))
    assert first.performance.cycling_ftp_watts == Decimal("250.00")
    assert second.performance.cycling_ftp_watts == Decimal("260.00")
    assert first.fingerprint != second.fingerprint
