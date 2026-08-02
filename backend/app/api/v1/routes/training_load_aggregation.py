from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.application.combined_training_load_aggregation import (
    AGGREGATION_ALGORITHM_VERSION,
    InvalidAggregationRangeError,
    TrainingLoadAggregationApplication,
)
from app.db.models import AthleteProfile
from app.db.session import get_db_session


router = APIRouter(
    prefix="/training-load",
    tags=["training-load"],
)


class DailyTrainingLoadResponse(BaseModel):
    id: UUID
    local_date: date
    timezone_name: str
    source_load_algorithm_version: str
    aggregation_algorithm_version: str
    total_load: float
    endurance_load: float
    strength_load: float
    strength_session_count: int
    manual_strength_algorithm_version: str
    activity_count: int
    loaded_activity_count: int
    null_load_activity_count: int
    total_duration_seconds: float
    coverage: str
    quality: str
    warnings: list
    activity_ids: list
    calculated_at: datetime


class WeeklyTrainingLoadResponse(BaseModel):
    id: UUID
    iso_year: int
    iso_week: int
    week_start_date: date
    week_end_date: date
    timezone_name: str
    source_load_algorithm_version: str
    aggregation_algorithm_version: str
    total_load: float
    endurance_load: float
    strength_load: float
    strength_session_count: int
    manual_strength_algorithm_version: str
    activity_count: int
    loaded_activity_count: int
    null_load_activity_count: int
    total_duration_seconds: float
    coverage: str
    quality: str
    warnings: list
    activity_ids: list
    calculated_at: datetime


def _get_athlete_profile_id(
    current_user: AuthenticatedUser,
    session: Session,
) -> UUID:
    athlete = session.scalar(
        select(AthleteProfile).where(
            AthleteProfile.user_id == current_user.id
        )
    )
    return athlete.id if athlete else current_user.id


@router.get("/daily", response_model=list[DailyTrainingLoadResponse])
def get_daily_training_load(
    start_date: date,
    end_date: date,
    timezone_name: str = Query(..., min_length=1, max_length=64),
    source_load_algorithm_version: str = Query(
        "0.7b.1",
        min_length=1,
        max_length=32,
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = _get_athlete_profile_id(current_user, session)

    try:
        rows = TrainingLoadAggregationApplication(
            session
        ).get_daily_aggregates(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
    except InvalidAggregationRangeError:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    return [
        DailyTrainingLoadResponse.model_validate(
            row,
            from_attributes=True,
        )
        for row in rows
    ]



@router.get("/weekly", response_model=list[WeeklyTrainingLoadResponse])
def get_weekly_training_load(
    start_date: date,
    end_date: date,
    timezone_name: str = Query(..., min_length=1, max_length=64),
    source_load_algorithm_version: str = Query(
        "0.7b.1",
        min_length=1,
        max_length=32,
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = _get_athlete_profile_id(current_user, session)

    weekly_start = start_date - timedelta(days=start_date.weekday())
    weekly_end = end_date + timedelta(days=6 - end_date.weekday())

    rows = TrainingLoadAggregationApplication(
        session
    ).get_weekly_aggregates(
        athlete_profile_id,
        start_date=weekly_start,
        end_date=weekly_end,
        timezone_name=timezone_name,
        source_load_algorithm_version=source_load_algorithm_version,
    )

    return [
        WeeklyTrainingLoadResponse.model_validate(
            row,
            from_attributes=True,
        )
        for row in rows
    ]


@router.post(
    "/daily/recalculate",
    response_model=list[DailyTrainingLoadResponse],
)
def recalculate_daily_training_load(
    start_date: date,
    end_date: date,
    timezone_name: str = Query(..., min_length=1, max_length=64),
    source_load_algorithm_version: str = Query(
        "0.7b.1",
        min_length=1,
        max_length=32,
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = _get_athlete_profile_id(current_user, session)
    application = TrainingLoadAggregationApplication(session)

    try:
        application.recalculate_daily(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
        session.commit()

        rows = application.get_daily_aggregates(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
    except InvalidAggregationRangeError:
        session.rollback()
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )
    except Exception:
        session.rollback()
        raise

    return [
        DailyTrainingLoadResponse.model_validate(
            row,
            from_attributes=True,
        )
        for row in rows
    ]


@router.post(
    "/weekly/recalculate",
    response_model=list[WeeklyTrainingLoadResponse],
)
def recalculate_weekly_training_load(
    start_date: date,
    end_date: date,
    timezone_name: str = Query(..., min_length=1, max_length=64),
    source_load_algorithm_version: str = Query(
        "0.7b.1",
        min_length=1,
        max_length=32,
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = _get_athlete_profile_id(current_user, session)
    application = TrainingLoadAggregationApplication(session)

    try:
        application.recalculate_weekly(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
        session.commit()

        weekly_start = start_date - timedelta(days=start_date.weekday())
        weekly_end = end_date + timedelta(days=6 - end_date.weekday())

        rows = application.get_weekly_aggregates(
            athlete_profile_id,
            start_date=weekly_start,
            end_date=weekly_end,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
    except InvalidAggregationRangeError:
        session.rollback()
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )
    except Exception:
        session.rollback()
        raise

    return [
        WeeklyTrainingLoadResponse.model_validate(
            row,
            from_attributes=True,
        )
        for row in rows
    ]


class TrainingLoadRecalculationResponse(BaseModel):
    daily: list[DailyTrainingLoadResponse]
    weekly: list[WeeklyTrainingLoadResponse]


@router.post(
    "/recalculate",
    response_model=TrainingLoadRecalculationResponse,
)
def recalculate_training_load(
    start_date: date,
    end_date: date,
    timezone_name: str = Query(..., min_length=1, max_length=64),
    source_load_algorithm_version: str = Query(
        "0.7b.1",
        min_length=1,
        max_length=32,
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = _get_athlete_profile_id(current_user, session)
    application = TrainingLoadAggregationApplication(session)

    try:
        application.recalculate_all(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
        session.commit()

        daily_rows = application.get_daily_aggregates(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )

        weekly_start = start_date - timedelta(days=start_date.weekday())
        weekly_end = end_date + timedelta(days=6 - end_date.weekday())

        weekly_rows = application.get_weekly_aggregates(
            athlete_profile_id,
            start_date=weekly_start,
            end_date=weekly_end,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
    except InvalidAggregationRangeError:
        session.rollback()
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )
    except Exception:
        session.rollback()
        raise

    return TrainingLoadRecalculationResponse(
        daily=[
            DailyTrainingLoadResponse.model_validate(
                row,
                from_attributes=True,
            )
            for row in daily_rows
        ],
        weekly=[
            WeeklyTrainingLoadResponse.model_validate(
                row,
                from_attributes=True,
            )
            for row in weekly_rows
        ],
    )

