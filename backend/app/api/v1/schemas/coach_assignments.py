from uuid import UUID
from pydantic import BaseModel, ConfigDict


class CoachCandidateResponse(BaseModel):
    user_id: UUID
    display_name: str
    email: str


class AthleteCandidateResponse(BaseModel):
    athlete_profile_id: UUID
    display_name: str


class CoachAssignmentCandidatesResponse(BaseModel):
    coaches: list[CoachCandidateResponse]
    athletes: list[AthleteCandidateResponse]


class CoachAssignmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coach_user_id: UUID
    athlete_profile_id: UUID


class CoachAssignmentResponse(BaseModel):
    membership_id: UUID
    coach_user_id: UUID
    coach_display_name: str
    coach_email: str
    athlete_profile_id: UUID
    athlete_display_name: str
    is_active: bool
    is_default: bool
