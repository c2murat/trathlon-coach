from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.dependencies.auth import AuthenticatedUser,get_current_user
from app.application.authentication import UserAuthSessionService
from app.application.login_rate_limit import InMemoryLoginRateLimiter,LoginRateLimitPolicy
from app.core.settings import Settings,get_settings
from app.db.base import Base,utc_now
from app.db.models import User,UserAuthSession
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import hash_password,verify_password
from scripts.audit_authentication import audit
from scripts.cleanup_auth_sessions import cleanup_sessions

PASSWORD="a secure test password"

def user(session,email="user@example.test",**values):
    row=User(email=email,normalized_email=email,auth_subject="subject-"+email,password_hash=values.pop("password_hash",hash_password(PASSWORD)),status=values.pop("status","active"),**values);session.add(row);session.commit();return row

@pytest.fixture
def env():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);session=Session(engine);settings=Settings(auth_mode="session",environment="test",login_rate_limit_failures=2)
    app=create_app();app.dependency_overrides[get_db_session]=lambda:(yield session);app.dependency_overrides[get_settings]=lambda:settings
    @app.post("/test/write")
    def write(identity:AuthenticatedUser=Depends(get_current_user)):return {"id":str(identity.id)}
    @app.post("/test/external")
    def external():return {"ok":True}
    yield session,settings,app
    session.close();Base.metadata.drop_all(engine);engine.dispose()

def test_rate_limiter_is_independent_and_expires_without_leaking():
    now=[0.0];limiter=InMemoryLoginRateLimiter(LoginRateLimitPolicy(2,10,2),clock=lambda:now[0]);limiter.record_failure("a");limiter.record_failure("a");assert limiter.is_limited("a");assert not limiter.is_limited("b");now[0]=11;assert not limiter.is_limited("a");assert limiter.cleanup()==0

def test_login_limit_uniform_success_after_window_and_independent_keys(env):
    session,settings,app=env;user(session);client=TestClient(app)
    for _ in range(2):assert client.post("/auth/login",json={"email":"user@example.test","password":"wrong password"}).status_code==401
    blocked=client.post("/auth/login",json={"email":"user@example.test","password":PASSWORD});assert blocked.status_code==429;assert blocked.json()=={"detail":{"code":"too_many_login_attempts"}};assert blocked.headers["retry-after"]==str(settings.login_rate_limit_window_seconds)
    assert client.post("/auth/login",json={"email":"other@example.test","password":"wrong password"}).status_code==401
    app.state.login_rate_limiter.reset("testclient|user@example.test");assert client.post("/auth/login",json={"email":"user@example.test","password":PASSWORD}).status_code==200

def test_active_session_limit_revokes_oldest_but_ignores_expired_and_revoked(env):
    session,_,_=env;row=user(session);service=UserAuthSessionService(session);now=utc_now()
    expired=service.create_session(row.id,ttl=timedelta(seconds=1),now=now-timedelta(days=1));revoked=service.create_session(row.id,ttl=timedelta(days=2),now=now-timedelta(hours=2));service.revoke_session(revoked.session_token,now=now-timedelta(hours=1));first=service.create_session(row.id,ttl=timedelta(days=1),now=now-timedelta(minutes=1));second=service.create_session(row.id,ttl=timedelta(days=1),now=now,max_active_sessions=1);session.flush()
    assert session.get(UserAuthSession,second.session_id).revoked_at is None;assert session.get(UserAuthSession,first.session_id).revoked_at==now;assert session.get(UserAuthSession,expired.session_id).revoked_at is None

def test_cleanup_dry_run_and_execute_select_only_eligible(env):
    session,_,_=env;row=user(session);now=utc_now();active=UserAuthSession(user=row,token_hash="a"*64,csrf_token_hash="b"*64,created_at=now-timedelta(days=1),expires_at=now+timedelta(days=1));expired=UserAuthSession(user=row,token_hash="c"*64,csrf_token_hash="d"*64,created_at=now-timedelta(days=2),expires_at=now);revoked=UserAuthSession(user=row,token_hash="e"*64,csrf_token_hash="f"*64,created_at=now-timedelta(days=40),expires_at=now+timedelta(days=1),revoked_at=now-timedelta(days=31));recent=UserAuthSession(user=row,token_hash="1"*64,csrf_token_hash="2"*64,created_at=now-timedelta(days=2),expires_at=now+timedelta(days=1),revoked_at=now-timedelta(days=1));session.add_all([active,expired,revoked,recent]);session.commit()
    result=cleanup_sessions(session,now=now,revoked_retention=timedelta(days=30),dry_run=True);assert result["eligible_count"]==2;assert len(session.scalars(select(UserAuthSession)).all())==4
    result=cleanup_sessions(session,now=now,revoked_retention=timedelta(days=30),dry_run=False);session.flush();assert result["deleted_count"]==2;assert {x.id for x in session.scalars(select(UserAuthSession))}=={active.id,recent.id}

