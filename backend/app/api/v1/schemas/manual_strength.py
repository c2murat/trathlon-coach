from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr


class ManualStrengthSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    timezone_name: StrictStr
    duration_minutes: StrictInt
    body_regions: list[StrictStr]
    perceived_exertion: StrictInt | None = None
    notes: StrictStr | None = None


class ManualStrengthSessionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: datetime | None = None
    timezone_name: StrictStr | None = None
    duration_minutes: StrictInt | None = None
    body_regions: list[StrictStr] | None = None
    perceived_exertion: StrictInt | None = None
    notes: StrictStr | None = None


class ManualStrengthTrainingLoadResponse(BaseModel):
    load_value: float
    method: str
    unit: str
    quality: str
    warnings: list[str]
    algorithm_version: str
    calculated_at: datetime


class ManualStrengthSessionResponse(BaseModel):
    id: UUID
    started_at: datetime
    timezone_name: str
    duration_minutes: int
    body_regions: list[str]
    perceived_exertion: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    training_load: ManualStrengthTrainingLoadResponse
