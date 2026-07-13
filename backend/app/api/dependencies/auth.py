from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.core.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Minimal authenticated identity passed into application endpoints."""

    id: UUID


LOCAL_MVP_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


def get_current_user(settings: Settings = Depends(get_settings)) -> AuthenticatedUser:
    """Return one fixed local user until authentication is implemented.

    SECURITY TODO: replace this dependency before any non-development deployment.
    It intentionally refuses to provide an identity outside development/test.
    """

    if settings.environment not in {"development", "test"}:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"code": "authentication_not_implemented"},
        )
    return AuthenticatedUser(id=LOCAL_MVP_USER_ID)