def test_secure_configuration_validation():
    with pytest.raises(ValidationError):Settings(environment="production",auth_mode="session",session_cookie_secure=False)
    assert not Settings(environment="development",auth_mode="session",session_cookie_secure=False).session_cookie_secure
    assert Settings(environment="production",auth_mode="session",session_cookie_secure=True).session_cookie_secure
    with pytest.raises(ValidationError):Settings(session_cookie_samesite="none",session_cookie_secure=False)

def test_origin_is_complementary_to_csrf_and_login_external_routes_unaffected(env):
    session,_,app=env;user(session);client=TestClient(app);assert client.post("/auth/login",headers={"Origin":"https://evil.test"},json={"email":"user@example.test","password":PASSWORD}).status_code==200;token=client.cookies.get("tricoach_csrf")
    assert client.post("/test/write",headers={"Origin":"http://127.0.0.1:5173","X-CSRF-Token":token}).status_code==200
    response=client.post("/test/write",headers={"Origin":"https://evil.test","X-CSRF-Token":token});assert response.status_code==403;assert response.json()["detail"]["code"]=="origin_validation_failed"
    assert client.post("/test/write",headers={"X-CSRF-Token":token}).status_code==200;assert client.get("/auth/me",headers={"Origin":"https://evil.test"}).status_code==200;assert client.post("/test/external",headers={"Origin":"https://evil.test"}).status_code==200

def test_password_rehash_and_last_login_only_on_success(env,monkeypatch):
    session,_,app=env;row=user(session);original=row.password_hash;calls=[]
    monkeypatch.setattr("app.api.v1.routes.auth.verify_and_update_password",lambda password,stored:(password==PASSWORD,"replacement-hash" if password==PASSWORD else None));client=TestClient(app)
    assert client.post("/auth/login",json={"email":row.email,"password":"wrong password"}).status_code==401;session.refresh(row);assert row.password_hash==original and row.last_login_at is None
    assert client.post("/auth/login",json={"email":row.email,"password":PASSWORD}).status_code==200;session.refresh(row);assert row.password_hash=="replacement-hash" and row.last_login_at is not None

def test_current_hash_is_not_replaced_and_failed_account_states_keep_last_login(env):
    session,_,app=env;row=user(session);original=row.password_hash;client=TestClient(app);assert client.post("/auth/login",json={"email":row.email,"password":PASSWORD}).status_code==200;session.refresh(row);assert row.password_hash==original
    for status,deleted in (("disabled",None),("active",utc_now())):
        candidate=user(session,f"{status}-{bool(deleted)}@example.test",status=status,deleted_at=deleted);assert client.post("/auth/login",json={"email":candidate.email,"password":PASSWORD}).status_code==401;session.refresh(candidate);assert candidate.last_login_at is None

def test_auth_auditor_clean_and_detects_main_inconsistencies_without_writes(env):
    session,settings,_=env;row=user(session);now=utc_now();bad=UserAuthSession(user=row,token_hash="bad",csrf_token_hash="also-bad",created_at=now,expires_at=now-timedelta(seconds=1));row.password_hash="not-argon2";session.add(bad);session.commit();before=(bad.token_hash,row.password_hash);result=audit(session,settings=settings,now=now);assert result["issue_count"]>=4;assert result["checks"]["invalid_lifetime"] and result["checks"]["invalid_token_hash"] and result["checks"]["invalid_csrf_hash"] and result["checks"]["unexpected_password_hash"];assert (bad.token_hash,row.password_hash)==before
    session.delete(bad);row.password_hash=hash_password(PASSWORD);session.commit();assert audit(session,settings=settings,now=now)["issue_count"]==0
def test_logout_cookie_deletion_is_symmetric(env):
    session,settings,app=env;user(session);client=TestClient(app);login=client.post("/auth/login",json={"email":"user@example.test","password":PASSWORD});csrf=client.cookies.get(settings.csrf_cookie_name);logout=client.post("/auth/logout",headers={settings.csrf_header_name:csrf});assert logout.status_code==204
    cookies=logout.headers.get_list("set-cookie");session_cookie=next(x for x in cookies if x.startswith(settings.session_cookie_name+"="));csrf_cookie=next(x for x in cookies if x.startswith(settings.csrf_cookie_name+"="));assert "Path=/" in session_cookie and "SameSite=lax" in session_cookie and "Max-Age=0" in session_cookie and "expires=" in session_cookie.lower() and "HttpOnly" in session_cookie;assert "Path=/" in csrf_cookie and "SameSite=lax" in csrf_cookie and "Max-Age=0" in csrf_cookie and "expires=" in csrf_cookie.lower() and "HttpOnly" not in csrf_cookie
