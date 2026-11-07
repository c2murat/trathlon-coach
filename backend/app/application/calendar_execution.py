"""Batch presentation of C.1 for past calendar sessions, without writes."""
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.application.execution_overview import ExecutionSessionView, activity_facts, manual_strength_facts
from app.domains.planning.execution_evidence import FrozenModel, EXECUTION_EVIDENCE_VERSION


class CalendarExecution(FrozenModel):
    athlete_id: UUID
    as_of_date: date
    timezone: str
    start_date: date
    end_date: date
    evidence_version: str = EXECUTION_EVIDENCE_VERSION
    sessions: tuple[ExecutionSessionView, ...]


class CalendarExecutionApplication:
    def __init__(self, session):
        self.session = session

    def assemble(self, *, athlete_id: UUID, start_date: date, end_date: date, timezone_name: str, now: datetime):
        today = now.astimezone(ZoneInfo(timezone_name)).date()
        views = ()
        if start_date < today:
            with self.session.no_autoflush:
                batch = PrescribedCompletedEvidenceAssembler(self.session).assemble_range(
                    athlete_profile_id=athlete_id, start_date=start_date,
                    end_date_exclusive=min(today, end_date+timedelta(days=1)))
                evidence = {item.planned_session_id:item for item in batch.sessions}
                activities = {row.id:activity_facts(row) for row in batch.activities}
                activities.update({row.id:manual_strength_facts(row) for row in batch.manual_strength_sessions})
                views = tuple(ExecutionSessionView(id=planned.id, date=planned.scheduled_date,
                    sport=planned.sport, title=planned.title, planned_duration_seconds=planned.planned_duration_seconds,
                    planned_distance_meters=planned.planned_distance_meters,
                    workout=workout.parsed_definition() if workout else None, evidence=evidence[planned.id],
                    activities=tuple(activities[key] for key in evidence[planned.id].source_activity_ids))
                    for planned,workout in batch.planned_rows)
        return CalendarExecution(athlete_id=athlete_id, as_of_date=today, timezone=timezone_name,
            start_date=start_date, end_date=end_date, sessions=views)
