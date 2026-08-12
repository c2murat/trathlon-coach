from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.athlete_permissions import AthleteCapability, require_athlete_capability
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.schemas.athlete_profile import AthleteProfileCompletenessResponse, AthleteProfileResponse, AthleteProfileUpdateRequest
from app.application.athlete_profile import AthleteProfileApplication, AthleteProfileUpdateEmptyError, AthleteProfileValidationError, get_athlete_profile_completeness
from app.db.models import AthleteProfile
from app.db.session import get_db_session

router = APIRouter(prefix="/athlete/profile", tags=["athlete-profile"])
read_profile = require_athlete_capability(AthleteCapability.READ_ATHLETE_DATA)
edit_profile = require_athlete_capability(AthleteCapability.EDIT_ATHLETE_PROFILE)

def serialize(profile: AthleteProfile) -> AthleteProfileResponse:
    completeness = get_athlete_profile_completeness(profile)
    return AthleteProfileResponse(id=profile.id, display_name=profile.display_name, timezone=profile.timezone, unit_system=profile.unit_system, birth_year=profile.birth_year, sex_for_training_context=profile.sex_for_training_context, height_m=float(profile.height_m) if profile.height_m is not None else None, weight_kg=float(profile.weight_kg) if profile.weight_kg is not None else None, updated_at=profile.updated_at, completeness=AthleteProfileCompletenessResponse(status=completeness.status, missing_recommended_fields=list(completeness.missing_recommended_fields)))

@router.get("", response_model=AthleteProfileResponse)
def get_profile(current_athlete: CurrentAthleteContext = Depends(read_profile)) -> AthleteProfileResponse:
    return serialize(current_athlete.athlete_profile)

@router.patch("", response_model=AthleteProfileResponse)
def update_profile(payload: AthleteProfileUpdateRequest, current_athlete: CurrentAthleteContext = Depends(edit_profile), session: Session = Depends(get_db_session)) -> AthleteProfileResponse:
    try:
        profile = AthleteProfileApplication(session).update(current_athlete.athlete_profile, payload.model_dump(exclude_unset=True))
        session.commit()
        session.refresh(profile)
        return serialize(profile)
    except AthleteProfileUpdateEmptyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "athlete_profile_update_empty"}) from None
    except AthleteProfileValidationError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": exc.code}) from None
    except Exception:
        session.rollback()
        raise