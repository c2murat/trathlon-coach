from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.models import ActivityLap, CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession, StructuredWorkout
from app.domains.capability.analysis import LapEvidence
from app.domains.planning.execution_evidence import (
    EXECUTION_WINDOW_DAYS, LinkedActivityEvidence, PlannedSessionEvidence,
    PrescribedCompletedEvidenceContext, build_session_execution_evidence, build_summary,
)


class PrescribedCompletedEvidenceAssembler:
    """Assemble linked prescribed-vs-completed facts without changing planning."""

    def __init__(self, session):
        self.session = session

    def assemble(self, *, athlete_profile_id, as_of_date: date) -> PrescribedCompletedEvidenceContext:
        window_start = as_of_date - timedelta(days=EXECUTION_WINDOW_DAYS)
        planned_rows = tuple(self.session.execute(
            select(PlannedTrainingSession, StructuredWorkout)
            .outerjoin(StructuredWorkout, StructuredWorkout.planned_training_session_id == PlannedTrainingSession.id)
            .where(
                PlannedTrainingSession.athlete_profile_id == athlete_profile_id,
                PlannedTrainingSession.scheduled_date >= window_start,
                PlannedTrainingSession.scheduled_date < as_of_date,
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
        evidence = tuple(build_session_execution_evidence(PlannedSessionEvidence(
            session_id=row.id, planned_date=row.scheduled_date, sport=row.sport,
            session_type=row.title, planned_duration_seconds=row.planned_duration_seconds,
            planned_distance_m=Decimal(row.planned_distance_meters) if row.planned_distance_meters is not None else None,
            workout=workout.parsed_definition() if workout else None,
            linked_activities=tuple(by_session.get(row.id, ())),
        )) for row, workout in planned_rows)
        return PrescribedCompletedEvidenceContext(
            athlete_profile_id=athlete_profile_id, as_of_date=as_of_date,
            window_start_date=window_start, sessions=evidence, summary=build_summary(evidence),
        )
