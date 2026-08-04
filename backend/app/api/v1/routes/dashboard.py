from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.dependencies.current_athlete import CurrentAthleteContext, get_current_athlete
from app.application.queries.dashboard_analytics import DashboardAnalyticsQuery
from app.db.session import get_db_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
class SportBreakdownResponse(BaseModel):
    sport_type: str; activity_count: int; moving_time_seconds: int; distance_metres: float; elevation_metres: float
class SummaryResponse(BaseModel):
    period: str; period_start: datetime; period_end: datetime; activity_count: int; total_moving_time_seconds: int; total_distance_metres: float; total_elevation_metres: float; active_days: int; longest_activity_seconds: int; longest_activity_distance_metres: float; sport_breakdown: list[SportBreakdownResponse]
class TrendResponse(BaseModel):
    week_start: datetime; week_end: datetime; activity_count: int; moving_time_seconds: int; distance_metres: float; elevation_metres: float; active_days: int
class ConsistencyResponse(BaseModel):
    weeks: int; active_weeks: int; current_training_streak_weeks: int; longest_training_streak_weeks: int; average_active_days_per_week: float; average_moving_time_seconds_per_week: float; last_activity_at: datetime | None
@router.get("/summary", response_model=SummaryResponse)
def summary(period: Literal["week","month","last_30_days","year"]="week", current_athlete:CurrentAthleteContext=Depends(get_current_athlete), session:Session=Depends(get_db_session)): return DashboardAnalyticsQuery(session).summary(current_athlete.athlete_id, period)
@router.get("/trends", response_model=list[TrendResponse])
def trends(weeks:int=Query(8,ge=4,le=52), current_athlete:CurrentAthleteContext=Depends(get_current_athlete), session:Session=Depends(get_db_session)): return DashboardAnalyticsQuery(session).trends(current_athlete.athlete_id, weeks)
@router.get("/consistency", response_model=ConsistencyResponse)
def consistency(weeks:int=Query(12,ge=4,le=52), current_athlete:CurrentAthleteContext=Depends(get_current_athlete), session:Session=Depends(get_db_session)): return DashboardAnalyticsQuery(session).consistency(current_athlete.athlete_id, weeks)
