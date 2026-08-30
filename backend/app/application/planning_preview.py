from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.planning_context import PlanningContextAssembler
from app.db.models import (
    AthleteProfile,
    CompetitionGoal, PlannedTrainingSession, StructuredWorkout, TrainingPlan,
    TrainingPlanGoal, TrainingPlanPreview,
)
from app.domains.planning.contracts import PlanningRequest
from app.domains.planning.preview import TrainingPlanPreviewArtifact, build_preview_artifact
from app.domains.planning.season_structure import SeasonStructureBuilder, SeasonStructureConfig
from app.domains.planning.session_planning import SessionPlanningConfig, SessionType, build_session_plan
from app.domains.planning.weekly_budget import WeeklyBudgetConfig, build_weekly_budget_plan
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout, structured_workout_payload


class PlanningPreviewError(ValueError):
    code = "planning_preview_error"


class PlanningPreviewNotFoundError(PlanningPreviewError): code = "planning_preview_not_found"
class PlanningPreviewAthleteMismatchError(PlanningPreviewError): code = "planning_preview_athlete_mismatch"
class PlanningPreviewFingerprintMismatchError(PlanningPreviewError): code = "preview_fingerprint_mismatch"
class PlanningPreviewGoalInvalidError(PlanningPreviewError): code = "planning_preview_goal_invalid"
class PlanningPreviewBlockedError(PlanningPreviewError): code = "planning_preview_blocked"


VISIBLE_TRAINING_PLAN_STATUSES = ("draft", "active")


class TrainingPlanOverlapError(PlanningPreviewError):
    code = "training_plan_overlap"

    def __init__(self, plan: TrainingPlan):
        self.existing_training_plan_id = plan.id
        self.existing_start_date = plan.start_date
        self.existing_end_date = plan.end_date
        super().__init__(self.code)


def persistence_goal_role(season_role: str) -> str:
    """Adapt the richer season role to the historical persistence contract."""
    return "primary" if season_role == "primary" else "supporting"


