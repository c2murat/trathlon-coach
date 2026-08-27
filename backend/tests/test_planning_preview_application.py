import json
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.planning_preview import (
    PlanningPreviewApplication, PlanningPreviewAthleteMismatchError,
    PlanningPreviewFingerprintMismatchError, PlanningPreviewGoalInvalidError,
    persistence_goal_role,
)
from app.db.base import Base
from app.db.models import (
    AthleteProfile, CompetitionGoal, PlannedTrainingSession, StructuredWorkout,
    TrainingPlan, TrainingPlanGoal, TrainingPlanPreview, User,
)
from app.domains.planning.preview import build_preview_artifact
from app.domains.planning.models import StructuredWorkoutDefinition
from app.domains.planning.session_planning import SessionType
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout, structured_workout_payload
from tests.test_weekly_budget import context
from tests.test_session_planning import with_running_frequency
from tests.test_planning_preview_artifact import artifact


def seeded(source=None):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    source = source or artifact()
    with Session(engine) as session:
        user = User(email="preview@test", normalized_email="preview@test", auth_subject="preview", account_plan="athlete")
        athlete = AthleteProfile(id=source.athlete_id, display_name="Preview", timezone=source.timezone_name, unit_system="metric")
        session.add_all((user, athlete)); session.flush()
        for item in source.goals:
            session.add(CompetitionGoal(
                id=item.competition_goal_id, athlete_profile_id=athlete.id,
                name="Goal", event_date=item.event_date, timezone=item.timezone_name,
                event_category="running", event_format=item.event_format,
                priority=item.priority, status="active", created_by_user_id=user.id,
            ))
        row = TrainingPlanPreview(
            athlete_profile_id=athlete.id, created_by_user_id=user.id,
            status="pending", artifact=source.model_dump(mode="json", exclude_none=True),
            artifact_fingerprint=source.fingerprint, algorithm_version=source.algorithm_version,
            configuration_version=source.configuration_version,
        )
        session.add(row); session.commit()
        return engine, row.id, athlete.id, user.id, source


def test_accept_persists_exact_snapshot_and_retry_returns_same_plan():
    engine, preview_id, athlete_id, user_id, source = seeded()
    with Session(engine) as session:
        app = PlanningPreviewApplication(session)
        first = app.accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        second = app.accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        assert first.id == second.id
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 1
        expected = [item for item in source.sessions if item.prescription.session_type.value != "COMPETITION"]
        rows = session.scalars(select(PlannedTrainingSession).where(PlannedTrainingSession.training_plan_id == first.id)).all()
        assert len(rows) == len(expected)
        assert {(item.scheduled_date, item.sport, item.planned_duration_seconds) for item in rows} == {
            (item.prescription.date, item.prescription.discipline, (item.prescription.target_duration_minutes or 0) * 60)
            for item in expected
        }
        assert session.scalar(select(func.count()).select_from(StructuredWorkout)) == sum(item.workout.buildable for item in expected)


def test_two_logical_callers_receive_the_same_plan_without_duplicates():
    engine, preview_id, athlete_id, user_id, _ = seeded()
    with Session(engine) as first_session:
        first_id = PlanningPreviewApplication(first_session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete").id
    with Session(engine) as second_session:
        second_id = PlanningPreviewApplication(second_session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete").id
        assert second_id == first_id
        assert second_session.scalar(select(func.count()).select_from(TrainingPlan)) == 1


def test_accept_rolls_back_everything_on_midway_failure():
    engine, preview_id, athlete_id, user_id, _ = seeded()
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="injected_accept_failure"):
            PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete", fail_after_sessions=1)
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 0
        assert session.scalar(select(func.count()).select_from(TrainingPlanGoal)) == 0
        assert session.scalar(select(func.count()).select_from(PlannedTrainingSession)) == 0
        assert session.scalar(select(func.count()).select_from(StructuredWorkout)) == 0
        preview = session.get(TrainingPlanPreview, preview_id)
        assert preview.status == "pending" and preview.accepted_training_plan is None
        assert preview.accepted_at is None and preview.accepted_by_user_id is None


def test_cross_athlete_accept_is_rejected_without_writes():
    engine, preview_id, _, user_id, _ = seeded()
    with Session(engine) as session:
        other = AthleteProfile(display_name="Other", timezone="Europe/Madrid", unit_system="metric")
        session.add(other); session.commit()
        with pytest.raises(PlanningPreviewAthleteMismatchError):
            PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=other.id, user_id=user_id, role="athlete")
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 0


