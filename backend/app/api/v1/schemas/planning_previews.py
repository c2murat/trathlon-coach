from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domains.planning.contracts import PlanningPreferences
from app.domains.planning.preview import TrainingPlanPreviewArtifact


class PlanningPreviewCreate(BaseModel):
    planning_date: date
    start_date: date
    horizon_end_date: date | None = None
    goal_ids: tuple[UUID, ...] = Field(min_length=1)
    preferences: PlanningPreferences | None = None


class PlanningPreviewAccept(BaseModel):
    expected_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class PlanningPreviewResponse(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    accepted_at: datetime | None
    accepted_training_plan_id: UUID | None
    artifact: TrainingPlanPreviewArtifact


class TrainingPlanAcceptedResponse(BaseModel):
    training_plan_id: UUID
    preview_id: UUID
    status: str
