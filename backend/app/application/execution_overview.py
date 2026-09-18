"""Read-only presentation of the existing C.1 execution evidence."""
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from pydantic import field_serializer

from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.db.models import CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession, StructuredWorkout
from app.domains.planning.execution_evidence import FrozenModel, SessionExecutionEvidence, EXECUTION_EVIDENCE_VERSION
from app.domains.planning.models import StructuredWorkoutDefinition


class ActivityFacts(FrozenModel):
    id: UUID
    name: str
    sport: str
    started_at: datetime
    timezone: str
    duration_seconds: int
    distance_meters: float | None
    average_heart_rate_bpm: float | None
    average_power_w: float | None


class ExecutionSessionView(FrozenModel):
    id: UUID
    date: date
    sport: str
    title: str
    planned_duration_seconds: int | None
    planned_distance_meters: int | None
    workout: StructuredWorkoutDefinition | None
    evidence: SessionExecutionEvidence | None
    activities: tuple[ActivityFacts, ...]

    @field_serializer("workout")
    def serialize_workout(self, value):
        # Match the existing planned-workout API contract consumed by WorkoutDetail.
        return value.model_dump(mode="json", exclude_none=True) if value is not None else None


class ExecutionOverview(FrozenModel):
    athlete_id: UUID
    as_of_date: date
    window_start_date: date
    evidence_version: str = EXECUTION_EVIDENCE_VERSION
    latest_activity: ActivityFacts | None
    latest_activity_sessions: tuple[ExecutionSessionView, ...]
    recent_sessions: tuple[ExecutionSessionView, ...]


def activity_facts(row):
    return ActivityFacts(id=row.id, name=row.name, sport=row.sport, started_at=row.start_at,
        timezone=row.timezone, duration_seconds=row.moving_time_s if row.moving_time_s is not None else row.elapsed_time_s,
        distance_meters=row.distance_m, average_heart_rate_bpm=row.average_heart_rate_bpm,
        average_power_w=row.average_power_w)


class ExecutionOverviewApplication:
    def __init__(self, session):
        self.session = session

    def assemble(self, *, athlete_id: UUID, as_of_date: date, timezone_name: str) -> ExecutionOverview:
        with self.session.no_autoflush:
            # Overview's date is inclusive; C.1 accepts an exclusive day boundary.
            # This also evaluates today's linked last activity through C.1 itself.
            context = PrescribedCompletedEvidenceAssembler(self.session).assemble(
                athlete_profile_id=athlete_id, as_of_date=as_of_date+timedelta(days=1))
            evidence = {item.planned_session_id:item for item in context.sessions}
            recent = sorted((item for item in context.sessions if item.planned_date < as_of_date),
                key=lambda item:(item.planned_date,str(item.planned_session_id)), reverse=True)[:5]
            end = datetime.combine(as_of_date+timedelta(days=1), time.min, ZoneInfo(timezone_name)).astimezone(timezone.utc)
            latest = self.session.scalar(select(CompletedActivity).where(
                CompletedActivity.athlete_id == athlete_id, CompletedActivity.deleted_at.is_(None),
                CompletedActivity.provider_deleted_at.is_(None), CompletedActivity.start_at < end,
            ).order_by(CompletedActivity.start_at.desc(), CompletedActivity.id.desc()).limit(1))
            latest_sessions = () if latest is None else tuple(self.session.scalars(select(PlannedSessionActivityLink.planned_training_session_id).where(
                PlannedSessionActivityLink.athlete_profile_id == athlete_id,
                PlannedSessionActivityLink.completed_activity_id == latest.id,
            )).all())
            ids = {item.planned_session_id for item in recent} | set(latest_sessions)
            plans = () if not ids else self.session.execute(select(PlannedTrainingSession, StructuredWorkout)
                .outerjoin(StructuredWorkout, StructuredWorkout.planned_training_session_id == PlannedTrainingSession.id)
                .where(PlannedTrainingSession.athlete_profile_id == athlete_id, PlannedTrainingSession.id.in_(ids))
                .order_by(PlannedTrainingSession.scheduled_date.desc(), PlannedTrainingSession.id.desc())).all()
            activity_ids = {activity_id for planned_id in ids if planned_id in evidence
                for activity_id in evidence[planned_id].source_activity_ids}
            if latest is not None: activity_ids.add(latest.id)
            activities = {} if not activity_ids else {row.id:activity_facts(row) for row in self.session.scalars(
                select(CompletedActivity).where(CompletedActivity.athlete_id == athlete_id,
                    CompletedActivity.id.in_(activity_ids), CompletedActivity.deleted_at.is_(None),
                    CompletedActivity.provider_deleted_at.is_(None))).all()}
            views = {}
            for planned, workout in plans:
                item = evidence.get(planned.id)
                sources = item.source_activity_ids if item is not None else (latest.id,) if latest is not None and planned.id in latest_sessions else ()
                views[planned.id] = ExecutionSessionView(id=planned.id, date=planned.scheduled_date,
                    sport=planned.sport, title=planned.title, planned_duration_seconds=planned.planned_duration_seconds,
                    planned_distance_meters=planned.planned_distance_meters,
                    workout=workout.parsed_definition() if workout else None, evidence=item,
                    activities=tuple(activities[key] for key in sources if key in activities))
            return ExecutionOverview(athlete_id=athlete_id, as_of_date=as_of_date,
                window_start_date=context.window_start_date,
                latest_activity=activity_facts(latest) if latest else None,
                latest_activity_sessions=tuple(view for key,view in views.items() if key in latest_sessions),
                recent_sessions=tuple(views[item.planned_session_id] for item in recent))
