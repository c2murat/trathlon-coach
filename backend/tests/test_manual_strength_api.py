from datetime import datetime, timedelta, timezone
from uuid import uuid4
import warnings

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.routes.manual_strength import router
from app.db.base import Base
from app.db.models import AthleteProfile, ManualStrengthSession, ManualStrengthTrainingLoad, User, UserAthleteMembership
from app.db.session import get_db_session
from app.main import create_app

START = "2026-08-02T18:00:00+02:00"


@pytest.fixture
def api_context():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_connection, connection_record):
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    user_ids = [uuid4(), uuid4()]
    athlete_ids = []
    with factory() as session:
        for number, user_id in enumerate(user_ids):
            user = User(id=user_id, email=f"api{number}@example.com", normalized_email=f"api{number}@example.com", auth_subject=f"api-{number}")
            athlete = AthleteProfile(display_name="Test athlete", timezone="Europe/Madrid", unit_system="metric")
            session.add(athlete)
            session.flush()
            session.add(
                UserAthleteMembership(
                    user=user,
                    athlete_profile=athlete,
                    role="owner",
                    is_active=True,
                    is_default=True,
                )
            )
            athlete_ids.append(athlete.id)
        session.commit()

    active = {"user_id": user_ids[0]}
    application = FastAPI()
    application.include_router(router)

    def database_dependency():
        with factory() as session:
            yield session

    def user_dependency():
        return AuthenticatedUser(active["user_id"])

    application.dependency_overrides[get_db_session] = database_dependency
    application.dependency_overrides[get_current_user] = user_dependency
    with TestClient(application) as client:
        yield client, factory, active, user_ids, athlete_ids
    engine.dispose()


def payload(**overrides):
    data = {"started_at": START, "timezone_name": "Europe/Madrid", "duration_minutes": 45, "body_regions": ["back", "shoulders", "arms"], "perceived_exertion": 7, "notes": "  Trabajo general  "}
    data.update(overrides)
    return data


def create(client, **overrides):
    return client.post("/manual-strength-sessions", json=payload(**overrides))


@pytest.mark.parametrize(
    ("rpe", "value", "method", "warnings"),
    [(7, 52.5, "strength_rpe", []), (None, 37.5, "strength_duration", ["missing_perceived_exertion"])],
)
def test_post_creates_session_and_load(api_context, rpe, value, method, warnings):
    client, _, _, _, _ = api_context
    response = create(client, perceived_exertion=rpe)
    assert response.status_code == 201
    body = response.json()
    assert body["training_load"]["load_value"] == value
    assert body["training_load"]["method"] == method
    assert body["training_load"]["warnings"] == warnings
    assert body["training_load"]["algorithm_version"] == "0.7e.1"
    assert body["body_regions"] == ["back", "shoulders", "arms"]
    assert body["notes"] == "Trabajo general"
    assert "athlete_id" not in body


@pytest.mark.parametrize(
    "overrides",
    [
        {"body_regions": []},
        {"body_regions": ["back", "back"]},
        {"body_regions": ["full_body", "back"]},
        {"body_regions": ["unknown"]},
        {"duration_minutes": 0},
        {"duration_minutes": 1441},
        {"duration_minutes": True},
        {"duration_minutes": 45.0},
        {"perceived_exertion": 0},
        {"perceived_exertion": 11},
        {"perceived_exertion": True},
        {"perceived_exertion": 7.0},
        {"started_at": "2026-08-02T18:00:00"},
        {"timezone_name": "Unknown/Zone"},
        {"notes": "x" * 2001},
    ],
)
def test_post_rejects_invalid_input(api_context, overrides):
    client, factory, _, _, _ = api_context
    response = create(client, **overrides)
    assert response.status_code == 422
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ManualStrengthSession)) == 0


def test_full_body_and_canonical_order(api_context):
    client, _, _, _, _ = api_context
    assert create(client, body_regions=["full_body"]).status_code == 201
    response = create(client, body_regions=["glutes", "chest"])
    assert response.json()["body_regions"] == ["chest", "glutes"]


