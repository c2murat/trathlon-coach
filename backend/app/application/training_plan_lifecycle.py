from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AthleteProfile, TrainingPlan


TrainingPlanAction = Literal["activate", "complete", "archive"]


class TrainingPlanLifecycleError(ValueError):
    code = "training_plan_lifecycle_error"


class TrainingPlanNotFoundError(TrainingPlanLifecycleError):
    code = "training_plan_not_found"


class TrainingPlanInvalidTransitionError(TrainingPlanLifecycleError):
    code = "training_plan_invalid_transition"

    def __init__(self, plan: TrainingPlan, action: TrainingPlanAction):
        self.training_plan_id = plan.id
        self.current_status = plan.status
        self.requested_action = action
        super().__init__(self.code)


class TrainingPlanActiveConflictError(TrainingPlanLifecycleError):
    code = "training_plan_active_conflict"

    def __init__(self, plan: TrainingPlan):
        self.existing_training_plan_id = plan.id
        self.existing_start_date = plan.start_date
        self.existing_end_date = plan.end_date
        super().__init__(self.code)


class TrainingPlanLifecycleApplication:
    """Apply lifecycle transitions while serializing changes per athlete."""

    _targets: dict[TrainingPlanAction, str] = {
        "activate": "active",
        "complete": "completed",
        "archive": "archived",
    }
    _allowed = {
        ("draft", "active"),
        ("draft", "archived"),
        ("active", "completed"),
        ("active", "archived"),
    }

    def __init__(self, session: Session):
        self.session = session

    def transition(self, *, plan_id: UUID, athlete_id: UUID, action: TrainingPlanAction) -> TrainingPlan:
        try:
            # Keep this lock order aligned with preview acceptance: athlete first,
            # then the athlete-scoped plan. PostgreSQL holds both until commit.
            athlete = self.session.scalar(
                select(AthleteProfile)
                .where(AthleteProfile.id == athlete_id)
                .with_for_update()
            )
            if athlete is None:
                raise TrainingPlanNotFoundError()

            plan = self.session.scalar(
                select(TrainingPlan)
                .where(
                    TrainingPlan.id == plan_id,
                    TrainingPlan.athlete_profile_id == athlete_id,
                )
                .with_for_update()
            )
            if plan is None:
                raise TrainingPlanNotFoundError()

            target = self._targets[action]
            if plan.status == target:
                return plan
            if (plan.status, target) not in self._allowed:
                raise TrainingPlanInvalidTransitionError(plan, action)

            if target == "active":
                existing = self.session.scalar(
                    select(TrainingPlan)
                    .where(
                        TrainingPlan.athlete_profile_id == athlete_id,
                        TrainingPlan.status == "active",
                        TrainingPlan.id != plan.id,
                    )
                    .order_by(TrainingPlan.start_date, TrainingPlan.id)
                    .limit(1)
                )
                if existing is not None:
                    raise TrainingPlanActiveConflictError(existing)

            plan.status = target
            self.session.commit()
            self.session.refresh(plan)
            return plan
        except Exception:
            self.session.rollback()
            raise
