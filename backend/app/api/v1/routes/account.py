from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.schemas.account import AccountResponse, AccountUpdateRequest
from app.application.account import AccountApplication, AccountUnavailableError
from app.db.models import User
from app.db.session import get_db_session


router = APIRouter(prefix="/account", tags=["account"])


def _response(user: User) -> AccountResponse:
    return AccountResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _account_or_401(application: AccountApplication, current_user: AuthenticatedUser) -> User:
    try:
        return application.get_account(current_user.id)
    except AccountUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
        ) from None


@router.get("", response_model=AccountResponse)
def get_account(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> AccountResponse:
    return _response(_account_or_401(AccountApplication(session), current_user))


@router.patch("", response_model=AccountResponse)
def update_account(
    payload: AccountUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> AccountResponse:
    application = AccountApplication(session)
    try:
        user = application.update_account(current_user.id, display_name=payload.display_name)
        session.commit()
        session.refresh(user)
    except AccountUnavailableError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
        ) from None
    except Exception:
        session.rollback()
        raise
    return _response(user)