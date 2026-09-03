from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.domains.planning.contracts import FrozenModel, PerformanceSnapshot


CAPABILITY_ALGORITHM_VERSION = "0.8G.2A"
CAPABILITY_WINDOW_WEEKS = 12
CAPABILITY_WINDOW_DAYS = CAPABILITY_WINDOW_WEEKS * 7
RECENCY_WEIGHTS = {"RECENT": Decimal("1.00"), "MID": Decimal("0.75"), "OLDER": Decimal("0.50")}


class CapabilityConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class CapabilityPoint(FrozenModel):
    duration_seconds: int | None = Field(default=None, gt=0)
    distance_m: int | None = Field(default=None, gt=0)
    best_value: Decimal = Field(gt=0)
    representative_value: Decimal = Field(gt=0)
    usable_representative_value: Decimal = Field(gt=0)
    unit: Literal["seconds_per_km", "watts", "seconds_per_100m"]
    representative_support_count: int = Field(ge=1)
    representative_latest_evidence_date: date
    representative_days_since_evidence: int = Field(ge=0)
    representative_confidence: CapabilityConfidence
    representative_source_activity_ids: tuple[UUID, ...] = Field(min_length=1, max_length=4)
    evidence_coverage: Decimal = Field(ge=0, le=1)
    best_source_activity_id: UUID
    best_source_date: date
    best_source_lap_index: int | None = Field(default=None, ge=0)


class RepeatLikeEffort(FrozenModel):
    repeat_count: int = Field(ge=3)
    typical_duration_seconds: int = Field(gt=0)
    typical_distance_m: int | None = Field(default=None, gt=0)
    representative_value: Decimal = Field(gt=0)
    unit: Literal["seconds_per_km", "watts", "seconds_per_100m"]
    variation_ratio: Decimal = Field(ge=0)
    evidence_date: date
    days_since_evidence: int = Field(ge=0)
    confidence: CapabilityConfidence
    source_activity_id: UUID


class LongSessionTolerance(FrozenModel):
    longest_duration_seconds: int | None = Field(default=None, ge=0)
    longest_last_4w_seconds: int | None = Field(default=None, ge=0)
    median_weekly_longest_seconds: int | None = Field(default=None, ge=0)
    long_session_count: int = Field(ge=0)
    days_since_last_long: int | None = Field(default=None, ge=0)


class SportTrainingSummary(FrozenModel):
    sport: Literal["running", "cycling", "swimming", "strength"]
    activity_count: int = Field(ge=0)
    weeks_active: int = Field(ge=0, le=12)
    sessions_per_week: Decimal = Field(ge=0)
    minutes_per_week: Decimal = Field(ge=0)
    distance_per_week_m: Decimal | None = Field(default=None, ge=0)
    recent_4w_minutes: Decimal = Field(ge=0)
    mid_4w_minutes: Decimal = Field(ge=0)
    older_4w_minutes: Decimal = Field(ge=0)
    longest_session_duration_seconds: int | None = Field(default=None, ge=0)
    longest_session_last_4w_seconds: int | None = Field(default=None, ge=0)
    median_session_duration_seconds: int | None = Field(default=None, ge=0)
    quality_session_count: int = Field(ge=0)
    high_intensity_exposure_seconds: int = Field(ge=0)
    session_classification_counts: dict[str, int]
    intensity_distribution_seconds: dict[str, int]
    consistency: Decimal = Field(ge=0, le=1)
    trend: Literal["increasing", "stable", "decreasing", "insufficient_data"]
    training_summary_coverage: Decimal = Field(ge=0, le=1)
    confidence: CapabilityConfidence
    long_tolerance: LongSessionTolerance | None = None


class SportCapabilityProfile(FrozenModel):
    summary: SportTrainingSummary
    duration_efforts: tuple[CapabilityPoint, ...] = ()
    distance_efforts: tuple[CapabilityPoint, ...] = ()
    repeat_like_efforts: tuple[RepeatLikeEffort, ...] = ()


class ReferenceStalenessSignal(FrozenModel):
    reference_type: Literal["cycling_ftp_watts", "running_threshold_pace_seconds_per_km", "swimming_css_seconds_per_100m"]
    reference_value: Decimal = Field(gt=0)
    evidence_value: Decimal = Field(gt=0)
    evidence_date: date
    confidence: CapabilityConfidence
    reason: str


class OverallTrainingSummary(FrozenModel):
    activity_count: int = Field(ge=0)
    weeks_with_training: int = Field(ge=0, le=12)
    total_minutes: Decimal = Field(ge=0)
    consistency: Decimal = Field(ge=0, le=1)
    training_status_date: date | None = None
    fitness: Decimal | None = None
    fatigue: Decimal | None = None
    form: Decimal | None = None


class AthleteCapabilityContext(FrozenModel):
    athlete_profile_id: UUID
    as_of_date: date
    window_start: date
    window_end: date
    window_weeks: int = CAPABILITY_WINDOW_WEEKS
    algorithm_version: str = CAPABILITY_ALGORITHM_VERSION
    available_history_days: int = Field(ge=0, le=CAPABILITY_WINDOW_DAYS)
    weeks_with_training: int = Field(ge=0, le=12)
    coverage_ratio: Decimal = Field(ge=0, le=1)
    activity_count: int = Field(ge=0)
    confidence: CapabilityConfidence
    performance_references: PerformanceSnapshot
    running: SportCapabilityProfile
    cycling: SportCapabilityProfile
    swimming: SportCapabilityProfile
    strength: SportCapabilityProfile
    overall_training_summary: OverallTrainingSummary
    reference_staleness_signals: tuple[ReferenceStalenessSignal, ...] = ()
    relevant_future_sports: tuple[Literal["running", "cycling", "swimming"], ...] = ()
