from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.planning_preview import PlanningPreviewApplication
from app.application.training_plan_lifecycle import (
    TrainingPlanActiveConflictError,
    TrainingPlanInvalidTransitionError,
    TrainingPlanLifecycleApplication,
    TrainingPlanNotFoundError,
)
from app.db.models import AthleteProfile, TrainingPlan
from tests.test_planning_preview_application import seeded


def accepted_plan():
    engine, preview_id, athlete_id, user_id, _ = seeded()
    with Session(engine) as session:
        plan_id = PlanningPreviewApplication(session).accept(
            preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete"
        ).id
    return engine, athlete_id, plan_id


@pytest.mark.parametrize(
    ("initial", "action", "expected"),
    (
        ("draft", "activate", "active"),
        ("draft", "archive", "archived"),
        ("active", "complete", "completed"),
        ("active", "archive", "archived"),
    ),
)
def test_allowed_transitions(initial, action, expected):
    engine, athlete_id, plan_id = accepted_plan()
    with Session(engine) as session:
        session.get(TrainingPlan, plan_id).status = initial
        session.commit()
        plan = TrainingPlanLifecycleApplication(session).transition(
            plan_id=plan_id, athlete_id=athlete_id, action=action
        )
        assert plan.status == expected
        assert session.get(TrainingPlan, plan_id).status == expected


@pytest.mark.parametrize(
    ("status", "action"),
    (("active", "activate"), ("completed", "complete"), ("archived", "archive")),
)
def test_same_target_retry_is_idempotent(status, action):
    engine, athlete_id, plan_id = accepted_plan()
    with Session(engine) as session:
        session.get(TrainingPlan, plan_id).status = status
        session.commit()
        assert TrainingPlanLifecycleApplication(session).transition(
            plan_id=plan_id, athlete_id=athlete_id, action=action
        ).status == status
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 1


@pytest.mark.parametrize(
    ("status", "action"),
    (
        ("draft", "complete"),
        ("completed", "activate"),
        ("completed", "archive"),
        ("archived", "activate"),
        ("archived", "complete"),
    ),
)
def test_invalid_transitions_do_not_change_state(status, action):
    engine, athlete_id, plan_id = accepted_plan()
    with Session(engine) as session:
        session.get(TrainingPlan, plan_id).status = status
        session.commit()
        with pytest.raises(TrainingPlanInvalidTransitionError):
            TrainingPlanLifecycleApplication(session).transition(
                plan_id=plan_id, athlete_id=athlete_id, action=action
            )
        assert session.get(TrainingPlan, plan_id).status == status


def test_activation_conflict_reports_existing_active_plan():
    engine, athlete_id, plan_id = accepted_plan()
    with Session(engine) as session:
        plan = session.get(TrainingPlan, plan_id)
        existing = TrainingPlan(
            athlete_profile_id=athlete_id,
            title="Already active",
            start_date=plan.start_date - timedelta(days=30),
            end_date=plan.start_date - timedelta(days=1),
            status="active",
            origin="human",
        )
        session.add(existing)
        session.commit()
        with pytest.raises(TrainingPlanActiveConflictError) as caught:
            TrainingPlanLifecycleApplication(session).transition(
                plan_id=plan_id, athlete_id=athlete_id, action="activate"
            )
        assert caught.value.existing_training_plan_id == existing.id
        assert session.get(TrainingPlan, plan_id).status == "draft"


def test_transition_rolls_back_when_commit_fails(monkeypatch):
    engine, athlete_id, plan_id = accepted_plan()
    with Session(engine) as session:
        def fail_commit():
            raise RuntimeError("injected_lifecycle_commit_failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="injected_lifecycle_commit_failure"):
            TrainingPlanLifecycleApplication(session).transition(
                plan_id=plan_id, athlete_id=athlete_id, action="activate"
            )
    with Session(engine) as verification:
        assert verification.get(TrainingPlan, plan_id).status == "draft"
        assert verification.scalar(
            select(func.count()).select_from(TrainingPlan).where(
                TrainingPlan.athlete_profile_id == athlete_id,
                TrainingPlan.status == "active",
            )
        ) == 0


def test_active_plan_for_another_athlete_does_not_block_activation():
    engine, athlete_id, plan_id = accepted_plan()
    with Session(engine) as session:
        plan = session.get(TrainingPlan, plan_id)
        other = AthleteProfile(display_name="Other active", timezone="Europe/Madrid", unit_system="metric")
        session.add(other);session.flush()
        session.add(TrainingPlan(athlete_profile_id=other.id,title="Other",start_date=plan.start_date,end_date=plan.end_date,status="active",origin="human"))
        session.commit()
        assert TrainingPlanLifecycleApplication(session).transition(plan_id=plan_id,athlete_id=athlete_id,action="activate").status == "active"


def test_foreign_plan_is_not_disclosed_or_changed():
    engine, athlete_id, plan_id = accepted_plan()
    with Session(engine) as session:
        other = AthleteProfile(display_name="Other", timezone="Europe/Madrid", unit_system="metric")
        session.add(other)
        session.commit()
        with pytest.raises(TrainingPlanNotFoundError):
            TrainingPlanLifecycleApplication(session).transition(
                plan_id=plan_id, athlete_id=other.id, action="activate"
            )
        assert session.get(TrainingPlan, plan_id).status == "draft"
