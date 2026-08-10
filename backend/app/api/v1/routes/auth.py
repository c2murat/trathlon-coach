from datetime import timedelta
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthenticatedUser, csrf_validation_failed, get_current_user
from app.api.v1.schemas.auth import AuthenticatedUserResponse, LoginRequest
from app.application.authentication import SessionAuthenticationError, UserAuthSessionService
from app.application.login_rate_limit import InMemoryLoginRateLimiter, LoginRateLimitPolicy
from app.core.settings import Settings, get_settings
from app.db.base import utc_now
from app.db.models import User
from app.db.session import get_db_session
from app.security.identity import normalize_email
from app.security.passwords import hash_password, verify_and_update_password


router = APIRouter(prefix="/auth", tags=["authentication"])
_DUMMY_PASSWORD_HASH = hash_password("tricoach-invalid-password")
def get_login_rate_limiter(request: Request, settings: Settings = Depends(get_settings)) -> InMemoryLoginRateLimiter:
    policy = LoginRateLimitPolicy(settings.login_rate_limit_failures, settings.login_rate_limit_window_seconds, settings.login_rate_limit_max_keys)
    limiter = getattr(request.app.state, "login_rate_limiter", None)
    lock = getattr(request.app.state, "login_rate_limiter_lock", None)
    if limiter is not None and limiter.policy == policy:
        return limiter
    if lock is None:
        limiter = InMemoryLoginRateLimiter(policy)
        request.app.state.login_rate_limiter = limiter
        return limiter
    with lock:
        limiter = getattr(request.app.state, "login_rate_limiter", None)
        if limiter is None or limiter.policy != policy:
            limiter = InMemoryLoginRateLimiter(policy)
            request.app.state.login_rate_limiter = limiter
        return limiter
def _public_user(user: User, mode: str) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse(id=user.id,email=user.email,display_name=(user.display_name or "").strip() or user.email,authentication_mode=mode)


def _set_auth_cookies(response: Response, created, settings: Settings) -> None:
    common={"max_age":settings.session_ttl_seconds,"expires":created.expires_at,"path":settings.session_cookie_path,"secure":settings.session_cookie_secure,"samesite":settings.session_cookie_samesite}
    response.set_cookie(settings.session_cookie_name,created.session_token,httponly=True,**common)
    response.set_cookie(settings.csrf_cookie_name,created.csrf_token,httponly=False,**common)


def _delete_auth_cookies(response: Response, settings: Settings) -> None:
    common={"path":settings.session_cookie_path,"secure":settings.session_cookie_secure,"samesite":settings.session_cookie_samesite}
    response.delete_cookie(settings.session_cookie_name,httponly=True,**common)
    response.delete_cookie(settings.csrf_cookie_name,httponly=False,**common)


@router.post("/login", response_model=AuthenticatedUserResponse)
def login(payload:LoginRequest,request:Request,response:Response,settings:Settings=Depends(get_settings),session:Session=Depends(get_db_session),limiter:InMemoryLoginRateLimiter=Depends(get_login_rate_limiter))->AuthenticatedUserResponse:
    if settings.auth_mode!="session":raise HTTPException(status_code=409,detail={"code":"auth_mode_not_session"})
    normalized_email=normalize_email(payload.email);remote_host=request.client.host if request.client else "unknown";limit_key=f"{remote_host}|{normalized_email}"
    if limiter.is_limited(limit_key):raise HTTPException(status_code=429,detail={"code":"too_many_login_attempts"},headers={"Retry-After":str(settings.login_rate_limit_window_seconds)})
    user=session.scalar(select(User).where(User.normalized_email==normalized_email));password=payload.password.get_secret_value()
    password_valid,updated_hash=verify_and_update_password(password,user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH)
    if user is None or not password_valid or user.password_hash is None or user.status!="active" or user.deleted_at is not None:
        limiter.record_failure(limit_key);raise HTTPException(status_code=401,detail={"code":"invalid_credentials"})
    try:
        if updated_hash is not None:user.password_hash=updated_hash
        created=UserAuthSessionService(session).create_session(user.id,ttl=timedelta(seconds=settings.session_ttl_seconds),max_active_sessions=settings.max_active_sessions_per_user)
        user.last_login_at=utc_now();session.commit()
    except Exception:
        session.rollback();raise
    limiter.reset(limit_key);_set_auth_cookies(response,created,settings);return _public_user(user,"session")


@router.get("/me",response_model=AuthenticatedUserResponse)
def me(current_user:AuthenticatedUser=Depends(get_current_user),settings:Settings=Depends(get_settings),session:Session=Depends(get_db_session))->AuthenticatedUserResponse:
    user=session.get(User,current_user.id)
    if user is None:raise HTTPException(status_code=401,detail={"code":"authentication_required"})
    return _public_user(user,settings.auth_mode)


@router.post("/logout",status_code=status.HTTP_204_NO_CONTENT)
def logout(request:Request,response:Response,settings:Settings=Depends(get_settings),session:Session=Depends(get_db_session))->Response:
    if settings.auth_mode!="session":raise HTTPException(status_code=409,detail={"code":"auth_mode_not_session"})
    raw_token=request.cookies.get(settings.session_cookie_name)
    if raw_token:
        service=UserAuthSessionService(session)
        try:auth_session=service.resolve_session(raw_token)
        except (SessionAuthenticationError,ValueError):auth_session=None
        if auth_session is not None:
            origin=request.headers.get("origin")
            if origin is not None and origin.rstrip("/") not in settings.allowed_frontend_origins():raise HTTPException(status_code=403,detail={"code":"origin_validation_failed"})
            csrf_token=request.headers.get(settings.csrf_header_name)
            if not csrf_token or not service.verify_csrf(auth_session,csrf_token):raise csrf_validation_failed()
            service.revoke_session(raw_token);session.commit()
    _delete_auth_cookies(response,settings);response.status_code=status.HTTP_204_NO_CONTENT;return response