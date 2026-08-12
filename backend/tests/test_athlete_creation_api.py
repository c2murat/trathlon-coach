from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.athlete_permissions import capabilities_for_role
from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.models import AthleteProfile, CompletedActivity, User, UserAthleteMembership
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import hash_password


PASSWORD = "a secure test password"
VALID_PAYLOAD = {
    "display_name": "Atleta B",
    "timezone": "Europe/Madrid",
    "unit_system": "metric",
}


@pytest.fixture
def athlete_env():
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


def add_user(session: Session, suffix: str) -> User:
    user = User(
        email=f"{suffix}@example.test",
        normalized_email=f"{suffix}@example.test",
        auth_subject=f"subject-{suffix}",
        password_hash=hash_password(PASSWORD),
        display_name=f"Account {suffix}",
    )
    session.add(user)
    session.commit()
    return user


def add_athlete(
    session: Session,
    user: User,
    name: str,
    *,
    role: str = "owner",
    default: bool = False,
    active: bool = True,
    deleted: bool = False,
) -> AthleteProfile:
    athlete = AthleteProfile(
        display_name=name,
        timezone="UTC",
        unit_system="metric",
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add_all([
        athlete,
        UserAthleteMembership(
            user_id=user.id,
            athlete_profile=athlete,
            role=role,
            is_active=active,
            is_default=default,
        ),
    ])
    session.commit()
    return athlete


def authenticated_client(application, user: User) -> TestClient:
    client = TestClient(application)
    response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200
    return client


def mutation_headers(client: TestClient, **extra: str) -> dict[str, str]:
    token = client.cookies.get("tricoach_csrf")
    assert token
    return {"X-CSRF-Token": token, **extra}


def post_athlete(client: TestClient, payload=None, headers=None):
    return client.post(
        "/athletes",
        json=VALID_PAYLOAD if payload is None else payload,
        headers=mutation_headers(client) if headers is None else headers,
    )


def test_user_without_athletes_creates_owner_default_and_context(athlete_env):
    session, _, application = athlete_env
    user = add_user(session, "empty")
    account_before = (user.display_name, user.email, user.password_hash, user.last_login_at)
    client = authenticated_client(application, user)
    account_before = (user.display_name, user.email, user.password_hash, user.last_login_at)

    response = post_athlete(
        client,
        {"display_name": "   Atleta    B   ", "timezone": "Europe/Madrid", "unit_system": "metric"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Atleta B"
    assert body["role"] == "owner" and body["is_default"] is True
    assert body["capabilities"] == [item.value for item in capabilities_for_role("owner")]
    membership = session.scalar(select(UserAthleteMembership))
    assert membership.user_id == user.id
    assert membership.athlete_profile_id == UUID(body["id"])
    assert membership.role == "owner" and membership.is_active and membership.is_default
    context = client.get("/session/context").json()
    assert len(context["athletes"]) == 1
    assert context["athletes"][0]["athlete_id"] == body["id"]
    assert context["athletes"][0]["label"] == "Atleta B"
    session.refresh(user)
    assert (user.display_name, user.email, user.password_hash, user.last_login_at) == account_before


def test_second_athlete_preserves_a_and_starts_empty(athlete_env):
    session, _, application = athlete_env
    user = add_user(session, "second")
    athlete_a = add_athlete(session, user, "Athlete A", default=True)
    activity = CompletedActivity(
        athlete_id=athlete_a.id,
        source_summary="manual",
        sport="running",
        name="A run",
        start_at=datetime.now(timezone.utc),
        timezone="UTC",
        elapsed_time_s=600,
    )
    session.add(activity)
    session.commit()
    client = authenticated_client(application, user)

    response = post_athlete(client)
    assert response.status_code == 201 and response.json()["is_default"] is False
    athlete_b_id = response.json()["id"]
    memberships = {item.athlete_profile_id: (item.role, item.is_default) for item in session.scalars(select(UserAthleteMembership).where(UserAthleteMembership.user_id == user.id))}
    assert memberships == {athlete_a.id: ("owner", True), UUID(athlete_b_id): ("owner", False)}
    empty = client.get("/activities", headers={"X-TriCoach-Athlete-Id": athlete_b_id}).json()
    original = client.get("/activities", headers={"X-TriCoach-Athlete-Id": str(athlete_a.id)}).json()
    assert empty["total"] == 0 and empty["items"] == []
    assert original["total"] == 1 and original["items"][0]["id"] == str(activity.id)
    context = client.get("/session/context").json()
    assert {(item["label"], item["role"], item["is_default"]) for item in context["athletes"]} == {
        ("Athlete A", "owner", True), ("Atleta B", "owner", False)
    }


def test_multiple_existing_roles_are_untouched(athlete_env):
    session, _, application = athlete_env
    user = add_user(session, "many")
    existing = [
        add_athlete(session, user, "A", role="owner", default=True),
        add_athlete(session, user, "B", role="owner"),
        add_athlete(session, user, "C", role="coach"),
        add_athlete(session, user, "D", role="viewer"),
    ]
    before = {row.id: (row.role, row.is_default) for row in session.scalars(select(UserAthleteMembership).where(UserAthleteMembership.user_id == user.id))}
    response = post_athlete(authenticated_client(application, user))
    assert response.status_code == 201 and response.json()["role"] == "owner" and not response.json()["is_default"]
    after = {row.id: (row.role, row.is_default) for row in session.scalars(select(UserAthleteMembership).where(UserAthleteMembership.user_id == user.id))}
    assert all(after[membership_id] == values for membership_id, values in before.items())
    assert len(after) == 5
    persisted_ids = set(session.scalars(select(AthleteProfile.id).where(AthleteProfile.id.in_([item.id for item in existing]))))
    assert persisted_ids == {athlete.id for athlete in existing}


def test_viewer_can_create_owned_athlete(athlete_env):
    session, _, application = athlete_env
    owner = add_user(session, "foreign-owner")
    viewer = add_user(session, "viewer")
    add_athlete(session, owner, "Foreign", default=True)
    viewed = add_athlete(session, viewer, "Viewed", role="viewer", default=True)
    response = post_athlete(authenticated_client(application, viewer), headers=None)
    assert response.status_code == 201 and response.json()["role"] == "owner"
    assert response.json()["id"] != str(viewed.id)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": "", "timezone": "UTC", "unit_system": "metric"},
        {"display_name": "   ", "timezone": "UTC", "unit_system": "metric"},
        {"display_name": "x" * 201, "timezone": "UTC", "unit_system": "metric"},
        {"display_name": "Valid", "timezone": "", "unit_system": "metric"},
        {"display_name": "Valid", "timezone": "Madrid", "unit_system": "metric"},
        {"display_name": "Valid", "timezone": "x" * 65, "unit_system": "metric"},
        {"display_name": "Valid", "timezone": "UTC", "unit_system": "other"},
        {"display_name": "Valid", "timezone": "UTC", "unit_system": "metric", "user_id": str(uuid4())},
        {"display_name": "Valid", "timezone": "UTC", "unit_system": "metric", "owner_user_id": str(uuid4())},
        {"display_name": "Valid", "timezone": "UTC", "unit_system": "metric", "athlete_id": str(uuid4())},
        {"display_name": "Valid", "timezone": "UTC", "unit_system": "metric", "role": "viewer"},
        {"display_name": "Valid", "timezone": "UTC", "unit_system": "metric", "is_default": True},
        {"display_name": "Valid", "timezone": "UTC", "unit_system": "metric", "unknown": True},
    ],
)
def test_invalid_payloads_are_rejected_without_writes(athlete_env, payload):
    session, _, application = athlete_env
    user = add_user(session, uuid4().hex)
    response = post_athlete(authenticated_client(application, user), payload)
    assert response.status_code == 422
    assert session.scalar(select(func.count()).select_from(AthleteProfile)) == 0
    assert session.scalar(select(func.count()).select_from(UserAthleteMembership)) == 0


@pytest.mark.parametrize("timezone_name,unit_system", [("UTC", "metric"), ("Europe/Madrid", "imperial")])
def test_boundary_values_and_units(athlete_env, timezone_name, unit_system):
    session, _, application = athlete_env
    user = add_user(session, uuid4().hex)
    response = post_athlete(authenticated_client(application, user), {"display_name": "x" * 200, "timezone": timezone_name, "unit_system": unit_system})
    assert response.status_code == 201
    assert response.json()["timezone"] == timezone_name and response.json()["unit_system"] == unit_system


def test_authentication_csrf_origin_and_foreign_header(athlete_env):
    session, _, application = athlete_env
    user_a = add_user(session, "security-a")
    user_b = add_user(session, "security-b")
    foreign = add_athlete(session, user_b, "Foreign", default=True)
    assert TestClient(application).post("/athletes", json=VALID_PAYLOAD).status_code == 401
    client = authenticated_client(application, user_a)
    assert client.post("/athletes", json=VALID_PAYLOAD).status_code == 403
    bad_csrf = client.post("/athletes", json=VALID_PAYLOAD, headers={"X-CSRF-Token": "wrong"})
    assert bad_csrf.status_code == 403 and bad_csrf.json()["detail"]["code"] == "csrf_validation_failed"
    bad_origin = client.post("/athletes", json=VALID_PAYLOAD, headers=mutation_headers(client, Origin="https://evil.test"))
    assert bad_origin.status_code == 403 and bad_origin.json()["detail"]["code"] == "origin_validation_failed"
    response = client.post("/athletes", json=VALID_PAYLOAD, headers=mutation_headers(client, **{"X-TriCoach-Athlete-Id": str(foreign.id)}))
    assert response.status_code == 201
    membership = session.scalar(select(UserAthleteMembership).where(UserAthleteMembership.athlete_profile_id == UUID(response.json()["id"])))
    assert membership.user_id == user_a.id


def test_invalid_default_configuration_returns_409_without_repair(athlete_env):
    session, _, application = athlete_env
    user = add_user(session, "invalid-default")
    existing = add_athlete(session, user, "A", default=False)
    response = post_athlete(authenticated_client(application, user))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "athlete_default_configuration_invalid"
    assert session.scalar(select(func.count()).select_from(AthleteProfile)) == 1
    membership = session.scalar(select(UserAthleteMembership).where(UserAthleteMembership.athlete_profile_id == existing.id))
    assert membership.is_default is False


def test_multiple_defaults_corruption_returns_409(athlete_env):
    session, _, application = athlete_env
    user = add_user(session, "multiple-defaults")
    session.execute(text("DROP INDEX uq_user_athlete_memberships_active_default_user"))
    add_athlete(session, user, "A", default=True)
    add_athlete(session, user, "B", default=True)
    response = post_athlete(authenticated_client(application, user))
    assert response.status_code == 409
    assert session.scalar(select(func.count()).select_from(AthleteProfile)) == 2

def test_active_membership_to_deleted_athlete_returns_409(athlete_env):
    session, _, application = athlete_env
    user = add_user(session, "deleted-athlete")
    add_athlete(session, user, "Deleted", default=True, deleted=True)
    response = post_athlete(authenticated_client(application, user))
    assert response.status_code == 409
    assert session.scalar(select(func.count()).select_from(AthleteProfile)) == 1


def test_duplicate_names_are_allowed(athlete_env):
    session, _, application = athlete_env
    user = add_user(session, "duplicates")
    client = authenticated_client(application, user)
    first = post_athlete(client, {**VALID_PAYLOAD, "display_name": "Carlos"})
    second = post_athlete(client, {**VALID_PAYLOAD, "display_name": "Carlos"})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert session.scalar(select(func.count()).select_from(AthleteProfile)) == 2


def test_membership_failure_rolls_back_athlete(athlete_env, monkeypatch):
    session, _, application = athlete_env
    user = add_user(session, "rollback")
    client = authenticated_client(application, user)
    original_flush = session.flush

    def fail_membership_flush(*args, **kwargs):
        if any(isinstance(item, UserAthleteMembership) for item in session.new):
            raise RuntimeError("injected membership failure")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", fail_membership_flush)
    with pytest.raises(RuntimeError, match="injected membership failure"):
        post_athlete(client)
    monkeypatch.setattr(session, "flush", original_flush)
    assert session.scalar(select(func.count()).select_from(AthleteProfile)) == 0
    assert session.scalar(select(func.count()).select_from(UserAthleteMembership)) == 0


def test_cross_user_cannot_access_new_athlete(athlete_env):
    session, _, application = athlete_env
    creator = add_user(session, "creator")
    stranger = add_user(session, "stranger")
    created = post_athlete(authenticated_client(application, creator)).json()["id"]
    response = authenticated_client(application, stranger).get("/activities", headers={"X-TriCoach-Athlete-Id": created})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "athlete_not_authorized"