def test_list_is_owned_ordered_and_filtered(api_context):
    client, _, active, user_ids, _ = api_context
    old = create(client, started_at="2026-08-01T10:00:00+02:00").json()
    new = create(client, started_at="2026-08-03T10:00:00+02:00").json()
    active["user_id"] = user_ids[1]
    create(client, started_at="2026-08-04T10:00:00+02:00")
    active["user_id"] = user_ids[0]
    listed = client.get("/manual-strength-sessions").json()
    assert [item["id"] for item in listed] == [new["id"], old["id"]]
    assert [item["id"] for item in client.get("/manual-strength-sessions", params={"start_at": "2026-08-02T00:00:00+02:00"}).json()] == [new["id"]]
    assert [item["id"] for item in client.get("/manual-strength-sessions", params={"end_at": "2026-08-02T00:00:00+02:00"}).json()] == [old["id"]]


@pytest.mark.parametrize("params", [{"start_at": "2026-08-02T00:00:00"}, {"end_at": "2026-08-02T00:00:00"}, {"start_at": "2026-08-03T00:00:00Z", "end_at": "2026-08-02T00:00:00Z"}])
def test_list_rejects_invalid_filters(api_context, params):
    client, _, _, _, _ = api_context
    assert client.get("/manual-strength-sessions", params=params).status_code == 422


def test_get_is_isolated(api_context):
    client, _, active, user_ids, _ = api_context
    created = create(client).json()
    assert client.get(f"/manual-strength-sessions/{created['id']}").status_code == 200
    active["user_id"] = user_ids[1]
    response = client.get(f"/manual-strength-sessions/{created['id']}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "manual_strength_session_not_found"


def test_patch_partial_null_and_recalculation(api_context):
    client, _, _, _, _ = api_context
    created = create(client).json()
    response = client.patch(f"/manual-strength-sessions/{created['id']}", json={"duration_minutes": 30})
    assert response.status_code == 200
    assert response.json()["training_load"]["load_value"] == 35
    assert response.json()["notes"] == "Trabajo general"
    response = client.patch(f"/manual-strength-sessions/{created['id']}", json={"perceived_exertion": None, "notes": None})
    assert response.json()["perceived_exertion"] is None
    assert response.json()["notes"] is None
    assert response.json()["training_load"]["load_value"] == 25


def test_patch_empty_invalid_atomic_and_owned(api_context):
    client, _, active, user_ids, _ = api_context
    created = create(client).json()
    url = f"/manual-strength-sessions/{created['id']}"
    assert client.patch(url, json={}).status_code == 422
    assert client.patch(url, json={"duration_minutes": 0}).status_code == 422
    assert client.get(url).json()["duration_minutes"] == 45
    active["user_id"] = user_ids[1]
    assert client.patch(url, json={"duration_minutes": 30}).status_code == 404


def test_delete_is_owned_and_cascades(api_context):
    client, factory, active, user_ids, _ = api_context
    created = create(client).json()
    url = f"/manual-strength-sessions/{created['id']}"
    active["user_id"] = user_ids[1]
    assert client.delete(url).status_code == 404
    active["user_id"] = user_ids[0]
    response = client.delete(url)
    assert response.status_code == 204
    assert response.content == b""
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ManualStrengthSession)) == 0
        assert session.scalar(select(func.count()).select_from(ManualStrengthTrainingLoad)) == 0


def test_recalculate_is_idempotent_and_owned(api_context):
    client, factory, active, user_ids, _ = api_context
    created = create(client).json()
    url = f"/manual-strength-sessions/{created['id']}/training-load/recalculate"
    first = client.post(url)
    second = client.post(url)
    assert first.status_code == second.status_code == 200
    assert first.json()["load_value"] == second.json()["load_value"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(ManualStrengthTrainingLoad)) == 1
    active["user_id"] = user_ids[1]
    assert client.post(url).status_code == 404


def test_openapi_registers_all_operations_and_no_athlete_body_field(api_context):
    client, _, _, _, _ = api_context
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/manual-strength-sessions" in paths
    assert set(paths["/manual-strength-sessions"]) >= {"get", "post"}
    assert set(paths["/manual-strength-sessions/{session_id}"]) >= {"get", "patch", "delete"}
    assert "/manual-strength-sessions/{session_id}/training-load/recalculate" in paths
    create_schema = schema["components"]["schemas"]["ManualStrengthSessionCreateRequest"]
    assert "athlete_id" not in create_schema["properties"]


def test_no_new_sawarnings_and_existing_health_route():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", SAWarning)
        application = create_app()
    assert not [item for item in captured if issubclass(item.category, SAWarning)]
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
