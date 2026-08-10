from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.base import utc_now
from app.db.models import User, UserAuthSession
from app.security.tokens import generate_secret_token, hash_secret_token, verify_secret_token


class SessionAuthenticationError(Exception):
    """A deliberately non-specific authentication failure."""


@dataclass(frozen=True, slots=True)
class CreatedAuthSession:
    session_id: UUID
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    expires_at: datetime


class UserAuthSessionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_session(self, user_id: UUID, *, ttl: timedelta, now: datetime | None = None, max_active_sessions: int | None = None) -> CreatedAuthSession:
        if ttl <= timedelta(0):
            raise ValueError("Session TTL must be positive")
        user = self._session.get(User, user_id)
        if user is None or user.status != "active" or user.deleted_at is not None:
            raise SessionAuthenticationError
        created_at = now or utc_now()
        session_token = generate_secret_token()
        csrf_token = generate_secret_token()
        auth_session = UserAuthSession(
            user=user,
            token_hash=hash_secret_token(session_token),
            csrf_token_hash=hash_secret_token(csrf_token),
            created_at=created_at,
            expires_at=created_at + ttl,
        )
        self._session.add(auth_session)
        self._session.flush()
        if max_active_sessions is not None:
            if max_active_sessions < 1:
                raise ValueError("Active session limit must be positive")
            active_sessions = list(self._session.scalars(
                select(UserAuthSession).where(
                    UserAuthSession.user_id == user_id,
                    UserAuthSession.revoked_at.is_(None),
                    UserAuthSession.expires_at > created_at,
                ).order_by(UserAuthSession.created_at.asc(), UserAuthSession.id.asc())
            ).all())
            for oldest in active_sessions[:-max_active_sessions]:
                oldest.revoked_at = created_at
            self._session.flush()
        return CreatedAuthSession(
            session_id=auth_session.id,
            session_token=session_token,
            csrf_token=csrf_token,
            expires_at=auth_session.expires_at,
        )

    def resolve_session(self, raw_session_token: str, *, now: datetime | None = None) -> UserAuthSession:
        token_hash = hash_secret_token(raw_session_token)
        auth_session = self._session.scalar(
            select(UserAuthSession)
            .options(joinedload(UserAuthSession.user))
            .where(UserAuthSession.token_hash == token_hash)
        )
        current_time = now or utc_now()
        if (
            auth_session is None
            or auth_session.revoked_at is not None
            or auth_session.expires_at <= current_time
            or auth_session.user.status != "active"
            or auth_session.user.deleted_at is not None
        ):
            raise SessionAuthenticationError
        return auth_session

    def resolve_user(self, raw_session_token: str, *, now: datetime | None = None) -> User:
        return self.resolve_session(raw_session_token, now=now).user

    def verify_csrf(self, auth_session: UserAuthSession, raw_csrf_token: str) -> bool:
        return verify_secret_token(raw_csrf_token, auth_session.csrf_token_hash)

    def revoke_session(self, raw_session_token: str, *, now: datetime | None = None) -> bool:
        token_hash = hash_secret_token(raw_session_token)
        auth_session = self._session.scalar(
            select(UserAuthSession).where(UserAuthSession.token_hash == token_hash)
        )
        if auth_session is None:
            return False
        if auth_session.revoked_at is None:
            auth_session.revoked_at = now or utc_now()
            self._session.flush()
        return True