@pytest.mark.parametrize(("season_role", "stored_role"), (("primary", "primary"), ("supporting", "supporting"), ("training", "supporting")))
def test_persistence_goal_role_is_explicit(season_role, stored_role):
    assert persistence_goal_role(season_role) == stored_role


def test_priority_c_snapshot_keeps_training_role_and_persists_supporting():
    base = artifact()
    season = base.season_structure.model_copy(update={"goals": (base.season_structure.goals[0].model_copy(update={"role": "training"}),)})
    goals = (base.goals[0].model_copy(update={"priority": "C"}),)
    source = build_preview_artifact(
        athlete_id=base.athlete_id, timezone_name=base.timezone_name,
        context_fingerprint_value=base.context_fingerprint, season=season,
        budgets=base.weekly_budget_plan, session_plan=base.session_plan, goals=goals,
        workout_drafts=tuple(item.workout for item in base.sessions),
        algorithm_version=base.algorithm_version, configuration_version=base.configuration_version,
    )
    engine, preview_id, athlete_id, user_id, _ = seeded(source)
    with Session(engine) as session:
        plan = PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        assert session.get(TrainingPlanPreview, preview_id).artifact["season_structure"]["goals"][0]["role"] == "training"
        assert session.scalar(select(TrainingPlanGoal).where(TrainingPlanGoal.training_plan_id == plan.id)).relationship == "supporting"


def test_goal_changes_are_not_regenerated_and_new_goal_is_not_added():
    engine, preview_id, athlete_id, user_id, source = seeded()
    with Session(engine) as session:
        goal = session.get(CompetitionGoal, source.goals[0].competition_goal_id)
        goal.name, goal.priority, goal.distance_m = "Changed", "B", 15000
        session.add(CompetitionGoal(
            athlete_profile_id=athlete_id, name="New", event_date=goal.event_date,
            timezone=goal.timezone, event_category="running", event_format="custom",
            priority="C", status="active", created_by_user_id=user_id,
        ))
        session.commit()
        plan = PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        links = session.scalars(select(TrainingPlanGoal).where(TrainingPlanGoal.training_plan_id == plan.id)).all()
        assert len(links) == len(source.goals)
        assert links[0].relationship == "primary"


def test_inactive_goal_blocks_accept_atomically():
    engine, preview_id, athlete_id, user_id, source = seeded()
    with Session(engine) as session:
        session.get(CompetitionGoal, source.goals[0].competition_goal_id).status = "cancelled"
        session.commit()
        with pytest.raises(PlanningPreviewGoalInvalidError):
            PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 0
        assert session.get(TrainingPlanPreview, preview_id).status == "pending"


def test_deleted_goal_blocks_accept_atomically():
    engine, preview_id, athlete_id, user_id, source = seeded()
    with Session(engine) as session:
        session.delete(session.get(CompetitionGoal, source.goals[0].competition_goal_id))
        session.commit()
        with pytest.raises(PlanningPreviewGoalInvalidError):
            PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 0


def test_artifact_is_immutable_after_accept_and_corruption_is_rejected():
    engine, preview_id, athlete_id, user_id, _ = seeded()
    with Session(engine) as session:
        preview = session.get(TrainingPlanPreview, preview_id)
        before = json.dumps(preview.artifact, sort_keys=True)
        fingerprint = preview.artifact_fingerprint
        PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        session.refresh(preview)
        assert json.dumps(preview.artifact, sort_keys=True) == before
        assert preview.artifact_fingerprint == fingerprint
    engine, preview_id, athlete_id, user_id, _ = seeded()
    with Session(engine) as session:
        preview = session.get(TrainingPlanPreview, preview_id)
        damaged = dict(preview.artifact); damaged["algorithm_version"] = "corrupt"
        preview.artifact = damaged; session.commit()
        with pytest.raises(PlanningPreviewFingerprintMismatchError):
            PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 0


