from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.models import (
    ActivityLap, ActivityStream, ActivityTrainingLoad, AthleteDailyTrainingStatus,
    AthletePerformanceProfileVersion, AthletePerformanceReference,
    CompletedActivity, ManualStrengthSession,
)
from app.domains.capability.analysis import BIKE_DURATIONS, RUN_DURATIONS, ActivityEvidence, LapEvidence, build_capability_context, capability_window
from app.domains.planning.contracts import PerformanceReferenceSnapshot, PerformanceSnapshot


class AthleteCapabilityContextAssembler:
    """Build capability evidence on demand; all queries are athlete and cutoff scoped."""

    def __init__(self, session, *, training_load_algorithm_version: str = "0.7b.1", training_status_algorithm_version: str = "0.7f.1"):
        self.session = session
        self.load_version = training_load_algorithm_version
        self.status_version = training_status_algorithm_version

    def assemble(self, *, athlete_profile_id: UUID, as_of_date: date, timezone_name: str, performance: PerformanceSnapshot | None = None, relevant_future_sports=()):
        zone = ZoneInfo(timezone_name)
        window_start, _ = capability_window(as_of_date)
        start_utc = datetime.combine(window_start, time.min, zone).astimezone(timezone.utc)
        end_utc = datetime.combine(as_of_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        rows = tuple(self.session.scalars(
            select(CompletedActivity).where(
                CompletedActivity.athlete_id == athlete_profile_id,
                CompletedActivity.start_at >= start_utc, CompletedActivity.start_at < end_utc,
                CompletedActivity.deleted_at.is_(None), CompletedActivity.provider_deleted_at.is_(None),
                CompletedActivity.sport.in_(("running", "cycling", "swimming", "strength")),
            ).order_by(CompletedActivity.start_at, CompletedActivity.id)
        ).all())
        ids = tuple(row.id for row in rows)
        loads = {} if not ids else {row.completed_activity_id: row for row in self.session.scalars(
            select(ActivityTrainingLoad).where(ActivityTrainingLoad.completed_activity_id.in_(ids), ActivityTrainingLoad.algorithm_version == self.load_version)
        ).all()}
        laps = () if not ids else tuple(self.session.scalars(
            select(ActivityLap).where(ActivityLap.completed_activity_id.in_(ids)).order_by(ActivityLap.completed_activity_id, ActivityLap.lap_index)
        ).all())
        streams = () if not ids else tuple(self.session.scalars(
            select(ActivityStream).where(
                ActivityStream.completed_activity_id.in_(ids),
                ActivityStream.stream_type.in_(("time", "distance", "watts")),
            ).order_by(ActivityStream.completed_activity_id, ActivityStream.stream_type)
        ).all())
        by_id = {row.id: row for row in rows}
        activities = tuple(ActivityEvidence(
            activity_id=row.id, sport=row.sport, local_date=row.start_at.astimezone(zone).date(),
            duration_seconds=row.moving_time_s if row.moving_time_s is not None else row.elapsed_time_s,
            distance_m=Decimal(str(row.distance_m)) if row.distance_m is not None else None,
            average_speed_mps=Decimal(str(row.average_speed_mps)) if row.average_speed_mps is not None else None,
            average_power_w=Decimal(str(row.average_power_w)) if row.average_power_w is not None else None,
            coverage=self._coverage(loads.get(row.id)),
        ) for row in rows)
        lap_evidence = tuple(LapEvidence(
            activity_id=row.completed_activity_id, sport=by_id[row.completed_activity_id].sport,
            local_date=by_id[row.completed_activity_id].start_at.astimezone(zone).date(), lap_index=row.lap_index,
            duration_seconds=row.moving_time_seconds or row.elapsed_time_seconds or 0,
            distance_m=Decimal(str(row.distance_metres)) if row.distance_metres is not None else None,
            average_speed_mps=Decimal(str(row.average_speed_metres_per_second)) if row.average_speed_metres_per_second is not None else None,
            average_power_w=Decimal(str(row.average_watts)) if row.average_watts is not None else None,
            coverage=self._coverage(loads.get(row.completed_activity_id)),
            elapsed_seconds=row.elapsed_time_seconds,
            moving_seconds=row.moving_time_seconds,
        ) for row in laps if (row.moving_time_seconds or row.elapsed_time_seconds or 0) > 0)
        lap_evidence += self._stream_efforts(rows, streams, zone, loads)
        manual = tuple(self.session.scalars(select(ManualStrengthSession).where(
            ManualStrengthSession.athlete_id == athlete_profile_id,
            ManualStrengthSession.started_at >= start_utc, ManualStrengthSession.started_at < end_utc,
        ).order_by(ManualStrengthSession.started_at, ManualStrengthSession.id)).all())
        activities += tuple(ActivityEvidence(
            activity_id=row.id, sport="strength", local_date=row.started_at.astimezone(zone).date(),
            duration_seconds=row.duration_minutes * 60, distance_m=None,
        ) for row in manual)
        status = self.session.scalar(select(AthleteDailyTrainingStatus).where(
            AthleteDailyTrainingStatus.athlete_profile_id == athlete_profile_id,
            AthleteDailyTrainingStatus.local_date <= as_of_date,
            AthleteDailyTrainingStatus.timezone_name == timezone_name,
            AthleteDailyTrainingStatus.training_status_algorithm_version == self.status_version,
        ).order_by(AthleteDailyTrainingStatus.local_date.desc(), AthleteDailyTrainingStatus.id.desc()).limit(1))
        performance = performance or self._performance(athlete_profile_id, end_utc)
        return build_capability_context(
            athlete_id=athlete_profile_id, as_of_date=as_of_date, activities=activities,
            laps=lap_evidence, performance=performance, training_status=status,
            relevant_future_sports=relevant_future_sports,
        )

    def _stream_efforts(self, activities, streams, zone, loads):
        """Extract one sustained best window per activity/target from aligned streams."""
        grouped = {}
        for stream in streams:
            grouped.setdefault(stream.completed_activity_id, {})[stream.stream_type] = stream
        out = []
        for activity in activities:
            source = grouped.get(activity.id, {})
            time_stream = source.get("time")
            metric_stream = source.get("watts" if activity.sport == "cycling" else "distance")
            targets = BIKE_DURATIONS if activity.sport == "cycling" else RUN_DURATIONS if activity.sport == "running" else ()
            if not time_stream or not metric_stream or not targets:
                continue
            try:
                times = [Decimal(str(value)) for value in time_stream.values]
                metrics = [Decimal(str(value)) for value in metric_stream.values]
            except (ValueError, TypeError, ArithmeticError):
                continue
            if len(times) != len(metrics) or len(times) < 2 or any(right <= left for left, right in zip(times, times[1:])):
                continue
            stream_coverage = Decimal("0.75") if time_stream.original_sample_count > time_stream.sample_count or metric_stream.original_sample_count > metric_stream.sample_count else Decimal("1")
            coverage = min(self._coverage(loads.get(activity.id)), stream_coverage)
            for target_index, target in enumerate(targets):
                best = None
                right = 1
                for left in range(len(times)-1):
                    right = max(right, left+1)
                    while right < len(times) and times[right]-times[left] < target:
                        right += 1
                    if right >= len(times) or times[right]-times[left] > Decimal(target)*Decimal("1.10"):
                        continue
                    if activity.sport == "cycling":
                        value = sum(metrics[left:right+1], Decimal(0))/Decimal(right-left+1)
                        candidate = (value, left, right)
                        if best is None or candidate[0] > best[0]: best = candidate
                    else:
                        distance = metrics[right]-metrics[left]
                        if distance < 20: continue
                        pace = Decimal(target)*Decimal(1000)/distance
                        candidate = (pace, left, right, distance)
                        if Decimal("120") <= pace <= Decimal("900") and (best is None or candidate[0] < best[0]): best = candidate
                if best is None: continue
                out.append(LapEvidence(
                    activity_id=activity.id, sport=activity.sport, local_date=activity.start_at.astimezone(zone).date(),
                    lap_index=10000+target_index, duration_seconds=target,
                    distance_m=best[3] if activity.sport == "running" else None,
                    average_speed_mps=None, average_power_w=best[0] if activity.sport == "cycling" else None,
                    coverage=coverage,
                    elapsed_seconds=target,
                    moving_seconds=target,
                ))
        return tuple(out)

    @staticmethod
    def _coverage(load) -> Decimal:
        if load is None or load.coverage == "unavailable" or load.quality == "low": return Decimal("0.50")
        if load.coverage == "partial" or load.quality == "medium": return Decimal("0.75")
        return Decimal("1.00")

    def _performance(self, athlete_id, effective_before):
        profile = self.session.scalar(select(AthletePerformanceProfileVersion).where(
            AthletePerformanceProfileVersion.athlete_profile_id == athlete_id,
            AthletePerformanceProfileVersion.effective_from < effective_before,
        ).order_by(AthletePerformanceProfileVersion.effective_from.desc(), AthletePerformanceProfileVersion.id.desc()).limit(1))
        rows = tuple(self.session.scalars(select(AthletePerformanceReference).where(
            AthletePerformanceReference.athlete_profile_id == athlete_id,
            AthletePerformanceReference.effective_from < effective_before,
        ).order_by(AthletePerformanceReference.sport, AthletePerformanceReference.metric_type, AthletePerformanceReference.effective_from.desc(), AthletePerformanceReference.id.desc())).all())
        seen = set(); references = []
        for row in rows:
            key = (row.sport, row.metric_type)
            if key in seen: continue
            seen.add(key); references.append(PerformanceReferenceSnapshot(reference_id=row.id, sport=row.sport, metric_type=row.metric_type, value=row.value, unit=row.unit, source=row.data_origin, quality=row.quality_level, effective_from=row.effective_from, algorithm_version=row.algorithm_version))
        values = {"references": tuple(references)}
        if profile is not None:
            values.update(profile_version_id=profile.id, effective_from=profile.effective_from, source=profile.data_origin, algorithm_version=profile.algorithm_version, resting_heart_rate_bpm=profile.resting_heart_rate_bpm, maximum_heart_rate_bpm=profile.maximum_heart_rate_bpm, body_weight_kg=profile.weight_kg, cycling_ftp_watts=profile.cycling_ftp_watts, cycling_threshold_heart_rate_bpm=profile.cycling_threshold_heart_rate_bpm, running_threshold_heart_rate_bpm=profile.running_threshold_heart_rate_bpm, running_threshold_pace_seconds_per_km=profile.running_threshold_pace_seconds_per_km, swimming_css_seconds_per_100m=profile.swimming_css_seconds_per_100m, preferred_pool_length_metres=profile.preferred_pool_length_metres)
        return PerformanceSnapshot(**values)
