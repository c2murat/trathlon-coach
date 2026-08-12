from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

class AthleteProfileCompletenessResponse(BaseModel):
    status: Literal["minimal", "contextual"]
    missing_recommended_fields: list[str]

class AthleteProfileResponse(BaseModel):
    id: UUID
    display_name: str
    timezone: str
    unit_system: Literal["metric", "imperial"]
    birth_year: int | None
    sex_for_training_context: str | None
    height_m: float | None
    weight_kg: float | None
    updated_at: datetime
    completeness: AthleteProfileCompletenessResponse

class AthleteProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    unit_system: Literal["metric", "imperial"] | None = None
    birth_year: int | None = None
    sex_for_training_context: str | None = Field(default=None, max_length=32)
    height_m: Decimal | None = Field(default=None, max_digits=5, decimal_places=3)
    weight_kg: Decimal | None = Field(default=None, max_digits=6, decimal_places=3)

    @field_validator("display_name", "timezone", "unit_system")
    @classmethod
    def required_fields_cannot_be_null(cls, value, info):
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value