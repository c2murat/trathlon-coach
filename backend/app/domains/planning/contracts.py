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
    preferences: PlanningPreferences
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
    role: Literal["primary", "supporting"] | None = None
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
    ]
    severity: Literal["WARNING"] = "WARNING"
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


class PlanningContext(FrozenModel):
    request: PlanningRequest
    goals: tuple[PlanningGoal, ...]
    performance: PerformanceSnapshot
    training: AthleteTrainingSnapshot
    training_status: TrainingStatusSnapshot | None
    versions: ContextVersions
    warnings: tuple[PlanningWarning, ...]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
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
