from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PLANNING_CONTEXT_SCHEMA_VERSION = 1
WINDOW_DAYS = (7, 28, 42, 90)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlanningMode(str, Enum):
    INITIAL_PLAN = "INITIAL_PLAN"
    REPLAN_FROM_DATE = "REPLAN_FROM_DATE"


class AvailabilitySlot(FrozenModel):
    weekday: int = Field(ge=0, le=6)
    available_minutes: int = Field(ge=0, le=1440)
    max_sessions: int = Field(ge=0, le=4)
    earliest_time: time | None = None
    latest_time: time | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.earliest_time and self.latest_time and self.earliest_time >= self.latest_time:
            raise ValueError("earliest_time must be before latest_time")
        if self.available_minutes == 0 and self.max_sessions != 0:
            raise ValueError("unavailable slots cannot allow sessions")
        return self


class PlanningPreferences(FrozenModel):
    availability_slots: tuple[AvailabilitySlot, ...] = ()
    max_sessions_per_day: int = Field(ge=0, le=4)
    max_sessions_per_week: int = Field(ge=0, le=28)
    preferred_rest_days: tuple[int, ...] = ()
    preferred_long_run_day: int | None = Field(default=None, ge=0, le=6)
    preferred_long_bike_day: int | None = Field(default=None, ge=0, le=6)
    strength_sessions_per_week: int = Field(ge=0, le=7)

    @model_validator(mode="after")
    def validate_days(self):
        weekdays = tuple(slot.weekday for slot in self.availability_slots)
        if len(set(weekdays)) != len(weekdays):
            raise ValueError("availability weekdays must be unique")
        if tuple(sorted(weekdays)) != weekdays:
            raise ValueError("availability slots must be ordered by weekday")
        if tuple(sorted(set(self.preferred_rest_days))) != self.preferred_rest_days:
            raise ValueError("preferred rest days must be unique and ordered")
        if any(day < 0 or day > 6 for day in self.preferred_rest_days):
            raise ValueError("preferred rest day is invalid")
        return self


class PlanningRequest(FrozenModel):
    athlete_id: UUID
    planning_date: date
    timezone_name: str = Field(min_length=1, max_length=64)
    goal_ids: tuple[UUID, ...] = Field(min_length=1)
    mode: PlanningMode = PlanningMode.INITIAL_PLAN
    start_date: date
    horizon_end_date: date | None = None
    preferences: PlanningPreferences | None = None
    algorithm_version: str = Field(min_length=1, max_length=64)
    configuration_version: str = Field(min_length=1, max_length=64)

    @field_validator("goal_ids", mode="before")
    @classmethod
    def canonical_goal_ids(cls, value):
        return tuple(sorted((UUID(str(item)) for item in value), key=str))

    @model_validator(mode="after")
    def validate_request(self):
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
            raise ValueError("timezone_name must be a valid IANA timezone") from error
        if len(set(self.goal_ids)) != len(self.goal_ids):
            raise ValueError("goal_ids must be unique")
        if self.horizon_end_date is not None and self.horizon_end_date < self.start_date:
            raise ValueError("horizon_end_date must be on or after start_date")
        return self


class PlanningGoalSegment(FrozenModel):
    position: int = Field(ge=1)
    sport: Literal["swim", "bike", "run"]
    distance_m: int = Field(gt=0)
    elevation_gain_m: int | None = Field(default=None, ge=0)
    label: str | None = None


class PlanningGoal(FrozenModel):
    competition_goal_id: UUID
    event_date: date
    start_time: time | None = None
    timezone_name: str
    category: str
    event_format: str
    priority: Literal["A", "B", "C"]
    role: Literal["primary", "supporting", "training"] | None = None
    segments: tuple[PlanningGoalSegment, ...]
    target_finish_time_seconds: int | None = Field(default=None, gt=0)
    city: str | None = None
    region: str | None = None
    country: str | None = None
    status: Literal["active", "completed", "cancelled"]


class PerformanceReferenceSnapshot(FrozenModel):
    reference_id: UUID
    sport: str
    metric_type: str
    value: Decimal
    unit: str
    source: str
    quality: str
    effective_from: datetime
    algorithm_version: str | None = None


class PerformanceSnapshot(FrozenModel):
    profile_version_id: UUID | None = None
    effective_from: datetime | None = None
    source: str | None = None
    algorithm_version: str | None = None
    resting_heart_rate_bpm: int | None = None
    maximum_heart_rate_bpm: int | None = None
    body_weight_kg: Decimal | None = None
    cycling_ftp_watts: Decimal | None = None
    cycling_threshold_heart_rate_bpm: int | None = None
    running_threshold_heart_rate_bpm: int | None = None
    running_threshold_pace_seconds_per_km: Decimal | None = None
    swimming_css_seconds_per_100m: Decimal | None = None
    preferred_pool_length_metres: int | None = None
    references: tuple[PerformanceReferenceSnapshot, ...] = ()


