from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import Field, model_validator, model_serializer

from app.domains.planning.contracts import FrozenModel, PlanningGoal, context_fingerprint
from app.domains.planning.season_structure import SeasonStructure
from app.domains.planning.session_planning import SessionPlan, SessionPrescription, SessionType
from app.domains.planning.weekly_budget import WeeklyBudgetPlan
from app.domains.planning.workout_builder import StructuredWorkoutDraft, structured_workout_payload
from app.domains.planning.prescribed_load import PlannedLoadReconciliation, reconcile_plan_load
from app.domains.planning.weekly_intent import StructuralPlanningReport


PREVIEW_ARTIFACT_SCHEMA_VERSION = 1


def _validate_new_workout_leaf_titles(workout_drafts: tuple[StructuredWorkoutDraft, ...]) -> None:
    """Reject newly generated previews with non-portable leaf headings.

    This deliberately lives on the generation path rather than the artifact
    model validator so stored schema-v1 artifacts without titles remain
    readable.
    """
    for draft in workout_drafts:
        if draft.definition is None:
            continue
        pending = list(draft.definition.steps)
        while pending:
            node = pending.pop()
            if node.kind == "repeat":
                pending.extend(node.steps or ())
            elif not (node.title or "").strip():
                raise ValueError(
                    f"new preview workout leaf requires title: {draft.session_type.value}"
                )


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
    structural_planning: StructuralPlanningReport | None = None
    load_reconciliation: PlannedLoadReconciliation | None = None
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

    @model_serializer(mode="wrap")
    def serialize_legacy_compatible(self, handler, info):
        data = handler(self)
        if self.structural_planning is None:
            data.pop("structural_planning", None)
        elif "structural_planning" in data:
            # Persistence uses exclude_none=True for historical artifacts. The
            # intent contract distinguishes unknown quantities explicitly.
            data["structural_planning"] = self.structural_planning.model_dump(mode=info.mode)
            if "load_reconciliation" in data and self.load_reconciliation is not None:
                data["load_reconciliation"] = self.load_reconciliation.model_dump(mode=info.mode)
        return data

    @model_validator(mode="after")
    def validate_consistency(self):
        prescriptions = tuple(item for week in self.session_plan.weeks for item in week.sessions)
        if tuple(item.prescription for item in self.sessions) != prescriptions:
            raise ValueError("preview sessions do not match session plan")
        if self.plan_start != self.session_plan.planning_start or self.plan_end != self.session_plan.planning_end:
            raise ValueError("preview dates do not match session plan")
        if self.structural_planning is not None:
            if self.structural_planning.athlete_id != self.athlete_id or self.structural_planning.context_fingerprint != self.context_fingerprint:
                raise ValueError("structural report context mismatch")
            if len(self.structural_planning.weeks) != len(self.session_plan.weeks):
                raise ValueError("structural report week mismatch")
            for result, week in zip(self.structural_planning.weeks, self.session_plan.weeks, strict=True):
                result.intent.validate_structure()
                if result.placed != sum(s.discipline != "competition" for s in week.sessions) or result.placed + len(result.unplaced) != result.intended_sessions:
                    raise ValueError("structural report placement mismatch")
        return self


def preview_artifact_payload(artifact: TrainingPlanPreviewArtifact) -> dict:
    # Diagnostic metadata is intentionally outside prescription identity.
    payload = artifact.model_dump(mode="json", exclude={"fingerprint", "load_reconciliation", "structural_planning"}, exclude_none=True)
    for item, session in zip(payload["sessions"], artifact.sessions):
        if session.workout.definition is not None:
            item["workout"]["definition"] = structured_workout_payload(session.workout.definition)
    return payload


def build_preview_artifact(*, athlete_id, timezone_name, context_fingerprint_value, season, budgets, session_plan, goals, workout_drafts, algorithm_version, configuration_version, structural_planning=None):
    prescriptions = tuple(item for week in session_plan.weeks for item in week.sessions)
    if len(prescriptions) != len(workout_drafts):
        raise ValueError("one workout draft is required per prescription")
    _validate_new_workout_leaf_titles(workout_drafts)
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
    return TrainingPlanPreviewArtifact(**values, fingerprint=fingerprint,
        load_reconciliation=reconcile_plan_load(session_plan, workout_drafts), structural_planning=structural_planning)
