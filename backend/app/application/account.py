from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import User


class AccountUnavailableError(Exception):
    """The authenticated account is no longer available for self-service."""


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