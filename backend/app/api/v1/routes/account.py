from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import (
    AuthenticatedSession,
    AuthenticatedUser,
    authentication_required,
    get_current_auth_session,
    get_current_user,
)
from app.api.v1.schemas.account import (
    AccountResponse,
    AccountUpdateRequest,
    PasswordChangeRequest,
)
from app.application.account import (
    AccountApplication,
    AccountUnavailableError,
    CurrentPasswordInvalidError,
    PasswordUnchangedError,
)
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

@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    authenticated_session: AuthenticatedSession = Depends(get_current_auth_session),
    session: Session = Depends(get_db_session),
) -> None:
    if authenticated_session.auth_session_id is None:
        raise authentication_required()
    application = AccountApplication(session)
    try:
        application.change_password(
            authenticated_session.user_id,
            current_session_id=authenticated_session.auth_session_id,
            current_password=payload.current_password.get_secret_value(),
            new_password=payload.new_password.get_secret_value(),
        )
        session.commit()
    except AccountUnavailableError:
        session.rollback()
        raise authentication_required() from None
    except CurrentPasswordInvalidError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "current_password_invalid"},
        ) from None
    except PasswordUnchangedError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "new_password_unchanged"},
        ) from None
    except Exception:
        session.rollback()
        raise
