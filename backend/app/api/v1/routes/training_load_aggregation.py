from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies.current_athlete import CurrentAthleteContext, get_current_athlete
from app.api.dependencies.athlete_permissions import AthleteCapability, require_athlete_capability
from app.application.combined_training_load_aggregation import (
    AGGREGATION_ALGORITHM_VERSION,
    InvalidAggregationRangeError,
    TrainingLoadAggregationApplication,
)
from app.application.training_status_sync import sync_training_status_after_load_change
from app.domains.manual_strength import ALGORITHM_VERSION as MANUAL_STRENGTH_VERSION
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
    current_athlete: CurrentAthleteContext = Depends(get_current_athlete),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = current_athlete.athlete_id

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
    current_athlete: CurrentAthleteContext = Depends(get_current_athlete),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = current_athlete.athlete_id

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
    current_athlete: CurrentAthleteContext = Depends(require_athlete_capability(AthleteCapability.RECALCULATE_ATHLETE_DATA)),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = current_athlete.athlete_id
    application = TrainingLoadAggregationApplication(session)

    try:
        application.recalculate_daily(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
        sync_training_status_after_load_change(
            session,
            athlete_id=athlete_profile_id,
            affected_start_date=start_date,
            affected_end_date=end_date,
            timezone_name=timezone_name,
            training_load_algorithm_version=source_load_algorithm_version,
            manual_strength_algorithm_version=MANUAL_STRENGTH_VERSION,
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
    current_athlete: CurrentAthleteContext = Depends(require_athlete_capability(AthleteCapability.RECALCULATE_ATHLETE_DATA)),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = current_athlete.athlete_id
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
    current_athlete: CurrentAthleteContext = Depends(require_athlete_capability(AthleteCapability.RECALCULATE_ATHLETE_DATA)),
    session: Session = Depends(get_db_session),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_aggregation_range"},
        )

    athlete_profile_id = current_athlete.athlete_id
    application = TrainingLoadAggregationApplication(session)

    try:
        application.recalculate_all(
            athlete_profile_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            source_load_algorithm_version=source_load_algorithm_version,
        )
        sync_training_status_after_load_change(
            session,
            athlete_id=athlete_profile_id,
            affected_start_date=start_date,
            affected_end_date=end_date,
            timezone_name=timezone_name,
            training_load_algorithm_version=source_load_algorithm_version,
            manual_strength_algorithm_version=MANUAL_STRENGTH_VERSION,
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

