from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.db.models import ActivityLap, CompletedActivity, ManualStrengthSession, PlannedSessionActivityLink, PlannedSessionManualStrengthLink, PlannedTrainingSession, StructuredWorkout
from app.domains.capability.analysis import LapEvidence
from app.domains.planning.execution_evidence import (
    EXECUTION_WINDOW_DAYS, LinkedActivityEvidence, PlannedSessionEvidence,
    PrescribedCompletedEvidenceContext, build_session_execution_evidence, build_summary,
    ManualStrengthSourceEvidence, SessionExecutionEvidence,
)


@dataclass(frozen=True)
class ExecutionEvidenceBatch:
    sessions: tuple[SessionExecutionEvidence, ...]
    planned_rows: tuple
    activities: tuple[CompletedActivity, ...]
    manual_strength_sessions: tuple[ManualStrengthSession, ...] = ()


class PrescribedCompletedEvidenceAssembler:
    """Assemble linked prescribed-vs-completed facts without changing planning."""

    def __init__(self, session):
        self.session = session

    def assemble(self, *, athlete_profile_id, as_of_date: date) -> PrescribedCompletedEvidenceContext:
        window_start = as_of_date - timedelta(days=EXECUTION_WINDOW_DAYS)
        batch = self.assemble_range(athlete_profile_id=athlete_profile_id,
            start_date=window_start, end_date_exclusive=as_of_date)
        return PrescribedCompletedEvidenceContext(
            athlete_profile_id=athlete_profile_id, as_of_date=as_of_date,
            window_start_date=window_start, sessions=batch.sessions,
            manual_strength_sources=tuple(ManualStrengthSourceEvidence(
                id=row.id, started_at=row.started_at, timezone=row.timezone_name,
                duration_seconds=row.duration_minutes * 60,
            ) for row in batch.manual_strength_sessions),
            summary=build_summary(batch.sessions),
        )

    def assemble_range(self, *, athlete_profile_id, start_date: date, end_date_exclusive: date) -> ExecutionEvidenceBatch:
        """Reuse C.1 facts for a read-only presentation range, not an adaptation window."""
        planned_rows = tuple(self.session.execute(
            select(PlannedTrainingSession, StructuredWorkout)
            .outerjoin(StructuredWorkout, StructuredWorkout.planned_training_session_id == PlannedTrainingSession.id)
            .where(
                PlannedTrainingSession.athlete_profile_id == athlete_profile_id,
                PlannedTrainingSession.scheduled_date >= start_date,
                PlannedTrainingSession.scheduled_date < end_date_exclusive,
            ).order_by(PlannedTrainingSession.scheduled_date, PlannedTrainingSession.id)
        ).all())
        planned_ids = tuple(row.id for row, _ in planned_rows)
        linked_rows = () if not planned_ids else tuple(self.session.execute(
            select(PlannedSessionActivityLink, CompletedActivity)
            .join(CompletedActivity, CompletedActivity.id == PlannedSessionActivityLink.completed_activity_id)
            .where(
                PlannedSessionActivityLink.athlete_profile_id == athlete_profile_id,
                PlannedSessionActivityLink.planned_training_session_id.in_(planned_ids),
                CompletedActivity.athlete_id == athlete_profile_id,
                CompletedActivity.deleted_at.is_(None), CompletedActivity.provider_deleted_at.is_(None),
            ).order_by(PlannedSessionActivityLink.planned_training_session_id, CompletedActivity.id)
        ).all())
        activity_ids = tuple({activity.id for _, activity in linked_rows})
        lap_rows = () if not activity_ids else tuple(self.session.scalars(
            select(ActivityLap).where(ActivityLap.completed_activity_id.in_(activity_ids))
            .order_by(ActivityLap.completed_activity_id, ActivityLap.lap_index, ActivityLap.id)
        ).all())
        laps = {}
        activities = {activity.id: activity for _, activity in linked_rows}
        for row in lap_rows:
            activity = activities[row.completed_activity_id]
            duration = row.moving_time_seconds or row.elapsed_time_seconds or 0
            laps.setdefault(row.completed_activity_id, []).append(LapEvidence(
                activity_id=row.completed_activity_id, sport=activity.sport,
                local_date=activity.start_at.date(), lap_index=row.lap_index,
                duration_seconds=duration,
                distance_m=Decimal(str(row.distance_metres)) if row.distance_metres is not None else None,
                average_speed_mps=Decimal(str(row.average_speed_metres_per_second)) if row.average_speed_metres_per_second is not None else None,
                average_power_w=Decimal(str(row.average_watts)) if row.average_watts is not None else None,
                elapsed_seconds=row.elapsed_time_seconds, moving_seconds=row.moving_time_seconds,
            ))
        by_session = {}
        for link, activity in linked_rows:
            by_session.setdefault(link.planned_training_session_id, []).append(LinkedActivityEvidence(
                activity_id=activity.id, sport=activity.sport,
                duration_seconds=activity.moving_time_s if activity.moving_time_s is not None else activity.elapsed_time_s,
                distance_m=Decimal(str(activity.distance_m)) if activity.distance_m is not None else None,
                match_source=link.match_source, match_confidence=link.match_confidence,
                matching_algorithm_version=link.algorithm_version,
                laps=tuple(laps.get(activity.id, ())),
            ))
        manual_rows = self._manual_strength_rows(
            athlete_profile_id=athlete_profile_id,
            start_date=start_date,
            end_date_exclusive=end_date_exclusive,
        )
        linked_manual_rows = () if not planned_ids else tuple(self.session.execute(
            select(PlannedSessionManualStrengthLink, ManualStrengthSession)
            .join(ManualStrengthSession, ManualStrengthSession.id == PlannedSessionManualStrengthLink.manual_strength_session_id)
            .where(
                PlannedSessionManualStrengthLink.athlete_profile_id == athlete_profile_id,
                PlannedSessionManualStrengthLink.planned_training_session_id.in_(planned_ids),
                ManualStrengthSession.athlete_id == athlete_profile_id,
            ).order_by(PlannedSessionManualStrengthLink.planned_training_session_id, ManualStrengthSession.started_at, ManualStrengthSession.id)
        ).all())
        manual_map = {row.id: row for row in manual_rows}
        for _, row in linked_manual_rows:
            manual_map[row.id] = row
        manual_rows = tuple(sorted(manual_map.values(), key=lambda row: (row.started_at, str(row.id))))
        completed_linked_session_ids = {link.planned_training_session_id for link, _ in linked_rows}
        manually_linked_strength_session_ids = {link.planned_training_session_id for link, _ in linked_manual_rows}
        strength_sessions_by_date = {}
        for planned, _ in planned_rows:
            if planned.sport == "strength" and planned.id not in completed_linked_session_ids and planned.id not in manually_linked_strength_session_ids:
                strength_sessions_by_date.setdefault(planned.scheduled_date, []).append(planned)
        manual_by_date = {}
        for row in manual_rows:
            manual_by_date.setdefault(_manual_strength_local_date(row), []).append(row)
        for local_date, sessions in strength_sessions_by_date.items():
            candidates = manual_by_date.get(local_date, [])
            if len(sessions) == 1 and len(candidates) == 1:
                manual = candidates[0]
                by_session.setdefault(sessions[0].id, []).append(LinkedActivityEvidence(
                    activity_id=manual.id, sport="strength",
                    duration_seconds=manual.duration_minutes * 60,
                    distance_m=None, match_source="automatic",
                    match_confidence="high",
                    matching_algorithm_version="manual-strength-direct",
                    laps=(),
                ))
        for link, manual in linked_manual_rows:
            by_session.setdefault(link.planned_training_session_id, []).append(LinkedActivityEvidence(
                activity_id=manual.id, sport="strength",
                duration_seconds=manual.duration_minutes * 60,
                distance_m=None, match_source=link.match_source,
                match_confidence=link.match_confidence,
                matching_algorithm_version=None,
                laps=(),
            ))
        evidence = tuple(build_session_execution_evidence(PlannedSessionEvidence(
            session_id=row.id, planned_date=row.scheduled_date, sport=row.sport,
            session_type=row.title, planned_duration_seconds=row.planned_duration_seconds,
            planned_distance_m=Decimal(row.planned_distance_meters) if row.planned_distance_meters is not None else None,
            workout=workout.parsed_definition() if workout else None,
            linked_activities=tuple(by_session.get(row.id, ())),
        )) for row, workout in planned_rows)
        return ExecutionEvidenceBatch(evidence, planned_rows, tuple(activities.values()), manual_rows)

    def _manual_strength_rows(self, *, athlete_profile_id, start_date: date, end_date_exclusive: date) -> tuple[ManualStrengthSession, ...]:
        left = datetime.combine(start_date - timedelta(days=1), time.min, timezone.utc)
        right = datetime.combine(end_date_exclusive + timedelta(days=1), time.min, timezone.utc)
        rows = self.session.scalars(select(ManualStrengthSession).where(
            ManualStrengthSession.athlete_id == athlete_profile_id,
            ManualStrengthSession.started_at >= left,
            ManualStrengthSession.started_at < right,
        ).order_by(ManualStrengthSession.started_at, ManualStrengthSession.id)).all()
        return tuple(row for row in rows if start_date <= _manual_strength_local_date(row) < end_date_exclusive)


def _manual_strength_local_date(row: ManualStrengthSession) -> date:
    try:
        zone = ZoneInfo(row.timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    value = row.started_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone).date()
