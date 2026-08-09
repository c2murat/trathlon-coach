from uuid import UUID

from pydantic import BaseModel, Field, SecretStr


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)


class AuthenticatedUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    authentication_mode: str
