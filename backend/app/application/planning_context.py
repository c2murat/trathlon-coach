from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.db.models import (
    ActivityTrainingLoad,
    AthleteDailyTrainingLoad,
    AthleteDailyTrainingStatus,
    AthletePerformanceProfileVersion,
    AthletePerformanceReference,
    AthleteProfile,
    CompetitionGoal,
    CompletedActivity,
    ManualStrengthSession,
    ManualStrengthTrainingLoad,
)
from app.domains.planning.contracts import (
    WINDOW_DAYS,
    AthleteTrainingSnapshot,
    ContextVersions,
    PerformanceReferenceSnapshot,
    PerformanceSnapshot,
    PlanningContext,
    PlanningGoal,
    PlanningGoalSegment,
    PlanningRequest,
    PlanningWarning,
    SportTrainingSnapshot,
    TrainingStatusSnapshot,
    TrainingWindowSnapshot,
    context_fingerprint,
)
from app.application.planning_preferences import PlanningPreferencesApplication, preferences_from_row
from app.application.athlete_capability import AthleteCapabilityContextAssembler


class PlanningContextError(ValueError):
    pass


class PlanningAthleteNotFoundError(PlanningContextError):
    pass


class PlanningGoalNotFoundError(PlanningContextError):
    pass


class PlanningGoalAthleteMismatchError(PlanningContextError):
    pass


class PlanningGoalInvalidError(PlanningContextError):
    pass


class PlanningPreferencesUnavailableError(PlanningContextError):
    pass


class _ObservedSession:
    __slots__ = ("id", "local_date", "sport", "duration", "distance", "load")

    def __init__(self, identifier, local_date, sport, duration, distance, load):
        self.id = identifier
        self.local_date = local_date
        self.sport = sport
        self.duration = duration
        self.distance = distance
        self.load = load


