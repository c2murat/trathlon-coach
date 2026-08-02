from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.schemas.manual_strength import (
    ManualStrengthSessionCreateRequest,
    ManualStrengthSessionResponse,
    ManualStrengthSessionUpdateRequest,
    ManualStrengthTrainingLoadResponse,
)
from app.application.manual_strength import (
    InvalidManualStrengthSessionInputError,
    ManualStrengthApplication,
    ManualStrengthApplicationError,
    ManualStrengthAthleteNotFoundError,
    ManualStrengthSessionNotFoundError,
)
from app.db.models import AthleteProfile, ManualStrengthSession, ManualStrengthTrainingLoad
from app.db.session import get_db_session
from app.domains.manual_strength import ALGORITHM_VERSION

router = APIRouter(
    prefix="/manual-strength-sessions", tags=["Manual strength sessions"]
)


def _active_athlete(session: Session, user: AuthenticatedUser) -> AthleteProfile:
    athlete = session.scalar(
        select(AthleteProfile).where(AthleteProfile.user_id == user.id)
    )
    if athlete is None:
        raise HTTPException(status_code=404, detail={"code": "athlete_not_found"})
    return athlete


def _http_error(error: ManualStrengthApplicationError) -> HTTPException:
    if isinstance(error, ManualStrengthSessionNotFoundError):
        return HTTPException(
            status_code=404, detail={"code": "manual_strength_session_not_found"}
        )
    if isinstance(error, ManualStrengthAthleteNotFoundError):
        return HTTPException(status_code=404, detail={"code": "athlete_not_found"})
    if isinstance(error, InvalidManualStrengthSessionInputError):
        return HTTPException(
            status_code=422,
            detail={"code": "invalid_manual_strength_session", "message": str(error)},
        )
    return HTTPException(
        status_code=500, detail={"code": "manual_strength_application_error"}
    )


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=500, detail={"code": "manual_strength_persistence_error"}
    )


def _load_map(
    session: Session, session_ids: list[UUID]
) -> dict[UUID, ManualStrengthTrainingLoad]:
    if not session_ids:
        return {}
    rows = session.scalars(
        select(ManualStrengthTrainingLoad).where(
            ManualStrengthTrainingLoad.session_id.in_(session_ids),
            ManualStrengthTrainingLoad.algorithm_version == ALGORITHM_VERSION,
        )
    ).all()
    return {row.session_id: row for row in rows}


def _load_response(
    load: ManualStrengthTrainingLoad,
) -> ManualStrengthTrainingLoadResponse:
    return ManualStrengthTrainingLoadResponse(
        load_value=float(load.load_value),
        method=load.method,
        unit=load.unit,
        quality=load.quality,
        warnings=list(load.warnings),
        algorithm_version=load.algorithm_version,
        calculated_at=load.calculated_at,
    )


def _session_response(
    row: ManualStrengthSession, load: ManualStrengthTrainingLoad
) -> ManualStrengthSessionResponse:
    return ManualStrengthSessionResponse(
        id=row.id,
        started_at=row.started_at,
        timezone_name=row.timezone_name,
        duration_minutes=row.duration_minutes,
        body_regions=list(row.body_regions),
        perceived_exertion=row.perceived_exertion,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
        training_load=_load_response(load),
    )


def _current_load(session: Session, session_id: UUID) -> ManualStrengthTrainingLoad:
    load = _load_map(session, [session_id]).get(session_id)
    if load is None:
        raise HTTPException(
            status_code=500, detail={"code": "manual_strength_load_missing"}
        )
    return load


@router.post("", response_model=ManualStrengthSessionResponse, status_code=201)
def create_session(
    body: ManualStrengthSessionCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete = _active_athlete(session, current_user)
    try:
        row = ManualStrengthApplication(session).create_manual_strength_session(
            athlete.id,
            started_at=body.started_at,
            timezone_name=body.timezone_name,
            duration_minutes=body.duration_minutes,
            body_regions=tuple(body.body_regions),
            perceived_exertion=body.perceived_exertion,
            notes=body.notes,
        )
        load = _current_load(session, row.id)
        session.commit()
        return _session_response(row, load)
    except ManualStrengthApplicationError as error:
        session.rollback()
        raise _http_error(error) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise _database_error() from error


@router.get("", response_model=list[ManualStrengthSessionResponse])
def list_sessions(
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete = _active_athlete(session, current_user)
    if start_at is not None and (start_at.tzinfo is None or start_at.utcoffset() is None):
        raise HTTPException(422, detail={"code": "naive_start_at"})
    if end_at is not None and (end_at.tzinfo is None or end_at.utcoffset() is None):
        raise HTTPException(422, detail={"code": "naive_end_at"})
    if start_at is not None and end_at is not None and end_at < start_at:
        raise HTTPException(422, detail={"code": "invalid_date_range"})
    try:
        rows = ManualStrengthApplication(session).list_manual_strength_sessions(
            athlete.id, start_at=start_at, end_at=end_at
        )[offset : offset + limit]
    except ManualStrengthApplicationError as error:
        raise _http_error(error) from error
    loads = _load_map(session, [row.id for row in rows])
    return [_session_response(row, loads[row.id]) for row in rows]


@router.get("/{session_id}", response_model=ManualStrengthSessionResponse)
def get_session(
    session_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete = _active_athlete(session, current_user)
    try:
        row = ManualStrengthApplication(session).get_manual_strength_session(
            athlete.id, session_id
        )
    except ManualStrengthApplicationError as error:
        raise _http_error(error) from error
    return _session_response(row, _current_load(session, row.id))


@router.patch("/{session_id}", response_model=ManualStrengthSessionResponse)
def update_session(
    session_id: UUID,
    body: ManualStrengthSessionUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    if not body.model_fields_set:
        raise HTTPException(422, detail={"code": "empty_update"})
    values = body.model_dump(exclude_unset=True)
    if "body_regions" in values and values["body_regions"] is not None:
        values["body_regions"] = tuple(values["body_regions"])
    athlete = _active_athlete(session, current_user)
    try:
        row = ManualStrengthApplication(session).update_manual_strength_session(
            athlete.id, session_id, **values
        )
        load = _current_load(session, row.id)
        session.commit()
        return _session_response(row, load)
    except ManualStrengthApplicationError as error:
        session.rollback()
        raise _http_error(error) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise _database_error() from error


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete = _active_athlete(session, current_user)
    try:
        ManualStrengthApplication(session).delete_manual_strength_session(
            athlete.id, session_id
        )
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ManualStrengthApplicationError as error:
        session.rollback()
        raise _http_error(error) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise _database_error() from error


@router.post(
    "/{session_id}/training-load/recalculate",
    response_model=ManualStrengthTrainingLoadResponse,
)
def recalculate_load(
    session_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    athlete = _active_athlete(session, current_user)
    try:
        load = ManualStrengthApplication(session).recalculate_manual_strength_load(
            athlete.id, session_id
        )
        session.commit()
        return _load_response(load)
    except ManualStrengthApplicationError as error:
        session.rollback()
        raise _http_error(error) from error
    except SQLAlchemyError as error:
        session.rollback()
        raise _database_error() from error
