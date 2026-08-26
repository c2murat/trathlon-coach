from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.athlete_permissions import AthleteCapability, require_athlete_capability
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.schemas.planning_preferences import PlanningPreferencesResponse
from app.application.planning_preferences import (
    PlanningPreferencesApplication,
    PlanningPreferencesNotFoundError,
    preferences_from_row,
)
from app.db.session import get_db_session
from app.domains.planning.contracts import PlanningPreferences


router = APIRouter(prefix="/planning/preferences", tags=["planning-preferences"])
read = require_athlete_capability(AthleteCapability.READ_TRAINING_PLANNING)
write = require_athlete_capability(AthleteCapability.MANAGE_PLANNING_PREFERENCES)


def _response(row):
    return PlanningPreferencesResponse(
        id=row.id,
        athlete_profile_id=row.athlete_profile_id,
        version_number=row.version_number,
        created_at=row.created_at,
        preferences=preferences_from_row(row),
    )


@router.get("", response_model=PlanningPreferencesResponse)
def get_preferences(
    current: CurrentAthleteContext = Depends(read),
    session: Session = Depends(get_db_session),
):
    try:
        return _response(PlanningPreferencesApplication(session).require_latest(current.athlete_id))
    except PlanningPreferencesNotFoundError:
        raise HTTPException(status_code=404, detail={"code": "planning_preferences_not_found"}) from None


@router.put("", response_model=PlanningPreferencesResponse)
def replace_preferences(
    payload: PlanningPreferences,
    current: CurrentAthleteContext = Depends(write),
    session: Session = Depends(get_db_session),
):
    try:
        row = PlanningPreferencesApplication(session).replace(current.athlete_id, current.user_id, payload)
        session.commit()
        return _response(row)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": "planning_preferences_version_conflict"},
        ) from error
    except Exception:
        session.rollback()
        raise
