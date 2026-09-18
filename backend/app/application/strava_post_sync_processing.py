from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.application.combined_training_load_aggregation import TrainingLoadAggregationApplication
from app.application.training_load import ALGORITHM_VERSION as LOAD_VERSION, TrainingLoadApplication
from app.application.training_status_sync import sync_training_status_after_load_change
from app.application.planned_session_activity_matching import PlannedSessionActivityMatching, DATE_WINDOW_DAYS, _local_date
from app.db.models import AthleteProfile, CompletedActivity, PlannedTrainingSession
from app.domains.manual_strength import ALGORITHM_VERSION as MANUAL_STRENGTH_VERSION


@dataclass(frozen=True, slots=True)
class PostSyncProcessingResult:
    processed_count: int
    affected_start_date: date | None
    affected_end_date: date | None


class StravaPostSyncProcessingError(RuntimeError):
    def __init__(self, stage: str) -> None:
        super().__init__(f"post_sync_{stage}_failed")
        self.stage = stage


class StravaPostSyncProcessingApplication:
    """Rebuild local athlete-derived data after a checkpointed Strava import."""

    def __init__(self, session) -> None:
        self.session = session

    def process(self, *, athlete_id: UUID, activity_ids: tuple[UUID, ...]) -> PostSyncProcessingResult:
        if not activity_ids:
            return PostSyncProcessingResult(0, None, None)
        athlete = self.session.get(AthleteProfile, athlete_id)
        if athlete is None or athlete.deleted_at is not None:
            raise LookupError("athlete_not_found")
        activities = tuple(
            self.session.scalars(
                select(CompletedActivity)
                .where(
                    CompletedActivity.athlete_id == athlete_id,
                    CompletedActivity.id.in_(activity_ids),
                )
                .order_by(CompletedActivity.start_at, CompletedActivity.id)
            ).all()
        )
        if len(activities) != len(set(activity_ids)):
            raise LookupError("activity_scope_mismatch")
        zone = ZoneInfo(athlete.timezone)
        local_dates = tuple(item.start_at.astimezone(zone).date() for item in activities)
        start_date, end_date = min(local_dates), max(local_dates)
        try:
            load = TrainingLoadApplication(self.session)
            for activity in activities:
                load.calculate_for_activity(athlete_id, activity.id, LOAD_VERSION)
        except Exception as error:
            raise StravaPostSyncProcessingError("training_load") from error
        try:
            aggregation = TrainingLoadAggregationApplication(self.session)
            aggregation.recalculate_daily(
                athlete_id,
                start_date=start_date,
                end_date=end_date,
                timezone_name=athlete.timezone,
                source_load_algorithm_version=LOAD_VERSION,
                manual_strength_algorithm_version=MANUAL_STRENGTH_VERSION,
            )
            aggregation.recalculate_weekly(
                athlete_id,
                start_date=start_date,
                end_date=end_date,
                timezone_name=athlete.timezone,
                source_load_algorithm_version=LOAD_VERSION,
                manual_strength_algorithm_version=MANUAL_STRENGTH_VERSION,
            )
        except Exception as error:
            raise StravaPostSyncProcessingError("aggregating") from error
        try:
            sync_training_status_after_load_change(
                self.session,
                athlete_id=athlete_id,
                affected_start_date=start_date,
                affected_end_date=end_date,
                timezone_name=athlete.timezone,
                training_load_algorithm_version=LOAD_VERSION,
                manual_strength_algorithm_version=MANUAL_STRENGTH_VERSION,
            )
        except Exception as error:
            raise StravaPostSyncProcessingError("training_status") from error
        try:
            # All imported pages exist before applying the unchanged matching policy.
            candidate_dates = {_local_date(activity)+timedelta(days=offset)
                for activity in activities for offset in range(-DATE_WINDOW_DAYS, DATE_WINDOW_DAYS+1)}
            planned_ids = self.session.scalars(select(PlannedTrainingSession.id).where(
                PlannedTrainingSession.athlete_profile_id == athlete_id,
                PlannedTrainingSession.scheduled_date.in_(candidate_dates),
            ).order_by(PlannedTrainingSession.scheduled_date, PlannedTrainingSession.id)).all()
            matching = PlannedSessionActivityMatching(self.session)
            for planned_id in planned_ids:
                matching.auto_match(athlete_id, planned_id)
        except Exception as error:
            raise StravaPostSyncProcessingError("activity_matching") from error
        self.session.flush()
        return PostSyncProcessingResult(len(activities), start_date, end_date)
