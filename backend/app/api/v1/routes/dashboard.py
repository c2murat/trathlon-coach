from datetime import datetime
from typing import Literal
from datetime import date
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.dependencies.current_athlete import CurrentAthleteContext, get_current_athlete
from app.application.queries.dashboard_analytics import DashboardAnalyticsQuery
from app.db.session import get_db_session
from app.db.base import utc_now
from app.application.execution_overview import ExecutionOverview, ExecutionOverviewApplication

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

from app.application.athlete_daily_overview import AthleteDailyOverview, AthleteDailyOverviewApplication


@router.get("/daily-overview", response_model=AthleteDailyOverview)
def daily_overview(response: Response,
    current_athlete: CurrentAthleteContext = Depends(get_current_athlete), session: Session = Depends(get_db_session)):
    response.headers["Cache-Control"] = "private, no-store"
    return AthleteDailyOverviewApplication(session).assemble(athlete_id=current_athlete.athlete_id,
        timezone_name=current_athlete.athlete_profile.timezone, now=utc_now())

@router.get("/execution-overview", response_model=ExecutionOverview)
def execution_overview(response: Response, as_of_date: date | None = None,
    current_athlete: CurrentAthleteContext = Depends(get_current_athlete), session: Session = Depends(get_db_session)):
    zone = current_athlete.athlete_profile.timezone
    today = utc_now().astimezone(ZoneInfo(zone)).date()
    cutoff = as_of_date or today
    if cutoff > today or cutoff < date(2000,1,1):
        raise HTTPException(422, detail={"code":"invalid_execution_cutoff"})
    response.headers["Cache-Control"] = "private, no-store"
    return ExecutionOverviewApplication(session).assemble(athlete_id=current_athlete.athlete_id,
        as_of_date=cutoff, timezone_name=zone)

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
