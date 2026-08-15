from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.db.models import User
from app.db.session import get_db_session


def require_owner_account(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> User:
    user = session.get(User, current_user.id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "authentication_required"})
    if user.account_plan != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "owner_account_required"})
    return user
