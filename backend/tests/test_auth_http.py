from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.core.settings import Settings, get_settings
from app.db.base import Base, utc_now
from app.db.models import AthleteProfile, User, UserAthleteMembership, UserAuthSession
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import hash_password
from app.security.tokens import hash_secret_token


PASSWORD = "a secure test password"


@pytest.fixture
def http_auth():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    settings = Settings(auth_mode="session", environment="test", session_cookie_secure=False)
    application = create_app()

    def database_override():
        yield session

    application.dependency_overrides[get_db_session] = database_override
    application.dependency_overrides[get_settings] = lambda: settings

    @application.get("/test/protected")
    def protected_get(user: AuthenticatedUser = Depends(get_current_user)):
        return {"user_id": str(user.id)}

    @application.post("/test/protected")
    def protected_post(user: AuthenticatedUser = Depends(get_current_user)):
        return {"user_id": str(user.id)}

    @application.post("/test/external")
    def external_post():
        return {"ok": True}

    yield session, settings, application
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_user(session: Session, suffix="user", *, password_hash=True, status="active", deleted=False) -> User:
    user = User(
        email=f"{suffix}@example.test",
        normalized_email=f"{suffix}@example.test",
        auth_subject=f"subject-{suffix}",
        password_hash=hash_password(PASSWORD) if password_hash else None,
        status=status,
        deleted_at=utc_now() if deleted else None,
        display_name="Ana Triatleta",
    )
    session.add(user)
    session.commit()
    return user


def login(client: TestClient, email="user@example.test", password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def csrf(client: TestClient) -> str:
    value = client.cookies.get("tricoach_csrf")
    assert value
    return value


def test_login_normalizes_email_creates_session_and_safe_cookies(http_auth) -> None:
    session, _, application = http_auth
    user = add_user(session)
    client = TestClient(application)
    response = login(client, "  USER@EXAMPLE.TEST  ")
    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "email": user.email, "display_name": "Ana Triatleta", "authentication_mode": "session"}
    assert "password_hash" not in response.text and "token" not in response.text
    stored = session.scalar(select(UserAuthSession))
    assert stored and stored.user_id == user.id
    raw_session = client.cookies.get("tricoach_session")
    raw_csrf = csrf(client)
    assert stored.token_hash == hash_secret_token(raw_session)
    assert stored.csrf_token_hash == hash_secret_token(raw_csrf)
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("tricoach_session="))
    csrf_cookie = next(value for value in cookies if value.startswith("tricoach_csrf="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    assert "HttpOnly" not in csrf_cookie and "SameSite=lax" in csrf_cookie
    assert "Max-Age=1209600" in session_cookie and "expires=" in session_cookie.lower()
    assert user.last_login_at is not None


def test_secure_cookie_setting_is_applied(http_auth) -> None:
    session, settings, application = http_auth
    settings.session_cookie_secure = True
    add_user(session)
    response = TestClient(application, base_url="https://testserver").post("/auth/login", json={"email": "user@example.test", "password": PASSWORD})
    assert response.status_code == 200
    assert all("Secure" in value for value in response.headers.get_list("set-cookie"))


@pytest.mark.parametrize("case", ["wrong", "missing", "no_hash", "disabled", "deleted"])
def test_all_invalid_credentials_share_one_public_error(http_auth, case: str) -> None:
    session, _, application = http_auth
    if case != "missing":
        add_user(session, password_hash=case != "no_hash", status="disabled" if case == "disabled" else "active", deleted=case == "deleted")
    password = "another wrong password" if case == "wrong" else PASSWORD
    response = login(TestClient(application), password=password)
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_credentials"}}
    assert session.scalar(select(func.count()).select_from(UserAuthSession)) == 0


def test_login_is_controlled_outside_session_mode(http_auth) -> None:
    session, settings, application = http_auth
    settings.auth_mode = "development"
    add_user(session)
    response = login(TestClient(application))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "auth_mode_not_session"


def test_me_valid_missing_revoked_and_expired(http_auth) -> None:
    session, _, application = http_auth
    user = add_user(session)
    client = TestClient(application)
    assert client.get("/auth/me").status_code == 401
    assert login(client).status_code == 200
    body = client.get("/auth/me").json()
    assert body["id"] == str(user.id) and body["authentication_mode"] == "session"
    assert set(body) == {"id", "email", "display_name", "authentication_mode"}
    stored = session.scalar(select(UserAuthSession))
    stored.revoked_at = utc_now(); session.commit()
    assert client.get("/auth/me").status_code == 401
    stored.revoked_at = None; stored.expires_at = utc_now() - timedelta(seconds=1); session.commit()
    assert client.get("/auth/me").status_code == 401


def test_me_preserves_development_identity(http_auth) -> None:
    session, settings, application = http_auth
    settings.auth_mode = "development"
    user = User(id=UUID("00000000-0000-4000-8000-000000000001"), email="development@example.invalid", normalized_email="development@example.invalid", auth_subject="development", display_name="Desarrollo")
    session.add(user); session.commit()
    response = TestClient(application).get("/auth/me")
    assert response.status_code == 200
    assert response.json()["authentication_mode"] == "development"


def test_csrf_is_central_for_unsafe_authenticated_requests(http_auth) -> None:
    session, _, application = http_auth
    add_user(session)
    client = TestClient(application)
    login(client)
    assert client.get("/test/protected").status_code == 200
    assert client.post("/test/protected").status_code == 403
    assert client.post("/test/protected", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/test/protected", headers={"X-CSRF-Token": csrf(client)}).status_code == 200
    assert client.post("/test/external").status_code == 200


def test_csrf_from_another_session_is_rejected(http_auth) -> None:
    session, _, application = http_auth
    add_user(session, "user")
    add_user(session, "other")
    first, second = TestClient(application), TestClient(application)
    login(first); login(second, "other@example.test")
    assert first.post("/test/protected", headers={"X-CSRF-Token": csrf(second)}).status_code == 403


def test_logout_revokes_deletes_cookies_and_is_idempotent(http_auth) -> None:
    session, _, application = http_auth
    add_user(session)
    client = TestClient(application)
    login(client)
    assert client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    response = client.post("/auth/logout", headers={"X-CSRF-Token": csrf(client)})
    assert response.status_code == 204
    assert session.scalar(select(UserAuthSession)).revoked_at is not None
    assert client.cookies.get("tricoach_session") is None
    assert client.cookies.get("tricoach_csrf") is None
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/logout").status_code == 204


def test_real_login_preserves_multi_athlete_authorization(http_auth) -> None:
    session, _, application = http_auth
    user = add_user(session, "user")
    other = add_user(session, "other")
    owned, foreign = AthleteProfile(user=user), AthleteProfile(user=other)
    session.add_all([owned, foreign]); session.flush()
    session.add(UserAthleteMembership(user=user, athlete_profile=owned, role="owner", is_default=True)); session.commit()
    client = TestClient(application); login(client)
    assert client.get("/activities", headers={"X-TriCoach-Athlete-Id": str(owned.id)}).status_code == 200
    response = client.get("/activities", headers={"X-TriCoach-Athlete-Id": str(foreign.id)})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "athlete_not_authorized"
