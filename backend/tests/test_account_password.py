from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base, utc_now
from app.db.models import User, UserAuthSession
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import hash_password, verify_password
from app.security.tokens import hash_secret_token


OLD = "a secure current password"
NEW = "a different secure password"


@pytest.fixture
def env():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    settings = Settings(auth_mode="session", environment="test")
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: (yield session)
    app.dependency_overrides[get_settings] = lambda: settings
    yield session, app
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def user(session, suffix="user", **values):
    row = User(email=f"{suffix}@example.test", normalized_email=f"{suffix}@example.test", auth_subject=f"subject-{suffix}", password_hash=values.pop("password_hash", hash_password(OLD)), last_login_at=values.pop("last_login_at", utc_now() - timedelta(days=1)), **values)
    session.add(row)
    session.commit()
    return row


def login(client, row, password=OLD):
    return client.post("/auth/login", json={"email": row.email, "password": password})


def tokens(client):
    csrf = client.cookies.get("tricoach_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


def auth_session(session, client):
    raw = client.cookies.get("tricoach_session")
    return session.scalar(select(UserAuthSession).where(UserAuthSession.token_hash == hash_secret_token(raw)))


def change(client, **values):
    payload = {"current_password": OLD, "new_password": NEW} | values
    return client.post("/account/password", json=payload, headers=tokens(client))


def state(row, sessions):
    return row.password_hash, row.last_login_at, [(x.id, x.revoked_at, x.created_at, x.expires_at, x.token_hash, x.csrf_token_hash) for x in sessions]


def test_success_preserves_current_and_revokes_only_other_active_sessions(env):
    session, app = env
    a, b = user(session, "a"), user(session, "b")
    current, second, third, b_client = [TestClient(app) for _ in range(4)]
    for client, row in ((current, a), (second, a), (third, a), (b_client, b)):
        assert login(client, row).status_code == 200
    current_session, active2, active3, b_session = [auth_session(session, x) for x in (current, second, third, b_client)]
    now = utc_now()
    expired = UserAuthSession(user_id=a.id, token_hash="e"*64, csrf_token_hash="f"*64, created_at=now-timedelta(days=3), expires_at=now-timedelta(days=2))
    revoked = UserAuthSession(user_id=a.id, token_hash="a"*64, csrf_token_hash="b"*64, created_at=now-timedelta(days=2), expires_at=now+timedelta(days=1), revoked_at=now-timedelta(days=1))
    session.add_all([expired, revoked]); session.commit(); session.refresh(a)
    old_hash, last_login = a.password_hash, a.last_login_at
    current_values = current_session.created_at, current_session.expires_at, current_session.token_hash, current_session.csrf_token_hash
    b_before, revoked_before = state(b, [b_session]), revoked.revoked_at
    response = change(current)
    assert response.status_code == 204 and response.content == b""
    session.refresh(a)
    for item in (current_session, active2, active3, expired, revoked, b_session): session.refresh(item)
    assert a.password_hash != old_hash and verify_password(NEW, a.password_hash) and not verify_password(OLD, a.password_hash)
    assert a.last_login_at == last_login
    assert current_session.revoked_at is None
    assert (current_session.created_at, current_session.expires_at, current_session.token_hash, current_session.csrf_token_hash) == current_values
    assert active2.revoked_at and active3.revoked_at
    assert expired.revoked_at is None and revoked.revoked_at == revoked_before
    assert state(b, [b_session]) == b_before
    assert current.get("/auth/me").status_code == current.get("/account").status_code == 200
    assert second.get("/auth/me").status_code == 401
    assert login(TestClient(app), a, OLD).status_code == 401
    assert login(TestClient(app), a, NEW).status_code == 200


@pytest.mark.parametrize("payload,code", [
    ({"current_password": "incorrect password"}, 400),
    ({"new_password": "short"}, 422),
    ({"new_password": "x"*1025}, 422),
    ({"new_password": OLD}, 400),
    ({"email": "attacker@example.test"}, 422),
    ({"user_id": str(uuid4())}, 422),
    ({"session_id": str(uuid4())}, 422),
    ({"session_token": "attacker"}, 422),
    ({"revoke_other_sessions": False}, 422),
])
def test_invalid_requests_have_zero_effects(env, payload, code):
    session, app = env
    row = user(session, uuid4().hex)
    current, other = TestClient(app), TestClient(app)
    assert login(current, row).status_code == login(other, row).status_code == 200
    sessions = list(session.scalars(select(UserAuthSession).where(UserAuthSession.user_id == row.id)))
    session.refresh(row); before = state(row, sessions)
    response = change(current, **payload)
    assert response.status_code == code
    session.refresh(row)
    for item in sessions: session.refresh(item)
    assert state(row, sessions) == before


def test_authentication_csrf_and_origin(env):
    session, app = env
    row = user(session, "http")
    assert TestClient(app).post("/account/password", json={"current_password": OLD, "new_password": NEW}).status_code == 401
    client = TestClient(app); assert login(client, row).status_code == 200
    body = {"current_password": OLD, "new_password": NEW}
    assert client.post("/account/password", json=body).status_code == 403
    bad = client.post("/account/password", json=body, headers=tokens(client) | {"Origin": "https://bad.test"})
    assert bad.status_code == 403 and bad.json()["detail"]["code"] == "origin_validation_failed"
    assert client.post("/account/password", json=body, headers=tokens(client) | {"Origin": "http://127.0.0.1:5173"}).status_code == 204


def test_no_origin_with_csrf_and_no_athlete_succeeds(env):
    session, app = env
    row = user(session, "no-athlete"); client = TestClient(app); assert login(client, row).status_code == 200
    assert change(client).status_code == 204


@pytest.mark.parametrize("account_state", ["disabled", "pending_deletion", "deleted"])
def test_unusable_account_is_rejected(env, account_state):
    session, app = env
    row = user(session, account_state); client = TestClient(app); assert login(client, row).status_code == 200
    if account_state == "deleted": row.deleted_at = utc_now()
    else: row.status = account_state
    session.commit()
    assert change(client).status_code == 401


def test_missing_password_hash_fails_safely(env):
    session, app = env
    row = user(session, "no-hash"); client = TestClient(app); assert login(client, row).status_code == 200
    row.password_hash = None; session.commit()
    response = change(client)
    assert response.status_code == 400 and response.json()["detail"]["code"] == "current_password_invalid"


def test_commit_failure_rolls_back_everything(env, monkeypatch):
    session, app = env
    row = user(session, "rollback"); current, other = TestClient(app), TestClient(app)
    assert login(current, row).status_code == login(other, row).status_code == 200
    sessions = list(session.scalars(select(UserAuthSession).where(UserAuthSession.user_id == row.id)))
    session.refresh(row); before = state(row, sessions)
    monkeypatch.setattr(session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
    with pytest.raises(RuntimeError, match="commit failed"): change(current)
    session.refresh(row)
    for item in sessions: session.refresh(item)
    assert state(row, sessions) == before


def test_openapi_has_only_password_fields(env):
    _, app = env
    document = app.openapi()
    assert "post" in document["paths"]["/account/password"]
    schema = document["components"]["schemas"]["PasswordChangeRequest"]
    assert set(schema["properties"]) == set(schema["required"]) == {"current_password", "new_password"}
