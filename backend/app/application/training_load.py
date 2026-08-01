from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from sqlalchemy import select

from app.db.models import AthletePerformanceProfileVersion, CompletedActivity
from app.db.models.training_load import ActivityTrainingLoad
from app.domains.training_load import (
    Sport,
    TrainingLoadCoverage,
    TrainingLoadInput,
    TrainingLoadMethod,
    TrainingLoadQuality,
    TrainingLoadReason,
    TrainingLoadResult,
    TrainingLoadUnit,
    calculate,
)

ALGORITHM_VERSION = "0.7b.1"
MINIMUM_HEART_RATE_BPM = 20
MAXIMUM_HEART_RATE_BPM = 260


def _is_finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


def _unavailable_result(activity: CompletedActivity, warning: str, *, reason: TrainingLoadReason = TrainingLoadReason.INVALID_VALUE) -> TrainingLoadResult:
    sport = Sport(activity.sport) if activity.sport in {item.value for item in Sport} else Sport.OTHER
    return TrainingLoadResult(
        sport=sport,
        load=None,
        unit=TrainingLoadUnit.LOAD_POINTS,
        method=TrainingLoadMethod.DURATION_ONLY,
        coverage=TrainingLoadCoverage.UNAVAILABLE,
        quality=TrainingLoadQuality.NONE,
        reason=reason,
        algorithm_version=ALGORITHM_VERSION,
        duration_seconds=None,
        warnings=(warning,),
    )


class TrainingLoadApplication:
    def __init__(self, session):
        self.session = session

    def get_persisted(self, athlete_id, activity_id, algorithm_version=ALGORITHM_VERSION):
        activity = self.session.scalar(select(CompletedActivity).where(CompletedActivity.id == activity_id, CompletedActivity.athlete_id == athlete_id))
        if not activity:
            raise LookupError("Actividad no encontrada")
        return self.session.scalar(select(ActivityTrainingLoad).where(ActivityTrainingLoad.completed_activity_id == activity_id, ActivityTrainingLoad.algorithm_version == algorithm_version))

    def calculate_for_activity(self, athlete_id, activity_id, algorithm_version=ALGORITHM_VERSION):
        activity = self.session.scalar(select(CompletedActivity).where(CompletedActivity.id == activity_id, CompletedActivity.athlete_id == athlete_id))
        if not activity:
            raise LookupError("Actividad no encontrada")
        result = self._calculate(activity, athlete_id)
        row = self.session.scalar(select(ActivityTrainingLoad).where(ActivityTrainingLoad.completed_activity_id == activity.id, ActivityTrainingLoad.algorithm_version == algorithm_version))
        values = dict(
            load_value=result.load,
            method=result.method.value,
            unit=result.unit.value,
            coverage=result.coverage.value,
            quality=result.quality.value if result.quality else None,
            reason=result.reason.value,
            duration_seconds=result.duration_seconds,
            reference_value=result.reference_value,
            reference_metric=result.reference_unit,
            source_metrics={name: True for name in result.source_metrics},
            warnings=list(result.warnings),
            calculated_at=datetime.now(timezone.utc),
        )
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            self.session.add(ActivityTrainingLoad(completed_activity_id=activity.id, algorithm_version=algorithm_version, **values))
        self.session.flush()
        return result

    def _calculate(self, activity: CompletedActivity, athlete_id):
        moving_time = activity.moving_time_s
        if not _is_finite_number(moving_time) or moving_time <= 0:
            return _unavailable_result(activity, "moving_time_seconds ausente, no finito o no positivo.", reason=TrainingLoadReason.MISSING_DURATION)

        distance = activity.distance_m
        if not _is_finite_number(distance) or distance < 0:
            return _unavailable_result(activity, "distance_meters ausente, no finito o negativo.")

        heart_rate = activity.average_heart_rate_bpm
        input_warnings: list[str] = []
        if heart_rate is not None and (
            not _is_finite_number(heart_rate)
            or not MINIMUM_HEART_RATE_BPM <= heart_rate <= MAXIMUM_HEART_RATE_BPM
        ):
            heart_rate = None
            input_warnings.append("average_heart_rate_bpm no finita o fuera del rango aceptable; se omitió del cálculo.")

        profile = self.session.scalar(
            select(AthletePerformanceProfileVersion)
            .where(AthletePerformanceProfileVersion.athlete_profile_id == athlete_id, AthletePerformanceProfileVersion.effective_from <= activity.start_at)
            .order_by(AthletePerformanceProfileVersion.effective_from.desc())
            .limit(1)
        )
        try:
            training_input = TrainingLoadInput(
                sport=Sport(activity.sport) if activity.sport in {item.value for item in Sport} else Sport.OTHER,
                moving_time_seconds=moving_time,
                elapsed_time_seconds=activity.elapsed_time_s,
                distance_meters=distance,
                average_heart_rate_bpm=heart_rate,
                max_heart_rate_bpm=activity.max_heart_rate_bpm,
                average_power_watts=activity.average_power_w,
                normalized_power_watts=activity.weighted_average_power_w,
                average_speed_mps=activity.average_speed_mps,
                ftp_watts=float(profile.cycling_ftp_watts) if profile and profile.cycling_ftp_watts is not None else None,
                threshold_heart_rate_bpm=(profile.cycling_threshold_heart_rate_bpm if profile and activity.sport == "cycling" else profile.running_threshold_heart_rate_bpm if profile and activity.sport == "running" else None),
                reference_max_heart_rate_bpm=profile.maximum_heart_rate_bpm if profile else None,
                resting_heart_rate_bpm=profile.resting_heart_rate_bpm if profile else None,
                running_threshold_pace_seconds_per_km=float(profile.running_threshold_pace_seconds_per_km) if profile and profile.running_threshold_pace_seconds_per_km is not None else None,
                swim_css_seconds_per_100m=float(profile.swimming_css_seconds_per_100m) if profile and profile.swimming_css_seconds_per_100m is not None else None,
            )
        except (TypeError, ValueError) as error:
            return _unavailable_result(activity, f"Datos históricos inválidos para carga: {error}")

        result = calculate(training_input)
        if not input_warnings:
            return result
        return TrainingLoadResult(
            sport=result.sport,
            load=result.load,
            unit=result.unit,
            method=result.method,
            coverage=result.coverage,
            quality=result.quality,
            reason=result.reason,
            algorithm_version=result.algorithm_version,
            duration_seconds=result.duration_seconds,
            reference_value=result.reference_value,
            reference_unit=result.reference_unit,
            source_metrics=result.source_metrics,
            warnings=result.warnings + tuple(input_warnings),
        )
