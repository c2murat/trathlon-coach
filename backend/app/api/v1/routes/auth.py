from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException,Request,Response,status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.dependencies.auth import AuthenticatedUser,csrf_validation_failed,get_current_user
from app.api.v1.schemas.auth import AuthenticatedUserResponse,LoginRequest,RegistrationRequest
from app.application.account_registration import AccountRegistrationApplication,RegistrationError
from app.application.authentication import SessionAuthenticationError,UserAuthSessionService
from app.application.login_rate_limit import InMemoryLoginRateLimiter,LoginRateLimitPolicy
from app.core.settings import Settings,get_settings
from app.db.base import utc_now
from app.db.models import User
from app.db.session import get_db_session
from app.security.identity import normalize_email
from app.security.passwords import hash_password,verify_and_update_password
router=APIRouter(prefix="/auth",tags=["authentication"])
_DUMMY_PASSWORD_HASH=hash_password("tricoach-invalid-password")
def _limiter(request:Request,name:str,policy:LoginRateLimitPolicy)->InMemoryLoginRateLimiter:
 limiter=getattr(request.app.state,name,None)
 if limiter is None or limiter.policy!=policy:
  limiter=InMemoryLoginRateLimiter(policy);setattr(request.app.state,name,limiter)
 return limiter
def get_login_rate_limiter(request:Request,settings:Settings=Depends(get_settings))->InMemoryLoginRateLimiter:return _limiter(request,"login_rate_limiter",LoginRateLimitPolicy(settings.login_rate_limit_failures,settings.login_rate_limit_window_seconds,settings.login_rate_limit_max_keys))
def get_registration_rate_limiter(request:Request,settings:Settings=Depends(get_settings))->InMemoryLoginRateLimiter:return _limiter(request,"registration_rate_limiter",LoginRateLimitPolicy(settings.registration_rate_limit_attempts,settings.registration_rate_limit_window_seconds,settings.registration_rate_limit_max_keys))
def _public_user(user:User,mode:str)->AuthenticatedUserResponse:return AuthenticatedUserResponse(id=user.id,email=user.email,display_name=(user.display_name or "").strip() or user.email,authentication_mode=mode,account_plan=user.account_plan)
def _set_auth_cookies(response:Response,created,settings:Settings)->None:
 common={"max_age":settings.session_ttl_seconds,"expires":created.expires_at,"path":settings.session_cookie_path,"secure":settings.session_cookie_secure,"samesite":settings.session_cookie_samesite};response.set_cookie(settings.session_cookie_name,created.session_token,httponly=True,**common);response.set_cookie(settings.csrf_cookie_name,created.csrf_token,httponly=False,**common)
def _delete_auth_cookies(response:Response,settings:Settings)->None:
 common={"path":settings.session_cookie_path,"secure":settings.session_cookie_secure,"samesite":settings.session_cookie_samesite};response.delete_cookie(settings.session_cookie_name,httponly=True,**common);response.delete_cookie(settings.csrf_cookie_name,httponly=False,**common)
@router.post("/register",response_model=AuthenticatedUserResponse,status_code=status.HTTP_201_CREATED)
def register(payload:RegistrationRequest,request:Request,response:Response,settings:Settings=Depends(get_settings),session:Session=Depends(get_db_session),limiter:InMemoryLoginRateLimiter=Depends(get_registration_rate_limiter))->AuthenticatedUserResponse:
 if settings.auth_mode!="session":raise HTTPException(409,detail={"code":"auth_mode_not_session"})
 if not settings.public_registration_enabled:raise HTTPException(403,detail={"code":"registration_disabled"})
 key=f"{request.client.host if request.client else 'unknown'}|{normalize_email(payload.email)}"
 if limiter.is_limited(key):raise HTTPException(429,detail={"code":"too_many_registration_attempts"},headers={"Retry-After":str(settings.registration_rate_limit_window_seconds)})
 try:
  user=AccountRegistrationApplication(session).register(display_name=payload.display_name,email=payload.email,password=payload.password.get_secret_value(),account_plan=payload.account_plan,timezone=payload.timezone)
  created=UserAuthSessionService(session).create_session(user.id,ttl=timedelta(seconds=settings.session_ttl_seconds),max_active_sessions=settings.max_active_sessions_per_user);user.last_login_at=utc_now();session.commit()
 except RegistrationError as error:
  session.rollback();limiter.record_failure(key);code=str(error);raise HTTPException(409 if code=="registration_unavailable" else 422,detail={"code":code}) from None
 except IntegrityError:
  session.rollback();limiter.record_failure(key);raise HTTPException(409,detail={"code":"registration_unavailable"}) from None
 except Exception:
  session.rollback();raise
 limiter.reset(key);_set_auth_cookies(response,created,settings);return _public_user(user,"session")
@router.post("/login",response_model=AuthenticatedUserResponse)
def login(payload:LoginRequest,request:Request,response:Response,settings:Settings=Depends(get_settings),session:Session=Depends(get_db_session),limiter:InMemoryLoginRateLimiter=Depends(get_login_rate_limiter))->AuthenticatedUserResponse:
 if settings.auth_mode!="session":raise HTTPException(409,detail={"code":"auth_mode_not_session"})
 normalized_email=normalize_email(payload.email);key=f"{request.client.host if request.client else 'unknown'}|{normalized_email}"
 if limiter.is_limited(key):raise HTTPException(429,detail={"code":"too_many_login_attempts"},headers={"Retry-After":str(settings.login_rate_limit_window_seconds)})
 user=session.scalar(select(User).where(User.normalized_email==normalized_email));valid,updated=verify_and_update_password(payload.password.get_secret_value(),user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH)
 if user is None or not valid or user.password_hash is None or user.status!="active" or user.deleted_at is not None:limiter.record_failure(key);raise HTTPException(401,detail={"code":"invalid_credentials"})
 try:
  if updated is not None:user.password_hash=updated
  created=UserAuthSessionService(session).create_session(user.id,ttl=timedelta(seconds=settings.session_ttl_seconds),max_active_sessions=settings.max_active_sessions_per_user);user.last_login_at=utc_now();session.commit()
 except Exception:session.rollback();raise
 limiter.reset(key);_set_auth_cookies(response,created,settings);return _public_user(user,"session")
@router.get("/me",response_model=AuthenticatedUserResponse)
def me(current_user:AuthenticatedUser=Depends(get_current_user),settings:Settings=Depends(get_settings),session:Session=Depends(get_db_session))->AuthenticatedUserResponse:
 user=session.get(User,current_user.id)
 if user is None:raise HTTPException(401,detail={"code":"authentication_required"})
 return _public_user(user,settings.auth_mode)
@router.post("/logout",status_code=204)
def logout(request:Request,response:Response,settings:Settings=Depends(get_settings),session:Session=Depends(get_db_session))->Response:
 if settings.auth_mode!="session":raise HTTPException(409,detail={"code":"auth_mode_not_session"})
 raw=request.cookies.get(settings.session_cookie_name)
 if raw:
  service=UserAuthSessionService(session)
  try:auth_session=service.resolve_session(raw)
  except (SessionAuthenticationError,ValueError):auth_session=None
  if auth_session is not None:
   origin=request.headers.get("origin")
   if origin is not None and origin.rstrip("/") not in settings.allowed_frontend_origins():raise HTTPException(403,detail={"code":"origin_validation_failed"})
   csrf=request.headers.get(settings.csrf_header_name)
   if not csrf or not service.verify_csrf(auth_session,csrf):raise csrf_validation_failed()
   service.revoke_session(raw);session.commit()
 _delete_auth_cookies(response,settings);response.status_code=204;return response