class SportTrainingSnapshot(FrozenModel):
    sport: Literal["running", "cycling", "swimming", "strength"]
    activity_count: int = Field(ge=0)
    training_days: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)
    distance_m: Decimal | None = Field(default=None, ge=0)
    training_load: Decimal | None = Field(default=None, ge=0)
    loaded_activity_count: int = Field(ge=0)
    missing_load_activity_count: int = Field(ge=0)
    longest_duration_seconds: int | None = Field(default=None, ge=0)
    longest_distance_m: Decimal | None = Field(default=None, ge=0)


class TrainingWindowSnapshot(FrozenModel):
    days: Literal[7, 28, 42, 90]
    start_date: date
    end_date: date
    activity_count: int = Field(ge=0)
    training_days: int = Field(ge=0)
    total_duration_seconds: int = Field(ge=0)
    total_training_load: Decimal | None = Field(default=None, ge=0)
    endurance_load: Decimal | None = Field(default=None, ge=0)
    strength_load: Decimal | None = Field(default=None, ge=0)
    load_coverage: str | None = None
    load_quality: str | None = None
    load_days_available: int = Field(ge=0)
    sports: tuple[SportTrainingSnapshot, ...]


class AthleteTrainingSnapshot(FrozenModel):
    planning_date: date
    timezone_name: str
    observation_start: date
    observation_end: date
    expected_days: int = 90
    observed_days: int = Field(ge=0, le=90)
    activities_available: bool
    status_available: bool
    windows: tuple[TrainingWindowSnapshot, ...]


class TrainingStatusSnapshot(FrozenModel):
    local_date: date
    total_load: Decimal = Field(ge=0)
    fitness: Decimal = Field(ge=0)
    fatigue: Decimal = Field(ge=0)
    form: Decimal
    history_days: int = Field(ge=1)
    is_warmup: bool
    training_load_algorithm_version: str
    manual_strength_algorithm_version: str
    training_status_algorithm_version: str


class PlanningWarning(FrozenModel):
    code: Literal[
        "MISSING_PERFORMANCE_PROFILE",
        "NO_TRAINING_HISTORY",
        "TRAINING_LOAD_INCOMPLETE",
        "TRAINING_STATUS_UNAVAILABLE",
        "MULTIPLE_PRIMARY_GOALS_CLOSE",
        "SHORT_PREPARATION_HORIZON",
        "GOAL_DURING_TAPER",
        "GOALS_OVERLAP",
        "LOW_WEEKLY_AVAILABILITY",
        "MULTISPORT_AVAILABILITY_CONSTRAINT",
        "NO_TRAINING_AVAILABILITY",
        "INSUFFICIENT_LOAD_HISTORY",
        "LOW_LOAD_COVERAGE",
        "WEEKLY_LOAD_BASELINE_UNAVAILABLE",
        "AVAILABILITY_CAP_UNKNOWN",
        "STRENGTH_LOAD_BASELINE_UNAVAILABLE",
        "SESSION_PLACEMENT_CONSTRAINT",
        "WEEKLY_SESSION_LIMIT_REACHED",
        "KEY_SESSION_SPACING_CONSTRAINT",
        "DISCIPLINE_UNDERREPRESENTED",
        "LONG_SESSION_HISTORY_INSUFFICIENT",
        "SESSION_LOAD_TARGET_UNAVAILABLE",
        "WEEKLY_LOAD_BUDGET_UNDERSHOT",
        "WEEKLY_LOAD_BUDGET_OVERSHOT",
        "PREFERRED_REST_DAY_UNAVAILABLE",
        "PREFERRED_LONG_DAY_UNAVAILABLE",
    ]
    severity: Literal["WARNING", "ERROR"] = "WARNING"
    blocking: bool = False
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class ContextVersions(FrozenModel):
    context_schema_version: int = PLANNING_CONTEXT_SCHEMA_VERSION
    planning_algorithm_version: str
    configuration_version: str
    training_load_algorithm_version: str
    load_aggregation_algorithm_version: str
    manual_strength_algorithm_version: str
    training_status_algorithm_version: str
    performance_profile_version_id: UUID | None = None
    planning_preferences_version_id: UUID | None = None
    planning_preferences_version_number: int | None = None


class AdaptiveCapabilityPointSnapshot(FrozenModel):
    dimension: int = Field(gt=0)
    usable_value: Decimal = Field(gt=0)
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
    days_since_evidence: int = Field(ge=0, le=83)
    support_count: int = Field(ge=1)
    source_activity_ids: tuple[UUID, ...] = Field(default=(), max_length=4)


class AdaptiveRepeatSnapshot(FrozenModel):
    repeat_count: int = Field(ge=3)
    typical_duration_seconds: int = Field(gt=0)
    typical_distance_m: int | None = Field(default=None, gt=0)
    representative_value: Decimal = Field(gt=0)
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"]
    days_since_evidence: int = Field(ge=0, le=83)
    source_activity_id: UUID | None = None


