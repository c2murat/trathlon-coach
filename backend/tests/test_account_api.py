from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings, get_settings
from app.db.base import Base, utc_now
from app.db.models import User
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import hash_password


PASSWORD = "a secure test password"
PUBLIC_FIELDS = {"id", "email", "display_name", "created_at", "last_login_at"}
SENSITIVE_FIELDS = {
    "password", "password_hash", "normalized_email", "auth_subject", "token",
    "session", "csrf", "secret", "oauth", "status", "deleted_at", "timezone",
}


@pytest.fixture
def account_env():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    settings = Settings(auth_mode="session", environment="test")
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: (yield session)
    application.dependency_overrides[get_settings] = lambda: settings
    yield session, settings, application
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_user(session: Session, suffix: str, *, display_name: str | None = "Ana") -> User:
    user = User(
        email=f"{suffix}@example.test",
        normalized_email=f"{suffix}@example.test",
        auth_subject=f"subject-{suffix}",
        password_hash=hash_password(PASSWORD),
        display_name=display_name,
        last_login_at=utc_now() - timedelta(days=1),
    )
    session.add(user)
    session.commit()
    return user


def login(client: TestClient, email: str) -> None:
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200


def csrf(client: TestClient) -> str:
    token = client.cookies.get("tricoach_csrf")
    assert token
    return token


def test_get_returns_only_the_authenticated_account_without_an_athlete(account_env):
    session, _, application = account_env
    user = add_user(session, "owner", display_name="Ana Cuenta")
    client = TestClient(application)
    login(client, user.email)

    response = client.get("/account")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "email": user.email,
        "display_name": "Ana Cuenta",
        "created_at": user.created_at.isoformat().replace("+00:00", "Z"),
        "last_login_at": user.last_login_at.isoformat().replace("+00:00", "Z"),
    }
    assert set(response.json()) == PUBLIC_FIELDS
    assert not SENSITIVE_FIELDS.intersection(response.json())
    assert client.get("/account", headers={"Origin": "https://untrusted.test"}).status_code == 200


def test_get_requires_authentication(account_env):
    _, _, application = account_env
    response = TestClient(application).get("/account")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