class PlanningPreviewApplication:
    def __init__(self, session: Session):
        self.session = session

    def generate(self, *, request: PlanningRequest, user_id: UUID) -> TrainingPlanPreview:
        context = PlanningContextAssembler(
            self.session,
            training_load_algorithm_version="0.7b.1",
            load_aggregation_algorithm_version="0.7c.1",
            manual_strength_algorithm_version="0.7e.1",
            training_status_algorithm_version="0.7f.1",
        ).assemble(request)
        season = SeasonStructureBuilder(SeasonStructureConfig(version="0.8F.3", algorithm_version="0.8F.3")).build(context)
        if any(warning.blocking for warning in season.warnings):
            raise PlanningPreviewBlockedError()
        budgets = build_weekly_budget_plan(context, season, WeeklyBudgetConfig(version="0.8F.4", algorithm_version="0.8F.4"))
        session_plan = build_session_plan(context, season, budgets, SessionPlanningConfig(version="0.8F.8", algorithm_version="0.8F.8"))
        workout_config = WorkoutBuilderConfig(version="0.8F.8B", algorithm_version="0.8F.8B")
        prescriptions = tuple(item for week in session_plan.weeks for item in week.sessions)
        drafts = tuple(build_structured_workout(context, item, workout_config) for item in prescriptions)
        roles = {item.goal_id: item.role for item in season.goals}
        artifact_goals = tuple(goal.model_copy(update={"role": roles[goal.competition_goal_id]}) for goal in context.goals)
        artifact = build_preview_artifact(
            athlete_id=request.athlete_id, timezone_name=request.timezone_name,
            context_fingerprint_value=context.fingerprint, season=season, budgets=budgets,
            session_plan=session_plan, goals=artifact_goals, workout_drafts=drafts,
            algorithm_version="0.8F.8B", configuration_version="0.8F.8B",
        )
        row = TrainingPlanPreview(
            athlete_profile_id=request.athlete_id, created_by_user_id=user_id,
            status="pending", artifact=artifact.model_dump(mode="json", exclude_none=True),
            artifact_fingerprint=artifact.fingerprint,
            algorithm_version=artifact.algorithm_version,
            configuration_version=artifact.configuration_version,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def get(self, *, preview_id: UUID, athlete_id: UUID) -> TrainingPlanPreview:
        row = self.session.get(TrainingPlanPreview, preview_id)
        if row is None:
            raise PlanningPreviewNotFoundError()
        if row.athlete_profile_id != athlete_id:
            raise PlanningPreviewAthleteMismatchError()
        return row

    def artifact(self, row: TrainingPlanPreview) -> TrainingPlanPreviewArtifact:
        artifact = TrainingPlanPreviewArtifact.model_validate(row.artifact)
        if artifact.fingerprint != row.artifact_fingerprint:
            raise PlanningPreviewFingerprintMismatchError()
        if artifact.fingerprint != build_preview_artifact(
            athlete_id=artifact.athlete_id, timezone_name=artifact.timezone_name,
            context_fingerprint_value=artifact.context_fingerprint,
            season=artifact.season_structure, budgets=artifact.weekly_budget_plan,
            session_plan=artifact.session_plan, goals=artifact.goals,
            workout_drafts=tuple(item.workout for item in artifact.sessions),
            algorithm_version=artifact.algorithm_version,
            configuration_version=artifact.configuration_version,
        ).fingerprint:
            raise PlanningPreviewFingerprintMismatchError()
        return artifact

    def accept(self, *, preview_id: UUID, athlete_id: UUID, user_id: UUID, role: str, expected_fingerprint: str | None = None, fail_after_sessions: int | None = None) -> TrainingPlan:
        try:
            persisted_role = role if role in {"owner", "athlete", "coach"} else None
            row = self.session.scalar(select(TrainingPlanPreview).where(TrainingPlanPreview.id == preview_id).with_for_update())
            if row is None:
                raise PlanningPreviewNotFoundError()
            if row.athlete_profile_id != athlete_id:
                raise PlanningPreviewAthleteMismatchError()
            if expected_fingerprint is not None and expected_fingerprint != row.artifact_fingerprint:
                raise PlanningPreviewFingerprintMismatchError()
            if row.status == "accepted":
                plan = self.session.scalar(select(TrainingPlan).where(TrainingPlan.source_preview_id == row.id))
                if plan is None or plan.athlete_profile_id != athlete_id:
                    raise PlanningPreviewGoalInvalidError()
                return plan
            artifact = self.artifact(row)
            goal_ids = tuple(item.competition_goal_id for item in artifact.goals)
            goals = tuple(self.session.scalars(select(CompetitionGoal).where(CompetitionGoal.id.in_(goal_ids)).order_by(CompetitionGoal.id)).all())
            if len(goals) != len(goal_ids) or any(item.athlete_profile_id != athlete_id or item.status != "active" for item in goals):
                raise PlanningPreviewGoalInvalidError()
            # Serialize accept operations for this athlete. PostgreSQL holds this
            # row lock until commit/rollback, so a concurrent accept cannot pass
            # the overlap check using a stale view of the athlete's plans.
            locked_athlete = self.session.scalar(
                select(AthleteProfile)
                .where(AthleteProfile.id == athlete_id)
                .with_for_update()
            )
            if locked_athlete is None:
                raise PlanningPreviewAthleteMismatchError()
            overlap = self.session.scalar(
                select(TrainingPlan)
                .where(
                    TrainingPlan.athlete_profile_id == athlete_id,
                    TrainingPlan.status.in_(VISIBLE_TRAINING_PLAN_STATUSES),
                    TrainingPlan.start_date <= artifact.plan_end,
                    TrainingPlan.end_date >= artifact.plan_start,
                )
                .order_by(TrainingPlan.start_date, TrainingPlan.id)
                .limit(1)
            )
            if overlap is not None:
                raise TrainingPlanOverlapError(overlap)
            plan = TrainingPlan(
                athlete_profile_id=athlete_id,
                title=f"Generated training plan {artifact.plan_start.isoformat()}–{artifact.plan_end.isoformat()}",
                start_date=artifact.plan_start, end_date=artifact.plan_end,
                status="draft", origin="ai", created_by_user_id=None,
                created_via_role=persisted_role, algorithm_version=artifact.algorithm_version,
                source_preview_id=row.id,
            )
            self.session.add(plan); self.session.flush()
            current_goals = {item.id: item for item in goals}
            season_goals = {item.goal_id: item for item in artifact.season_structure.goals}
            for goal_id in goal_ids:
                relationship = season_goals[goal_id].role
                self.session.add(TrainingPlanGoal(training_plan_id=plan.id, competition_goal_id=current_goals[goal_id].id, relationship=persistence_goal_role(relationship)))
            created = 0
            for item in artifact.sessions:
                prescription = item.prescription
                if prescription.session_type is SessionType.COMPETITION:
                    continue
                planned = PlannedTrainingSession(
                    athlete_profile_id=athlete_id, training_plan_id=plan.id,
                    scheduled_date=prescription.date, timezone=artifact.timezone_name,
                    sport=prescription.discipline, title=prescription.session_type.value,
                    description=f"purpose={prescription.purpose.value}; target_load={prescription.target_load}",
                    planned_duration_seconds=prescription.target_duration_minutes * 60 if prescription.target_duration_minutes else None,
                    status="planned", origin="ai", created_by_user_id=None,
                    created_via_role=persisted_role, algorithm_version=item.workout.algorithm_version,
                )
                self.session.add(planned); self.session.flush(); created += 1
                if item.workout.buildable and item.workout.definition is not None:
                    payload = structured_workout_payload(item.workout.definition)
                    self.session.add(StructuredWorkout(planned_training_session_id=planned.id, schema_version=1, definition=payload))
                if fail_after_sessions is not None and created >= fail_after_sessions:
                    raise RuntimeError("injected_accept_failure")
            row.status = "accepted"
            row.accepted_by_user_id = user_id
            row.accepted_at = datetime.now(timezone.utc)
            self.session.commit()
            return plan
        except Exception:
            self.session.rollback()
            raise
