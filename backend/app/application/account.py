from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import User, UserAuthSession
from app.security.passwords import hash_password, verify_and_update_password


class AccountUnavailableError(Exception):
    """The authenticated account is no longer available for self-service."""


class CurrentPasswordInvalidError(Exception):
    """The supplied current credential cannot authorize the change."""


class PasswordUnchangedError(Exception):
    """The replacement credential must differ from the current credential."""


class AccountApplication:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_account(self, user_id: UUID) -> User:
        user = self._session.get(User, user_id)
        if user is None or user.status != "active" or user.deleted_at is not None:
            raise AccountUnavailableError
        return user

    def update_account(self, user_id: UUID, *, display_name: str | None) -> User:
        user = self.get_account(user_id)
        user.display_name = display_name
        self._session.flush()
        return user

    def change_password(
        self,
        user_id: UUID,
        *,
        current_session_id: UUID,
        current_password: str,
        new_password: str,
    ) -> None:
        user = self.get_account(user_id)
        if user.password_hash is None:
            raise CurrentPasswordInvalidError
        password_valid, _ = verify_and_update_password(current_password, user.password_hash)
        if not password_valid:
            raise CurrentPasswordInvalidError
        if new_password == current_password:
            raise PasswordUnchangedError

        new_hash = hash_password(new_password)
        now = utc_now()
        other_active_sessions = self._session.scalars(
            select(UserAuthSession).where(
                UserAuthSession.user_id == user.id,
                UserAuthSession.id != current_session_id,
                UserAuthSession.revoked_at.is_(None),
                UserAuthSession.expires_at > now,
            )
        ).all()
        user.password_hash = new_hash
        for auth_session in other_active_sessions:
            auth_session.revoked_at = now
        self._session.flush()