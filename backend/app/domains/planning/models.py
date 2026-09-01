from __future__ import annotations

from datetime import date, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

CompetitionCategory = Literal["triathlon", "running", "cycling", "swimming", "duathlon", "aquathlon"]
SegmentSport = Literal["swim", "bike", "run"]
CompetitionPriority = Literal["A", "B", "C"]
CompetitionStatus = Literal["active", "completed", "cancelled"]

class CompetitionGoalSegmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=1)
    sport: SegmentSport
    distance_m: int = Field(gt=0)
    label: str | None = Field(default=None, max_length=100)
    elevation_gain_m: int | None = Field(default=None, ge=0)

class CompetitionGoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    event_date: date
    event_start_time: time | None = None
    timezone: str = Field(min_length=1, max_length=64)
    event_category: CompetitionCategory
    event_format: str = Field(min_length=1, max_length=32)
    priority: CompetitionPriority
    segments: list[CompetitionGoalSegmentInput] = Field(default_factory=list, max_length=32)
    target_finish_time_seconds: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=4000)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    status: CompetitionStatus = "active"

    @model_validator(mode="after")
    def validate_shape(self):
        try: ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError: raise ValueError("invalid timezone") from None
        if [item.position for item in self.segments] != list(range(1, len(self.segments) + 1)):
            raise ValueError("segment positions must be contiguous and ordered")
        return self
class WorkoutDuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["time", "distance", "open"]
    seconds: int | None = Field(default=None, gt=0)
    meters: int | None = Field(default=None, gt=0)
    estimated_seconds: int | None = Field(default=None, gt=0)
    @model_validator(mode="after")
    def valid_value(self):
        if self.mode == "time" and (self.seconds is None or self.meters is not None or self.estimated_seconds is not None): raise ValueError("time duration requires seconds")
        if self.mode == "distance" and (self.meters is None or self.seconds is not None): raise ValueError("distance duration requires meters")
        if self.mode == "open" and (self.seconds is not None or self.meters is not None or self.estimated_seconds is not None): raise ValueError("open duration has no value")
        return self

class WorkoutTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Literal["power", "heart_rate", "pace", "swim_pace", "cadence", "rpe", "none"]
    mode: Literal["zone", "absolute_range", "percent_reference", "none"]
    reference: Literal["FTP", "threshold_hr", "threshold_pace", "CSS"] | None = None
    minimum: float | None = Field(default=None, ge=0)
    maximum: float | None = Field(default=None, ge=0)
    zone_min: int | None = Field(default=None, ge=1, le=10)
    zone_max: int | None = Field(default=None, ge=1, le=10)
    reference_value: float | None = Field(default=None, gt=0)
    reference_unit: Literal["watts", "seconds_per_km", "seconds_per_100m"] | None = None
    resolved_minimum: float | None = Field(default=None, ge=0)
    resolved_maximum: float | None = Field(default=None, ge=0)
    resolved_unit: Literal["watts", "seconds_per_km", "seconds_per_100m"] | None = None
    @model_validator(mode="after")
    def valid_range(self):
        if self.mode == "none":
            if self.metric != "none": raise ValueError("none mode requires none metric")
            return self
        if self.metric == "none": raise ValueError("target metric required")
        if self.mode == "zone":
            if self.zone_min is None or self.zone_max is None or self.zone_min > self.zone_max: raise ValueError("invalid zone range")
        else:
            if self.minimum is None or self.maximum is None or self.minimum > self.maximum: raise ValueError("invalid target range")
        if self.mode == "percent_reference" and self.reference is None: raise ValueError("reference required")
        resolved = (self.reference_value, self.reference_unit, self.resolved_minimum, self.resolved_maximum, self.resolved_unit)
        if any(item is not None for item in resolved):
            if any(item is None for item in resolved): raise ValueError("resolved target snapshot must be complete")
            if self.mode != "percent_reference": raise ValueError("resolved target requires percent reference mode")
            if self.resolved_minimum > self.resolved_maximum: raise ValueError("invalid resolved target range")
            if self.reference_unit != self.resolved_unit: raise ValueError("reference and resolved units must match")
        return self

class WorkoutNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["step", "repeat"]
    phase: Literal["warmup", "work", "recovery", "cooldown", "drill", "strength"] | None = None
    duration: WorkoutDuration | None = None
    target: WorkoutTarget | None = None
    instructions: str | None = Field(default=None, max_length=1000)
    title: str | None = Field(default=None, max_length=120)
    movement_pattern: Literal["KNEE_DOMINANT", "HIP_HINGE", "UNILATERAL_LOWER", "CALF", "SOLEUS", "HORIZONTAL_PULL", "HORIZONTAL_PUSH", "CORE_ANTI_EXTENSION", "CORE_ANTI_ROTATION", "CORE_LATERAL"] | None = None
    sets: int | None = Field(default=None, ge=1, le=10)
    reps: int | None = Field(default=None, ge=1, le=100)
    rest_seconds: int | None = Field(default=None, ge=0, le=600)
    unilateral: bool | None = None
    repetitions: int | None = Field(default=None, ge=2, le=100)
    steps: list[WorkoutNode] | None = None
    @model_validator(mode="after")
    def valid_node(self):
        if self.kind == "step":
            if self.phase is None or self.duration is None or self.repetitions is not None or self.steps is not None: raise ValueError("invalid workout step")
            strength = (self.movement_pattern, self.sets, self.reps, self.rest_seconds, self.unilateral)
            if any(item is not None for item in strength) and self.phase != "strength": raise ValueError("exercise fields require strength phase")
            if self.phase == "strength" and any(item is None for item in (self.title, self.movement_pattern, self.sets, self.rest_seconds)): raise ValueError("strength exercise snapshot must be complete")
        elif self.repetitions is None or not self.steps or self.phase is not None or self.duration is not None or self.target is not None:
            raise ValueError("invalid repeat block")
        return self

class StructuredWorkoutDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    sport: Literal["running", "cycling", "swimming", "strength", "multisport"]
    title: str | None = Field(default=None, max_length=200)
    purpose: str | None = Field(default=None, max_length=100)
    steps: list[WorkoutNode] = Field(min_length=1)
