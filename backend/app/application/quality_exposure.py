from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.models import ActivityLap, ActivityTrainingLoad, CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession
from app.domains.capability.analysis import LapEvidence
from app.domains.planning.contracts import PerformanceSnapshot
from app.domains.planning.quality_exposure import (
    QualityExposureEvidence, SESSION_STIMULUS, build_quality_exposure_snapshot,
    classify_structured_activity, classify_unlinked,
)


class QualityExposureAssembler:
    """Build one compact, provider-neutral 12-week exposure snapshot."""

    def __init__(self, session, *, training_load_algorithm_version="0.7b.1"):
        self.session = session; self.load_version = training_load_algorithm_version

    def assemble(self, *, athlete_profile_id, as_of_date: date, timezone_name: str, performance: PerformanceSnapshot | None = None):
        zone = ZoneInfo(timezone_name); start = as_of_date - timedelta(days=83)
        start_utc = datetime.combine(start, time.min, zone).astimezone(timezone.utc)
        end_utc = datetime.combine(as_of_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        activities = tuple(self.session.scalars(select(CompletedActivity).where(
            CompletedActivity.athlete_id == athlete_profile_id,
            CompletedActivity.start_at >= start_utc, CompletedActivity.start_at < end_utc,
            CompletedActivity.deleted_at.is_(None), CompletedActivity.provider_deleted_at.is_(None),
            CompletedActivity.sport.in_(("running", "cycling", "swimming")),
        ).order_by(CompletedActivity.start_at, CompletedActivity.id)).all())
        ids = tuple(item.id for item in activities)
        links = () if not ids else tuple(self.session.execute(
            select(PlannedSessionActivityLink.completed_activity_id, PlannedTrainingSession.title)
            .join(PlannedTrainingSession, PlannedTrainingSession.id == PlannedSessionActivityLink.planned_training_session_id)
            .where(PlannedSessionActivityLink.athlete_profile_id == athlete_profile_id,
                   PlannedSessionActivityLink.completed_activity_id.in_(ids))
        ).all())
        linked = {activity_id: title for activity_id, title in links}
        lap_rows = () if not ids else tuple(self.session.scalars(
            select(ActivityLap).where(ActivityLap.completed_activity_id.in_(ids))
            .order_by(ActivityLap.completed_activity_id, ActivityLap.lap_index)
        ).all())
        by_id = {item.id: item for item in activities}
        laps = {}
        for row in lap_rows:
            activity = by_id[row.completed_activity_id]
            laps.setdefault(row.completed_activity_id, []).append(LapEvidence(
                activity_id=row.completed_activity_id, sport=activity.sport,
                local_date=activity.start_at.astimezone(zone).date(), lap_index=row.lap_index,
                duration_seconds=row.moving_time_seconds or row.elapsed_time_seconds or 0,
                distance_m=Decimal(str(row.distance_metres)) if row.distance_metres is not None else None,
                average_speed_mps=Decimal(str(row.average_speed_metres_per_second)) if row.average_speed_metres_per_second is not None else None,
                average_power_w=Decimal(str(row.average_watts)) if row.average_watts is not None else None,
                elapsed_seconds=row.elapsed_time_seconds, moving_seconds=row.moving_time_seconds,
            ))
        loads = {} if not ids else {item.completed_activity_id: item for item in self.session.scalars(
            select(ActivityTrainingLoad).where(
                ActivityTrainingLoad.completed_activity_id.in_(ids),
                ActivityTrainingLoad.algorithm_version == self.load_version,
            ).order_by(ActivityTrainingLoad.completed_activity_id)
        ).all()}
        evidence = []
        for activity in activities:
            mapping = SESSION_STIMULUS.get(linked.get(activity.id, ""))
            confidence = "HIGH"
            if mapping is None:
                structured = classify_structured_activity(
                    discipline=activity.sport, laps=tuple(laps.get(activity.id, ())),
                    performance=performance or PerformanceSnapshot(),
                )
                if structured is not None:
                    mapping = (activity.sport, structured.stimulus)
                    confidence = "MEDIUM"
            if mapping is None:
                stimulus = classify_unlinked(
                    discipline=activity.sport,
                    effective_intensity=getattr(loads.get(activity.id), "effective_intensity", None),
                )
                if stimulus is None: continue
                mapping = (activity.sport, stimulus); confidence = "MEDIUM"
            evidence.append(QualityExposureEvidence(
                activity_id=activity.id, local_date=activity.start_at.astimezone(zone).date(),
                discipline=mapping[0], stimulus=mapping[1], confidence=confidence,
            ))
        return build_quality_exposure_snapshot(cutoff_date=as_of_date, evidence=evidence)
