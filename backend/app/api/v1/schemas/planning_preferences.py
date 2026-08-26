from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.planning.contracts import PlanningPreferences


class PlanningPreferencesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    athlete_profile_id: UUID
    version_number: int
    created_at: datetime
    preferences: PlanningPreferences