def test_db_unique_source_preview_and_coach_attribution():
    engine, preview_id, athlete_id, coach_id, _ = seeded()
    with Session(engine) as session:
        plan = PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=coach_id, role="coach")
        preview = session.get(TrainingPlanPreview, preview_id)
        assert preview.created_by_user_id == coach_id and preview.accepted_by_user_id == coach_id
        assert preview.accepted_training_plan.id == plan.id
        assert plan.athlete_profile_id == athlete_id and plan.origin == "ai" and plan.created_by_user_id is None
        assert plan.created_via_role == "coach" and plan.source_preview_id == preview_id
        session.add(TrainingPlan(athlete_profile_id=athlete_id, title="Duplicate", start_date=plan.start_date, end_date=plan.end_date, status="draft", origin="ai", source_preview_id=preview_id))
        with pytest.raises(IntegrityError):
            session.commit()


def test_workouts_are_exact_and_competition_is_not_duplicated():
    engine, preview_id, athlete_id, user_id, source = seeded()
    with Session(engine) as session:
        plan = PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        rows = session.scalars(select(PlannedTrainingSession).where(PlannedTrainingSession.training_plan_id == plan.id)).all()
        assert len(rows) == sum(item.prescription.session_type.value != "COMPETITION" for item in source.sessions)
        persisted = {row.id: session.scalar(select(StructuredWorkout).where(StructuredWorkout.planned_training_session_id == row.id)) for row in rows}
        expected = [item for item in source.sessions if item.prescription.session_type.value != "COMPETITION"]
        for row, item in zip(rows, expected):
            if item.workout.buildable:
                assert StructuredWorkoutDefinition.model_validate(persisted[row.id].definition) == StructuredWorkoutDefinition.model_validate(structured_workout_payload(item.workout.definition))


def test_exact_persistence_covers_representative_workout_families():
    ctx = context(windows=with_running_frequency())
    base = artifact(ctx)
    replacements = (
        (SessionType.RUN_EASY, "running"),
        (SessionType.RUN_THRESHOLD, "running"),
        (SessionType.BIKE_ENDURANCE, "cycling"),
        (SessionType.SWIM_AEROBIC, "swimming"),
        (SessionType.GENERAL_STRENGTH, "strength"),
    )
    changed_weeks = []
    for index, week in enumerate(base.session_plan.weeks):
        if index < len(replacements):
            kind, discipline = replacements[index]
            sessions = (week.sessions[0].model_copy(update={"session_type": kind, "discipline": discipline}), *week.sessions[1:])
            week = week.model_copy(update={"sessions": sessions})
        changed_weeks.append(week)
    plan = base.session_plan.model_copy(update={"weeks": tuple(changed_weeks)})
    prescriptions = tuple(item for week in plan.weeks for item in week.sessions)
    config = WorkoutBuilderConfig(version="workout-1", algorithm_version="workout-algorithm-1")
    drafts = tuple(build_structured_workout(ctx, item, config) for item in prescriptions)
    source = build_preview_artifact(
        athlete_id=base.athlete_id, timezone_name=base.timezone_name,
        context_fingerprint_value=base.context_fingerprint, season=base.season_structure,
        budgets=base.weekly_budget_plan, session_plan=plan, goals=base.goals,
        workout_drafts=drafts, algorithm_version=base.algorithm_version,
        configuration_version=base.configuration_version,
    )
    engine, preview_id, athlete_id, user_id, _ = seeded(source)
    with Session(engine) as session:
        accepted = PlanningPreviewApplication(session).accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        rows = session.scalars(select(PlannedTrainingSession).where(PlannedTrainingSession.training_plan_id == accepted.id)).all()
        assert {row.title for row in rows} >= {kind.value for kind, _ in replacements}
        for row in rows:
            workout = session.scalar(select(StructuredWorkout).where(StructuredWorkout.planned_training_session_id == row.id))
            if workout is not None:
                StructuredWorkoutDefinition.model_validate(workout.definition)


def test_representative_artifact_size_is_reasonable():
    size = len(json.dumps(artifact().model_dump(mode="json"), separators=(",", ":")).encode())
    assert 1_000 < size < 5_000_000