def test_patch_requires_authentication(account_env):
    _, _, application = account_env
    response = TestClient(application).patch(
        "/account", json={"display_name": "Unauthorized"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"


@pytest.mark.parametrize("state", ["disabled", "pending_deletion", "deleted"])
def test_invalid_account_state_cannot_read_or_update(account_env, state: str):
    session, _, application = account_env
    user = add_user(session, state)
    client = TestClient(application)
    login(client, user.email)
    if state == "deleted":
        user.deleted_at = utc_now()
    else:
        user.status = state
    session.commit()
    headers = {"X-CSRF-Token": csrf(client)}
    assert client.get("/account").status_code == 401
    assert client.patch("/account", json={"display_name": "Blocked"}, headers=headers).status_code == 401


def test_each_session_reads_its_own_user_and_query_cannot_select_another(account_env):
    session, _, application = account_env
    first = add_user(session, "first", display_name="Primera")
    second = add_user(session, "second", display_name="Segunda")
    first_client, second_client = TestClient(application), TestClient(application)
    login(first_client, first.email)
    login(second_client, second.email)

    first_body = first_client.get(f"/account?user_id={second.id}").json()
    second_body = second_client.get(f"/account?user_id={first.id}").json()

    assert first_body["id"] == str(first.id) and first_body["email"] == first.email
    assert second_body["id"] == str(second.id) and second_body["email"] == second.email
    assert first_client.get(f"/account/{second.id}").status_code == 404


def test_patch_normalizes_and_persists_only_display_name(account_env):
    session, _, application = account_env
    user = add_user(session, "owner")
    original = {
        "email": user.email,
        "password_hash": user.password_hash,
        "status": user.status,
        "last_login_at": user.last_login_at,
    }
    client = TestClient(application)
    login(client, user.email)
    original["last_login_at"] = user.last_login_at

    response = client.patch(
        "/account",
        json={"display_name": "   Carlos   Murat   "},
        headers={"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": csrf(client)},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Carlos Murat"
    assert set(response.json()) == PUBLIC_FIELDS
    session.refresh(user)
    assert user.display_name == "Carlos Murat"
    assert user.email == original["email"]
    assert user.password_hash == original["password_hash"]
    assert user.status == original["status"]
    assert user.last_login_at == original["last_login_at"]


@pytest.mark.parametrize("value", [None, "", "   \t  "])
def test_patch_can_clear_nullable_display_name(account_env, value):
    session, _, application = account_env
    user = add_user(session, f"clear-{uuid4().hex}")
    client = TestClient(application)
    login(client, user.email)
    response = client.patch(
        "/account", json={"display_name": value}, headers={"X-CSRF-Token": csrf(client)}
    )
    assert response.status_code == 200
    assert response.json()["display_name"] is None
    session.refresh(user)
    assert user.display_name is None


@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": "Carlos", "status": "disabled"},
        {"display_name": "Carlos", "email": "attacker@example.test"},
        {"password_hash": "fake"},
        {"id": str(uuid4())},
        {"display_name": "Carlos", "athlete_id": str(uuid4())},
        {"display_name": "Carlos", "arbitrary": True},
        {},
    ],
)
def test_mass_assignment_and_unknown_fields_are_rejected_atomically(account_env, payload):
    session, _, application = account_env
    user = add_user(session, f"mass-{uuid4().hex}", display_name="Original")
    original = (user.email, user.password_hash, user.status, user.display_name)
    client = TestClient(application)
    login(client, user.email)

    response = client.patch(
        "/account", json=payload, headers={"X-CSRF-Token": csrf(client)}
    )

    assert response.status_code == 422
    session.refresh(user)
    assert (user.email, user.password_hash, user.status, user.display_name) == original


def test_display_name_longer_than_200_after_normalization_is_rejected(account_env):
    session, _, application = account_env
    user = add_user(session, "long-name", display_name="Original")
    client = TestClient(application)
    login(client, user.email)
    response = client.patch(
        "/account", json={"display_name": "x" * 201}, headers={"X-CSRF-Token": csrf(client)}
    )
    assert response.status_code == 422
    session.refresh(user)
    assert user.display_name == "Original"


def test_patch_requires_csrf_and_validates_origin(account_env):
    session, _, application = account_env
    user = add_user(session, "http-security")
    client = TestClient(application)
    login(client, user.email)
    token = csrf(client)

    assert client.patch("/account", json={"display_name": "No CSRF"}).status_code == 403
    foreign = client.patch(
        "/account",
        json={"display_name": "Wrong origin"},
        headers={"Origin": "https://untrusted.test", "X-CSRF-Token": token},
    )
    assert foreign.status_code == 403
    assert foreign.json()["detail"]["code"] == "origin_validation_failed"
    allowed = client.patch(
        "/account",
        json={"display_name": "Allowed"},
        headers={"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": token},
    )
    assert allowed.status_code == 200


def test_user_a_patch_never_modifies_user_b(account_env):
    session, _, application = account_env
    first = add_user(session, "patch-a", display_name="A")
    second = add_user(session, "patch-b", display_name="B")
    client = TestClient(application)
    login(client, first.email)
    response = client.patch(
        f"/account?user_id={second.id}",
        json={"display_name": "A updated"},
        headers={"X-CSRF-Token": csrf(client)},
    )
    assert response.status_code == 200
    session.refresh(first)
    session.refresh(second)
    assert first.display_name == "A updated"
    assert second.display_name == "B"


def test_openapi_account_contract_has_no_sensitive_fields(account_env):
    _, _, application = account_env
    document = application.openapi()
    assert set(document["paths"]["/account"]) >= {"get", "patch"}
    response_properties = set(document["components"]["schemas"]["AccountResponse"]["properties"])
    update_properties = set(document["components"]["schemas"]["AccountUpdateRequest"]["properties"])
    assert response_properties == PUBLIC_FIELDS
    assert update_properties == {"display_name"}
    assert not SENSITIVE_FIELDS.intersection(response_properties | update_properties)