class PlanningContextAssembler:
    """Build an immutable planning input. It never generates or persists a plan."""

    def __init__(
        self,
        session,
        *,
        training_load_algorithm_version: str,
        load_aggregation_algorithm_version: str,
        manual_strength_algorithm_version: str,
        training_status_algorithm_version: str,
    ):
        self.session = session
        self.load_version = training_load_algorithm_version
        self.aggregation_version = load_aggregation_algorithm_version
        self.strength_version = manual_strength_algorithm_version
        self.status_version = training_status_algorithm_version

    def assemble(self, request: PlanningRequest) -> PlanningContext:
        if request.mode.value != "INITIAL_PLAN":
            raise PlanningContextError("REPLAN_FROM_DATE is not executable in 0.8F.2")
        athlete = self.session.get(AthleteProfile, request.athlete_id)
        if athlete is None or athlete.deleted_at is not None:
            raise PlanningAthleteNotFoundError("athlete not found")
        if athlete.timezone != request.timezone_name:
            raise PlanningContextError("request timezone does not match athlete timezone")

        zone = ZoneInfo(request.timezone_name)
        cutoff_date = request.planning_date - timedelta(days=1)
        observation_start = cutoff_date - timedelta(days=89)
        start_utc = datetime.combine(observation_start, time.min, zone).astimezone(timezone.utc)
        cutoff_exclusive_utc = datetime.combine(request.planning_date, time.min, zone).astimezone(timezone.utc)
        performance_exclusive_utc = datetime.combine(
            request.planning_date + timedelta(days=1), time.min, zone
        ).astimezone(timezone.utc)

        goals = self._goals(request)
        preference_row = None
        if request.preferences is None:
            preference_row = PlanningPreferencesApplication(self.session).latest(request.athlete_id)
            if preference_row is None:
                raise PlanningPreferencesUnavailableError("planning preferences are required")
            preferences = preferences_from_row(preference_row)
        else:
            preferences = request.preferences
        performance = self._performance(request.athlete_id, performance_exclusive_utc)
        sessions = self._sessions(
            request.athlete_id, zone, start_utc, cutoff_exclusive_utc
        )
        daily_loads = self._daily_loads(
            request.athlete_id, observation_start, cutoff_date, request.timezone_name
        )
        status = self._status(request.athlete_id, cutoff_date, request.timezone_name)
        training = self._training_snapshot(
            request, observation_start, cutoff_date, sessions, daily_loads, status is not None
        )
        warnings = self._warnings(performance, sessions, daily_loads, status)
        versions = ContextVersions(
            planning_algorithm_version=request.algorithm_version,
            configuration_version=request.configuration_version,
            training_load_algorithm_version=self.load_version,
            load_aggregation_algorithm_version=self.aggregation_version,
            manual_strength_algorithm_version=self.strength_version,
            training_status_algorithm_version=self.status_version,
            performance_profile_version_id=performance.profile_version_id,
            planning_preferences_version_id=preference_row.id if preference_row else None,
            planning_preferences_version_number=preference_row.version_number if preference_row else None,
        )
        payload = {
            "request": request,
            "preferences": preferences,
            "goals": goals,
            "performance": performance,
            "training": training,
            "training_status": status,
            "versions": versions,
            "warnings": warnings,
        }
        return PlanningContext(**payload, fingerprint=context_fingerprint(payload))

    def assemble_capability(self, request: PlanningRequest):
        """Read-only 0.8G.2A integration; intentionally excluded from planning and its fingerprint."""
        performance_exclusive = datetime.combine(request.planning_date + timedelta(days=1), time.min, ZoneInfo(request.timezone_name)).astimezone(timezone.utc)
        performance = self._performance(request.athlete_id, performance_exclusive)
        sports = {"run": "running", "bike": "cycling", "swim": "swimming"}
        relevant = tuple(sports[item.sport] for goal in self._goals(request) if goal.event_date >= request.planning_date for item in goal.segments)
        return AthleteCapabilityContextAssembler(
            self.session, training_load_algorithm_version=self.load_version,
            training_status_algorithm_version=self.status_version,
        ).assemble(athlete_profile_id=request.athlete_id, as_of_date=request.planning_date, timezone_name=request.timezone_name, performance=performance, relevant_future_sports=relevant)

    def _goals(self, request: PlanningRequest) -> tuple[PlanningGoal, ...]:
        rows = tuple(
            self.session.scalars(
                select(CompetitionGoal)
                .where(CompetitionGoal.id.in_(request.goal_ids))
                .options(selectinload(CompetitionGoal.segments))
                .order_by(CompetitionGoal.event_date, CompetitionGoal.priority, CompetitionGoal.id)
            ).all()
        )
        by_id = {row.id: row for row in rows}
        missing = [identifier for identifier in request.goal_ids if identifier not in by_id]
        if missing:
            # A separately existing goal proves an athlete mismatch; otherwise it is absent.
            foreign = self.session.scalar(
                select(CompetitionGoal.id).where(
                    CompetitionGoal.id.in_(missing),
                    CompetitionGoal.athlete_profile_id != request.athlete_id,
                ).limit(1)
            )
            if foreign is not None:
                raise PlanningGoalAthleteMismatchError("goal belongs to another athlete")
            raise PlanningGoalNotFoundError("goal not found")
        if any(row.athlete_profile_id != request.athlete_id for row in rows):
            raise PlanningGoalAthleteMismatchError("goal belongs to another athlete")
        if any(row.status != "active" for row in rows):
            raise PlanningGoalInvalidError("only active goals can enter an initial context")
        if any(row.event_date < request.start_date for row in rows):
            raise PlanningGoalInvalidError("goal date must be on or after plan start date")

        canonical = sorted(rows, key=lambda row: (row.event_date, row.priority, str(row.id)))
        return tuple(
            PlanningGoal(
                competition_goal_id=row.id,
                event_date=row.event_date,
                start_time=row.event_start_time,
                timezone_name=row.timezone,
                category=row.event_category,
                event_format=row.event_format,
                priority=row.priority,
                role=None,
                segments=tuple(
                    PlanningGoalSegment(
                        position=segment.position,
                        sport=segment.sport,
                        distance_m=segment.distance_m,
                        elevation_gain_m=segment.elevation_gain_m,
                        label=segment.label,
                    )
                    for segment in sorted(row.segments, key=lambda item: (item.position, str(item.id)))
                ),
                target_finish_time_seconds=row.target_finish_time_seconds,
                city=row.city,
                region=row.region,
                country=row.country,
                status=row.status,
            )
            for row in canonical
        )

    def _performance(self, athlete_id: UUID, effective_before: datetime) -> PerformanceSnapshot:
        profile = self.session.scalar(
            select(AthletePerformanceProfileVersion)
            .where(
                AthletePerformanceProfileVersion.athlete_profile_id == athlete_id,
                AthletePerformanceProfileVersion.effective_from < effective_before,
            )
            .order_by(
                AthletePerformanceProfileVersion.effective_from.desc(),
                AthletePerformanceProfileVersion.id.desc(),
            )
            .limit(1)
        )
        reference_rows = tuple(
            self.session.scalars(
                select(AthletePerformanceReference)
                .where(
                    AthletePerformanceReference.athlete_profile_id == athlete_id,
                    AthletePerformanceReference.effective_from < effective_before,
                )
                .order_by(
                    AthletePerformanceReference.sport,
                    AthletePerformanceReference.metric_type,
                    AthletePerformanceReference.effective_from.desc(),
                    AthletePerformanceReference.id.desc(),
                )
            ).all()
        )
        current = {}
        quality = {"confirmed": 4, "high": 3, "medium": 2, "low": 1}
        origin = {"measured": 5, "manual": 4, "imported": 3, "derived": 2, "estimated": 1}
        for row in reference_rows:
            key = (row.sport, row.metric_type)
            rank = (
                quality.get(row.quality_level, 0),
                origin.get(row.data_origin, 0),
                row.measured_at or datetime.min.replace(tzinfo=timezone.utc),
                row.effective_from,
                row.created_at,
                str(row.id),
            )
            previous = current.get(key)
            if previous is None or rank > previous[0]:
                current[key] = (rank, row)
        references = tuple(
            PerformanceReferenceSnapshot(
                reference_id=row.id,
                sport=row.sport,
                metric_type=row.metric_type,
                value=row.value,
                unit=row.unit,
                source=row.data_origin,
                quality=row.quality_level,
                effective_from=row.effective_from,
                algorithm_version=row.algorithm_version,
            )
            for _, row in sorted(current.values(), key=lambda item: (item[1].sport, item[1].metric_type, str(item[1].id)))
        )
        if profile is None:
            return PerformanceSnapshot(references=references)
        return PerformanceSnapshot(
            profile_version_id=profile.id,
            effective_from=profile.effective_from,
            source=profile.data_origin,
            algorithm_version=profile.algorithm_version,
            resting_heart_rate_bpm=profile.resting_heart_rate_bpm,
            maximum_heart_rate_bpm=profile.maximum_heart_rate_bpm,
            body_weight_kg=profile.weight_kg,
            cycling_ftp_watts=profile.cycling_ftp_watts,
            cycling_threshold_heart_rate_bpm=profile.cycling_threshold_heart_rate_bpm,
            running_threshold_heart_rate_bpm=profile.running_threshold_heart_rate_bpm,
            running_threshold_pace_seconds_per_km=profile.running_threshold_pace_seconds_per_km,
            swimming_css_seconds_per_100m=profile.swimming_css_seconds_per_100m,
            preferred_pool_length_metres=profile.preferred_pool_length_metres,
            references=references,
        )

    def _sessions(self, athlete_id, zone, start_utc, end_utc) -> tuple[_ObservedSession, ...]:
        activity_rows = self.session.execute(
            select(CompletedActivity, ActivityTrainingLoad)
            .outerjoin(
                ActivityTrainingLoad,
                and_(
                    ActivityTrainingLoad.completed_activity_id == CompletedActivity.id,
                    ActivityTrainingLoad.algorithm_version == self.load_version,
                ),
            )
            .where(
                CompletedActivity.athlete_id == athlete_id,
                CompletedActivity.start_at >= start_utc,
                CompletedActivity.start_at < end_utc,
                CompletedActivity.deleted_at.is_(None),
                CompletedActivity.provider_deleted_at.is_(None),
            )
            .order_by(CompletedActivity.start_at, CompletedActivity.id)
        ).all()
        out = [
            _ObservedSession(
                activity.id,
                activity.start_at.astimezone(zone).date(),
                activity.sport,
                activity.moving_time_s if activity.moving_time_s is not None else activity.elapsed_time_s,
                Decimal(str(activity.distance_m)) if activity.distance_m is not None else None,
                Decimal(str(load.load_value)) if load is not None and load.load_value is not None else None,
            )
            for activity, load in activity_rows
            if activity.sport in {"running", "cycling", "swimming", "strength"}
        ]
        strength_rows = self.session.execute(
            select(ManualStrengthSession, ManualStrengthTrainingLoad)
            .outerjoin(
                ManualStrengthTrainingLoad,
                and_(
                    ManualStrengthTrainingLoad.session_id == ManualStrengthSession.id,
                    ManualStrengthTrainingLoad.algorithm_version == self.strength_version,
                ),
            )
            .where(
                ManualStrengthSession.athlete_id == athlete_id,
                ManualStrengthSession.started_at >= start_utc,
                ManualStrengthSession.started_at < end_utc,
            )
            .order_by(ManualStrengthSession.started_at, ManualStrengthSession.id)
        ).all()
        out.extend(
            _ObservedSession(
                strength.id,
                strength.started_at.astimezone(zone).date(),
                "strength",
                strength.duration_minutes * 60,
                None,
                Decimal(str(load.load_value)) if load is not None else None,
            )
            for strength, load in strength_rows
        )
        return tuple(sorted(out, key=lambda item: (item.local_date, str(item.id))))

    def _daily_loads(self, athlete_id, start_date, end_date, timezone_name):
        return tuple(
            self.session.scalars(
                select(AthleteDailyTrainingLoad)
                .where(
                    AthleteDailyTrainingLoad.athlete_profile_id == athlete_id,
                    AthleteDailyTrainingLoad.local_date.between(start_date, end_date),
                    AthleteDailyTrainingLoad.timezone_name == timezone_name,
                    AthleteDailyTrainingLoad.source_load_algorithm_version == self.load_version,
                    AthleteDailyTrainingLoad.manual_strength_algorithm_version == self.strength_version,
                    AthleteDailyTrainingLoad.aggregation_algorithm_version == self.aggregation_version,
                )
                .order_by(AthleteDailyTrainingLoad.local_date, AthleteDailyTrainingLoad.id)
            ).all()
        )

    def _status(self, athlete_id, cutoff_date, timezone_name):
        row = self.session.scalar(
            select(AthleteDailyTrainingStatus)
            .where(
                AthleteDailyTrainingStatus.athlete_profile_id == athlete_id,
                AthleteDailyTrainingStatus.local_date <= cutoff_date,
                AthleteDailyTrainingStatus.timezone_name == timezone_name,
                AthleteDailyTrainingStatus.training_load_algorithm_version == self.load_version,
                AthleteDailyTrainingStatus.manual_strength_algorithm_version == self.strength_version,
                AthleteDailyTrainingStatus.training_status_algorithm_version == self.status_version,
            )
            .order_by(AthleteDailyTrainingStatus.local_date.desc(), AthleteDailyTrainingStatus.id.desc())
            .limit(1)
        )
        if row is None:
            return None
        return TrainingStatusSnapshot(
            local_date=row.local_date,
            total_load=row.total_load,
            fitness=row.fitness,
            fatigue=row.fatigue,
            form=row.form,
            history_days=row.history_day_number,
            is_warmup=row.is_warmup,
            training_load_algorithm_version=row.training_load_algorithm_version,
            manual_strength_algorithm_version=row.manual_strength_algorithm_version,
            training_status_algorithm_version=row.training_status_algorithm_version,
        )

    def _training_snapshot(self, request, observation_start, cutoff_date, sessions, daily_loads, status_available):
        windows = tuple(
            self._window(days, cutoff_date, sessions, daily_loads) for days in WINDOW_DAYS
        )
        return AthleteTrainingSnapshot(
            planning_date=request.planning_date,
            timezone_name=request.timezone_name,
            observation_start=observation_start,
            observation_end=cutoff_date,
            observed_days=90,
            activities_available=bool(sessions),
            status_available=status_available,
            windows=windows,
        )

    def _window(self, days, cutoff_date, sessions, daily_loads):
        start = cutoff_date - timedelta(days=days - 1)
        selected = tuple(item for item in sessions if start <= item.local_date <= cutoff_date)
        loads = tuple(item for item in daily_loads if start <= item.local_date <= cutoff_date)
        sports = tuple(self._sport(sport, selected) for sport in ("running", "cycling", "swimming", "strength"))
        coverage_order = {"unavailable": 0, "partial": 1, "complete": 2}
        quality_order = {"unavailable": 0, "low": 1, "medium": 2, "high": 3}
        coverage = min((row.coverage for row in loads), key=lambda value: coverage_order.get(value, -1), default=None)
        quality = min((row.quality for row in loads), key=lambda value: quality_order.get(value, -1), default=None)
        return TrainingWindowSnapshot(
            days=days,
            start_date=start,
            end_date=cutoff_date,
            activity_count=len(selected),
            training_days=len({item.local_date for item in selected}),
            total_duration_seconds=sum(item.duration for item in selected),
            total_training_load=sum((row.total_load for row in loads), Decimal(0)) if loads else None,
            endurance_load=sum((row.endurance_load for row in loads), Decimal(0)) if loads else None,
            strength_load=sum((row.strength_load for row in loads), Decimal(0)) if loads else None,
            load_coverage=coverage,
            load_quality=quality,
            load_days_available=len(loads),
            sports=sports,
        )

    @staticmethod
    def _sport(sport, sessions):
        selected = tuple(item for item in sessions if item.sport == sport)
        distances = tuple(item.distance for item in selected if item.distance is not None)
        loads = tuple(item.load for item in selected if item.load is not None)
        return SportTrainingSnapshot(
            sport=sport,
            activity_count=len(selected),
            training_days=len({item.local_date for item in selected}),
            duration_seconds=sum(item.duration for item in selected),
            distance_m=None if sport == "strength" else sum(distances, Decimal(0)),
            training_load=sum(loads, Decimal(0)) if loads else None,
            loaded_activity_count=len(loads),
            missing_load_activity_count=len(selected) - len(loads),
            longest_duration_seconds=max((item.duration for item in selected), default=None),
            longest_distance_m=None if sport == "strength" else max(distances, default=None),
        )

    @staticmethod
    def _warnings(performance, sessions, daily_loads, status):
        warnings = []
        if performance.profile_version_id is None and not performance.references:
            warnings.append(PlanningWarning(code="MISSING_PERFORMANCE_PROFILE"))
        if not sessions:
            warnings.append(PlanningWarning(code="NO_TRAINING_HISTORY"))
        session_dates = {item.local_date for item in sessions}
        aggregate_dates = {item.local_date for item in daily_loads}
        if sessions and (
            not session_dates.issubset(aggregate_dates)
            or any(item.load is None for item in sessions)
            or any(item.coverage != "complete" for item in daily_loads)
        ):
            warnings.append(PlanningWarning(code="TRAINING_LOAD_INCOMPLETE"))
        if status is None:
            warnings.append(PlanningWarning(code="TRAINING_STATUS_UNAVAILABLE"))
        return tuple(sorted(warnings, key=lambda warning: warning.code))
