"""Read-only composition of D.1, planning, goals, analytics and Q at one instant."""
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.application.execution_overview import ExecutionOverview, ExecutionOverviewApplication
from app.application.training_status_interpretation import TrainingStatusOverviewAssembler
from app.application.queries.dashboard_analytics import DashboardAnalyticsQuery
from app.db.models import CompetitionGoal, PlannedTrainingSession
from app.domains.training_status.interpretation import TrainingStatusInterpretation
from app.domains.training_status import ALGORITHM_VERSION as STATUS_VERSION
from app.domains.manual_strength import ALGORITHM_VERSION as STRENGTH_VERSION
from app.application.training_load import ALGORITHM_VERSION as LOAD_VERSION


class DailySession(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    scheduled_date: date
    scheduled_start_time: time | None
    sport: str
    title: str
    planned_duration_seconds: int | None
    planned_distance_meters: int | None
    status: str


class DailyGoal(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    event_date: date
    event_category: str
    event_format: str
    priority: str
    city: str | None
    days_remaining: int


class AthleteDailyOverview(BaseModel):
    athlete_id: UUID
    as_of_date: date
    timezone: str
    interpretation: TrainingStatusInterpretation
    today_sessions: tuple[DailySession, ...]
    next_session: DailySession | None
    next_goal: DailyGoal | None
    execution: ExecutionOverview
    # Existing analytics payloads; no new calculations or persisted projections.
    summary: dict
    trends: list[dict]
    consistency: dict


class AthleteDailyOverviewApplication:
    def __init__(self, session):
        self.session = session

    def assemble(self, *, athlete_id: UUID, timezone_name: str, now: datetime):
        today = now.astimezone(ZoneInfo(timezone_name)).date()
        with self.session.no_autoflush:
            _, _, interpretation = TrainingStatusOverviewAssembler(self.session).assemble(
                athlete_id=athlete_id, start_date=today, as_of_date=today,
                timezone_name=timezone_name, training_load_algorithm_version=LOAD_VERSION,
                manual_strength_algorithm_version=STRENGTH_VERSION,
                training_status_algorithm_version=STATUS_VERSION)
            base = select(PlannedTrainingSession).where(PlannedTrainingSession.athlete_profile_id == athlete_id)
            order = (PlannedTrainingSession.scheduled_date,
                PlannedTrainingSession.scheduled_start_time.asc().nulls_last(), PlannedTrainingSession.id)
            sessions = self.session.scalars(base.where(PlannedTrainingSession.scheduled_date == today).order_by(*order)).all()
            next_session = self.session.scalar(base.where(
                PlannedTrainingSession.scheduled_date > today).order_by(*order).limit(1))
            goal = self.session.scalar(select(CompetitionGoal).where(
                CompetitionGoal.athlete_profile_id == athlete_id,
                CompetitionGoal.status == "active", CompetitionGoal.event_date > today,
            ).order_by(CompetitionGoal.event_date, CompetitionGoal.created_at, CompetitionGoal.id).limit(1))
            next_goal = None if goal is None else DailyGoal(
                **{field:getattr(goal, field) for field in DailyGoal.model_fields if field != "days_remaining"},
                days_remaining=(goal.event_date-today).days)
            analytics = DashboardAnalyticsQuery(self.session, now=now)
            return AthleteDailyOverview(athlete_id=athlete_id, as_of_date=today, timezone=timezone_name,
                interpretation=interpretation, today_sessions=tuple(DailySession.model_validate(x) for x in sessions),
                next_session=DailySession.model_validate(next_session) if next_session else None, next_goal=next_goal,
                execution=ExecutionOverviewApplication(self.session).assemble(
                    athlete_id=athlete_id, as_of_date=today, timezone_name=timezone_name),
                summary=analytics.summary(athlete_id,"week"), trends=analytics.trends(athlete_id,8),
                consistency=analytics.consistency(athlete_id,12))
