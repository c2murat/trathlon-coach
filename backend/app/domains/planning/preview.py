from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import Field, model_validator

from app.domains.planning.contracts import FrozenModel, PlanningGoal, context_fingerprint
from app.domains.planning.season_structure import SeasonStructure
from app.domains.planning.session_planning import SessionPlan, SessionPrescription, SessionType
from app.domains.planning.weekly_budget import WeeklyBudgetPlan
from app.domains.planning.workout_builder import StructuredWorkoutDraft, structured_workout_payload


PREVIEW_ARTIFACT_SCHEMA_VERSION = 1


class PreviewSessionArtifact(FrozenModel):
    prescription: SessionPrescription
    workout: StructuredWorkoutDraft

    @model_validator(mode="after")
    def validate_pair(self):
        if self.prescription.session_type != self.workout.session_type:
            raise ValueError("workout does not match prescription")
        if self.workout.buildable and self.workout.definition is None:
            raise ValueError("buildable workout requires definition")
        if self.prescription.session_type is SessionType.COMPETITION and self.workout.definition is not None:
            raise ValueError("competition cannot contain workout")
        return self


class TrainingPlanPreviewArtifact(FrozenModel):
    schema_version: int = PREVIEW_ARTIFACT_SCHEMA_VERSION
    athlete_id: UUID
    timezone_name: str
    plan_start: date
    plan_end: date
    context_fingerprint: str
    season_structure: SeasonStructure
    weekly_budget_plan: WeeklyBudgetPlan
    session_plan: SessionPlan
    goals: tuple[PlanningGoal, ...]
    sessions: tuple[PreviewSessionArtifact, ...]
    algorithm_version: str
    configuration_version: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_consistency(self):
        prescriptions = tuple(item for week in self.session_plan.weeks for item in week.sessions)
        if tuple(item.prescription for item in self.sessions) != prescriptions:
            raise ValueError("preview sessions do not match session plan")
        if self.plan_start != self.session_plan.planning_start or self.plan_end != self.session_plan.planning_end:
            raise ValueError("preview dates do not match session plan")
        return self


def preview_artifact_payload(artifact: TrainingPlanPreviewArtifact) -> dict:
    payload = artifact.model_dump(mode="json", exclude={"fingerprint"}, exclude_none=True)
    for item, session in zip(payload["sessions"], artifact.sessions):
        if session.workout.definition is not None:
            item["workout"]["definition"] = structured_workout_payload(session.workout.definition)
    return payload


def build_preview_artifact(*, athlete_id, timezone_name, context_fingerprint_value, season, budgets, session_plan, goals, workout_drafts, algorithm_version, configuration_version):
    prescriptions = tuple(item for week in session_plan.weeks for item in week.sessions)
    if len(prescriptions) != len(workout_drafts):
        raise ValueError("one workout draft is required per prescription")
    sessions = tuple(PreviewSessionArtifact(prescription=item, workout=workout) for item, workout in zip(prescriptions, workout_drafts))
    values = dict(
        athlete_id=athlete_id, timezone_name=timezone_name,
        plan_start=session_plan.planning_start, plan_end=session_plan.planning_end,
        context_fingerprint=context_fingerprint_value, season_structure=season,
        weekly_budget_plan=budgets, session_plan=session_plan, goals=goals,
        sessions=sessions, algorithm_version=algorithm_version,
        configuration_version=configuration_version,
    )
    fingerprint = context_fingerprint(values)
    return TrainingPlanPreviewArtifact(**values, fingerprint=fingerprint)
