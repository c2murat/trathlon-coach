from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator

from app.application.athletes import normalize_athlete_display_name


class AthleteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    timezone: str
    unit_system: Literal["metric", "imperial"]

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_display_name(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return normalize_athlete_display_name(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("timezone must contain between 1 and 64 characters")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be a valid IANA timezone") from None
        return value


class AthleteCreateResponse(BaseModel):
    id: UUID
    display_name: str
    timezone: str
    unit_system: Literal["metric", "imperial"]
    role: Literal["owner"]
    is_default: bool
    capabilities: list[str]