class AdaptiveCapabilitySnapshot(FrozenModel):
    algorithm_version: str
    cutoff_date: date
    running_duration: tuple[AdaptiveCapabilityPointSnapshot, ...] = ()
    cycling_duration: tuple[AdaptiveCapabilityPointSnapshot, ...] = ()
    swimming_distance: tuple[AdaptiveCapabilityPointSnapshot, ...] = ()
    running_repeats: tuple[AdaptiveRepeatSnapshot, ...] = ()
    swimming_repeats: tuple[AdaptiveRepeatSnapshot, ...] = ()


class QualityExposureSignal(FrozenModel):
    discipline: Literal["running", "cycling", "swimming"]
    stimulus: Literal["TEMPO", "SWEET_SPOT", "THRESHOLD", "INTERVAL", "TECHNIQUE", "AEROBIC"]
    weighted_exposure: Decimal = Field(ge=0)
    count_0_27d: int = Field(ge=0)
    count_28_55d: int = Field(ge=0)
    count_56_83d: int = Field(ge=0)
    days_since_last: int | None = Field(default=None, ge=0, le=83)
    confidence: Literal["HIGH", "MEDIUM"]


class QualityExposureSnapshot(FrozenModel):
    algorithm_version: str
    cutoff_date: date
    signals: tuple[QualityExposureSignal, ...] = ()


class PlanningAdaptationItem(FrozenModel):
    proposal_version: str
    numeric_policy_version: str | None = None
    cutoff_date: date
    sport: Literal["running", "cycling", "swimming"]
    session_type: str
    target_kind: Literal["RUN_PACE", "POWER", "SWIM_PACE"]
    proposal_kind: Literal["INCREASE_TARGET", "DECREASE_TARGET"]
    direction: Literal["FASTER_PACE", "SLOWER_PACE", "HIGHER_POWER", "LOWER_POWER"]
    confidence: Literal["HIGH", "MEDIUM"]
    current_minimum: Decimal = Field(gt=0)
    current_maximum: Decimal = Field(gt=0)
    proposed_minimum: Decimal = Field(gt=0)
    proposed_maximum: Decimal = Field(gt=0)
    unit: Literal["watts", "seconds_per_km", "seconds_per_100m"]

    @model_validator(mode="after")
    def validate_adaptation(self):
        if self.current_minimum > self.current_maximum or self.proposed_minimum > self.proposed_maximum:
            raise ValueError("planning adaptation range cannot be inverted")
        expected = {
            "running": ("RUN_PACE", "seconds_per_km"),
            "cycling": ("POWER", "watts"),
            "swimming": ("SWIM_PACE", "seconds_per_100m"),
        }[self.sport]
        if (self.target_kind, self.unit) != expected:
            raise ValueError("planning adaptation target is incompatible with sport")
        increasing = self.proposal_kind == "INCREASE_TARGET"
        expected_direction = (
            "HIGHER_POWER" if self.sport == "cycling" and increasing else
            "LOWER_POWER" if self.sport == "cycling" else
            "FASTER_PACE" if increasing else "SLOWER_PACE"
        )
        if self.direction != expected_direction:
            raise ValueError("planning adaptation direction is inconsistent")
        if self.sport == "cycling":
            valid = self.proposed_minimum >= self.current_minimum and self.proposed_maximum >= self.current_maximum if increasing else self.proposed_minimum <= self.current_minimum and self.proposed_maximum <= self.current_maximum
        else:
            valid = self.proposed_minimum <= self.current_minimum and self.proposed_maximum <= self.current_maximum if increasing else self.proposed_minimum >= self.current_minimum and self.proposed_maximum >= self.current_maximum
        if not valid:
            raise ValueError("planning adaptation values contradict direction")
        return self


class PlanningAdaptationInput(FrozenModel):
    athlete_id: UUID
    proposal_version: str
    numeric_policy_version: str | None = None
    cutoff_date: date
    items: tuple[PlanningAdaptationItem, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_items(self):
        keys = [(item.sport, item.session_type, item.target_kind) for item in self.items]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("planning adaptation items must be unique and canonically ordered")
        if any(item.proposal_version != self.proposal_version or item.cutoff_date != self.cutoff_date for item in self.items):
            raise ValueError("planning adaptation versions and cutoffs must agree")
        if any(item.numeric_policy_version != self.numeric_policy_version for item in self.items):
            raise ValueError("planning adaptation numeric policy versions must agree")
        return self


class PlanningContext(FrozenModel):
    request: PlanningRequest
    preferences: PlanningPreferences
    goals: tuple[PlanningGoal, ...]
    performance: PerformanceSnapshot
    training: AthleteTrainingSnapshot
    training_status: TrainingStatusSnapshot | None
    versions: ContextVersions
    warnings: tuple[PlanningWarning, ...]
    adaptive_capability: AdaptiveCapabilitySnapshot | None = None
    quality_exposure: QualityExposureSnapshot | None = None
    planning_adaptation: PlanningAdaptationInput | None = None
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        # Preserve hashes of stored C.4 artifacts that predate this optional field.
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
                if not (key == "numeric_policy_version" and item is None)}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical datetimes must be timezone-aware")
        return value.isoformat(timespec="microseconds")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def context_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
