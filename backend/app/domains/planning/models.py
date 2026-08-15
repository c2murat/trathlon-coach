from __future__ import annotations

from datetime import date, time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

CompetitionCategory = Literal["triathlon", "running", "cycling", "swimming"]
CompetitionPriority = Literal["A", "B", "C"]
CompetitionStatus = Literal["active", "completed", "cancelled"]

class CompetitionGoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    event_date: date
    event_start_time: time | None = None
    timezone: str = Field(min_length=1, max_length=64)
    event_category: CompetitionCategory
    event_format: str = Field(min_length=1, max_length=32)
    priority: CompetitionPriority
    distance_m: int | None = Field(default=None, ge=0)
    swim_distance_m: int | None = Field(default=None, ge=0)
    bike_distance_m: int | None = Field(default=None, ge=0)
    run_distance_m: int | None = Field(default=None, ge=0)
    target_finish_time_seconds: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=4000)
    status: CompetitionStatus = "active"

    @model_validator(mode="after")
    def validate_shape(self):
        try: ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError: raise ValueError("invalid timezone") from None
        triathlon = self.event_category == "triathlon"
        legs = (self.swim_distance_m, self.bike_distance_m, self.run_distance_m)
        if triathlon and (self.distance_m is not None or any(value is None for value in legs)):
            raise ValueError("triathlon requires swim, bike and run distances")
        if not triathlon and (self.distance_m is None or any(value is not None for value in legs)):
            raise ValueError("single-sport competition requires distance_m only")
        return self

class WorkoutDuration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["time", "distance", "open"]
    seconds: int | None = Field(default=None, gt=0)
    meters: int | None = Field(default=None, gt=0)
    @model_validator(mode="after")
    def valid_value(self):
        if self.mode == "time" and (self.seconds is None or self.meters is not None): raise ValueError("time duration requires seconds")
        if self.mode == "distance" and (self.meters is None or self.seconds is not None): raise ValueError("distance duration requires meters")
        if self.mode == "open" and (self.seconds is not None or self.meters is not None): raise ValueError("open duration has no value")
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
        return self

class WorkoutNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["step", "repeat"]
    phase: Literal["warmup", "work", "recovery", "cooldown"] | None = None
    duration: WorkoutDuration | None = None
    target: WorkoutTarget | None = None
    instructions: str | None = Field(default=None, max_length=1000)
    repetitions: int | None = Field(default=None, ge=2, le=100)
    steps: list[WorkoutNode] | None = None
    @model_validator(mode="after")
    def valid_node(self):
        if self.kind == "step":
            if self.phase is None or self.duration is None or self.repetitions is not None or self.steps is not None: raise ValueError("invalid workout step")
        elif self.repetitions is None or not self.steps or self.phase is not None or self.duration is not None or self.target is not None:
            raise ValueError("invalid repeat block")
        return self

class StructuredWorkoutDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    sport: Literal["running", "cycling", "swimming", "strength", "multisport"]
    steps: list[WorkoutNode] = Field(min_length=1)
