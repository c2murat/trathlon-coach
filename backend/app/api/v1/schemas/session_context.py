from uuid import UUID
from pydantic import BaseModel
class CurrentUserResponse(BaseModel):
    id: UUID
    display_name: str
    email: str | None = None
    account_plan: str
class AthleteMembershipResponse(BaseModel):
    athlete_id: UUID
    label: str
    role: str
    is_default: bool
    capabilities: list[str]
class SessionContextResponse(BaseModel):
    user: CurrentUserResponse
    athletes: list[AthleteMembershipResponse]
    selected_athlete_id: UUID | None
    selection_required: bool
