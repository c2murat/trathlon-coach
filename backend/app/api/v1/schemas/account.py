from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class AccountResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    created_at: datetime
    last_login_at: datetime | None


class AccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def normalize_display_name(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        if not normalized:
            return None
        if len(normalized) > 200:
            raise ValueError("display_name cannot exceed 200 characters")
        return normalized

    @model_validator(mode="after")
    def require_display_name(self):
        if "display_name" not in self.model_fields_set:
            raise ValueError("display_name is required")
        return self