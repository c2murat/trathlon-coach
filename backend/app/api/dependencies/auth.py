from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.application.authentication import SessionAuthenticationError, UserAuthSessionService
from app.core.settings import Settings, get_settings
from app.db.session import get_db_session


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Minimal authenticated identity passed into application endpoints."""

    id: UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    """Internal authentication context; session identifiers never cross the API."""

    user_id: UUID
    auth_session_id: UUID | None


LOCAL_MVP_USER_ID = UUID("00000000-0000-4000-8000-000000000001")


def get_development_current_user(settings: Settings) -> AuthenticatedUser:
    if settings.environment not in {"development", "test"}:
        raise authentication_required()
    return AuthenticatedUser(id=LOCAL_MVP_USER_ID)


def get_current_auth_session(
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> AuthenticatedSession:
    """Resolve the user and centrally enforce CSRF for cookie-authenticated writes."""

    if settings.auth_mode == "development":
        user = get_development_current_user(settings)
        return AuthenticatedSession(user_id=user.id, auth_session_id=None)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise authentication_required()
    service = UserAuthSessionService(session)
    try:
        auth_session = service.resolve_session(raw_token)
    except (SessionAuthenticationError, ValueError):
        raise authentication_required() from None
    if request.method.upper() not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") not in settings.allowed_frontend_origins():
            raise origin_validation_failed()
        csrf_token = request.headers.get(settings.csrf_header_name)
        if not csrf_token or not service.verify_csrf(auth_session, csrf_token):
            raise csrf_validation_failed()
    return AuthenticatedSession(
        user_id=auth_session.user_id,
        auth_session_id=auth_session.id,
    )


def get_current_user(
    authenticated_session: AuthenticatedSession = Depends(get_current_auth_session),
) -> AuthenticatedUser:
    return AuthenticatedUser(id=authenticated_session.user_id)


def authentication_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "authentication_required"},
        headers={"WWW-Authenticate": "Session"},
    )


def csrf_validation_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "csrf_validation_failed"},
    )

def origin_validation_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "origin_validation_failed"},
    )
