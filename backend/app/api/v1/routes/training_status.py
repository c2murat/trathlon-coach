from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.schemas.training_status import DailyTrainingStatusResponse
from app.application.training_status import (
    DuplicateTrainingStatusSourceDateError,
    InvalidTrainingStatusApplicationRangeError,
    InvalidTrainingStatusSourceDataError,
    InvalidTrainingStatusTimezoneError,
    InvalidTrainingStatusVersionError,
    TrainingStatusApplication,
    TrainingStatusApplicationError,
    TrainingStatusAthleteNotFoundError,
    TrainingStatusPersistenceError,
)
from app.db.models import AthleteDailyTrainingStatus, AthleteProfile
from app.db.session import get_db_session
from app.domains.manual_strength import ALGORITHM_VERSION as MANUAL_STRENGTH_VERSION
from app.domains.training_status import ALGORITHM_VERSION as TRAINING_STATUS_VERSION


TRAINING_LOAD_VERSION = "0.7b.1"

router = APIRouter(prefix="/training-status", tags=["Training status"])


def _active_athlete_id(
    session: Session,
    current_user: AuthenticatedUser,
) -> UUID:
    athlete = session.scalar(
        select(AthleteProfile).where(AthleteProfile.user_id == current_user.id)
    )
    if athlete is None:
        raise HTTPException(status_code=404, detail={"code": "athlete_not_found"})
    return athlete.id


def _response(row: AthleteDailyTrainingStatus) -> DailyTrainingStatusResponse:
    return DailyTrainingStatusResponse(
        date=row.local_date,
        timezone_name=row.timezone_name,
        total_load=float(row.total_load),
        fitness=float(row.fitness),
        fatigue=float(row.fatigue),
        form=float(row.form),
        history_day_number=row.history_day_number,
        is_warmup=bool(row.is_warmup),
        training_load_algorithm_version=row.training_load_algorithm_version,
        manual_strength_algorithm_version=row.manual_strength_algorithm_version,
        training_status_algorithm_version=row.training_status_algorithm_version,
        calculated_at=row.calculated_at,
    )


def _application_error(error: TrainingStatusApplicationError) -> HTTPException:
    if isinstance(error, TrainingStatusAthleteNotFoundError):
        return HTTPException(status_code=404, detail={"code": "athlete_not_found"})
    if isinstance(error, InvalidTrainingStatusApplicationRangeError):
        return HTTPException(
            status_code=422, detail={"code": "invalid_training_status_range"}
        )
    if isinstance(error, InvalidTrainingStatusTimezoneError):
        return HTTPException(status_code=422, detail={"code": "invalid_timezone"})
    if isinstance(error, InvalidTrainingStatusVersionError):
        return HTTPException(
            status_code=422, detail={"code": "invalid_algorithm_version"}
        )
    if isinstance(error, InvalidTrainingStatusSourceDataError):
        return HTTPException(
            status_code=422, detail={"code": "invalid_training_status_source"}
        )
    if isinstance(error, DuplicateTrainingStatusSourceDateError):
        return HTTPException(
            status_code=422,
            detail={"code": "duplicate_training_status_source_date"},
        )
    if isinstance(error, TrainingStatusPersistenceError):
        return HTTPException(
            status_code=500,
            detail={"code": "training_status_persistence_error"},
        )
    return HTTPException(
        status_code=500, detail={"code": "training_status_application_error"}
    )


def _version_parameters(
    training_load_algorithm_version: str,
    manual_strength_algorithm_version: str,
    training_status_algorithm_version: str,
) -> dict[str, str]:
    return {
        "training_load_algorithm_version": training_load_algorithm_version,
        "manual_strength_algorithm_version": manual_strength_algorithm_version,
        "training_status_algorithm_version": training_status_algorithm_version,
    }


@router.get("", response_model=list[DailyTrainingStatusResponse])
def list_training_status(
    start_date: date,
    end_date: date,
    timezone_name: str = Query(..., min_length=1, max_length=64),
    training_load_algorithm_version: str = Query(
        TRAINING_LOAD_VERSION, min_length=1, max_length=32
    ),
    manual_strength_algorithm_version: str = Query(
        MANUAL_STRENGTH_VERSION, min_length=1, max_length=32
    ),
    training_status_algorithm_version: str = Query(
        TRAINING_STATUS_VERSION, min_length=1, max_length=32
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete_id = _active_athlete_id(session, current_user)
    try:
        rows = TrainingStatusApplication(session).list_training_status(
            athlete_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            **_version_parameters(
                training_load_algorithm_version,
                manual_strength_algorithm_version,
                training_status_algorithm_version,
            ),
        )
    except TrainingStatusApplicationError as error:
        raise _application_error(error) from error
    return [_response(row) for row in rows]


@router.get("/latest", response_model=DailyTrainingStatusResponse)
def latest_training_status(
    timezone_name: str = Query(..., min_length=1, max_length=64),
    training_load_algorithm_version: str = Query(
        TRAINING_LOAD_VERSION, min_length=1, max_length=32
    ),
    manual_strength_algorithm_version: str = Query(
        MANUAL_STRENGTH_VERSION, min_length=1, max_length=32
    ),
    training_status_algorithm_version: str = Query(
        TRAINING_STATUS_VERSION, min_length=1, max_length=32
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete_id = _active_athlete_id(session, current_user)
    try:
        row = TrainingStatusApplication(session).get_latest_training_status(
            athlete_id,
            timezone_name=timezone_name,
            **_version_parameters(
                training_load_algorithm_version,
                manual_strength_algorithm_version,
                training_status_algorithm_version,
            ),
        )
    except TrainingStatusApplicationError as error:
        raise _application_error(error) from error
    if row is None:
        raise HTTPException(
            status_code=404, detail={"code": "training_status_not_found"}
        )
    return _response(row)


@router.post("/recalculate", response_model=list[DailyTrainingStatusResponse])
def recalculate_training_status(
    start_date: date,
    end_date: date,
    timezone_name: str = Query(..., min_length=1, max_length=64),
    training_load_algorithm_version: str = Query(
        TRAINING_LOAD_VERSION, min_length=1, max_length=32
    ),
    manual_strength_algorithm_version: str = Query(
        MANUAL_STRENGTH_VERSION, min_length=1, max_length=32
    ),
    training_status_algorithm_version: str = Query(
        TRAINING_STATUS_VERSION, min_length=1, max_length=32
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete_id = _active_athlete_id(session, current_user)
    try:
        rows = TrainingStatusApplication(session).recalculate_training_status(
            athlete_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            **_version_parameters(
                training_load_algorithm_version,
                manual_strength_algorithm_version,
                training_status_algorithm_version,
            ),
        )
        session.commit()
    except TrainingStatusApplicationError as error:
        session.rollback()
        raise _application_error(error) from error
    except Exception:
        session.rollback()
        raise
    return [_response(row) for row in rows]
