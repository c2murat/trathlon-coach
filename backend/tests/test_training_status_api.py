from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock
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
from app.api.v1.routes.training_status import router
from app.application.training_status import (
    TrainingStatusApplication,
    TrainingStatusPersistenceError,
)
from app.db.base import Base
from app.db.models import (
    AthleteDailyTrainingLoad,
    AthleteDailyTrainingStatus,
    AthleteProfile,
    User,
)
from app.db.session import get_db_session
from app.main import create_app


DAY = date(2026, 1, 1)
NOW = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)


class TrackingSession(Session):
    commits = 0
    rollbacks = 0

    def commit(self):
        TrackingSession.commits += 1
        return super().commit()

    def rollback(self):
        TrackingSession.rollbacks += 1
        return super().rollback()


@pytest.fixture
def api_context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        del record
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, class_=TrackingSession, expire_on_commit=False)
    user_ids = [uuid4(), uuid4()]
    athlete_ids = []
    with factory() as session:
        for number, user_id in enumerate(user_ids):
            user = User(
                id=user_id,
                email=f"status-api-{number}@example.com",
                normalized_email=f"status-api-{number}@example.com",
                auth_subject=f"status-api-{number}",
            )
            athlete = AthleteProfile(user=user, timezone="Europe/Madrid", unit_system="metric")
            session.add(athlete)
            session.flush()
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
    TrackingSession.commits = 0
    TrackingSession.rollbacks = 0
    with TestClient(application) as client:
        yield client, factory, active, user_ids, athlete_ids
    engine.dispose()


def params(**overrides):
    values = {
        "start_date": DAY.isoformat(),
        "end_date": DAY.isoformat(),
        "timezone_name": "Europe/Madrid",
        "training_load_algorithm_version": "0.7b.1",
        "manual_strength_algorithm_version": "0.7e.1",
        "training_status_algorithm_version": "0.7f.1",
    }
    values.update(overrides)
    return values


def latest_params(**overrides):
    values = params(**overrides)
    values.pop("start_date")
    values.pop("end_date")
    return values


def add_source(factory, athlete_id, offset, load, **overrides):
    with factory() as session:
        values = dict(
            athlete_profile_id=athlete_id,
            local_date=DAY + timedelta(days=offset),
            timezone_name="Europe/Madrid",
            source_load_algorithm_version="0.7b.1",
            manual_strength_algorithm_version="0.7e.1",
            aggregation_algorithm_version="0.7c.1",
            total_load=Decimal(str(load)),
            endurance_load=Decimal("900"),
            strength_load=Decimal("900"),
            strength_session_count=1,
            activity_count=1,
            loaded_activity_count=1,
            null_load_activity_count=0,
            total_duration_seconds=Decimal("3600"),
            coverage="complete",
            quality="high",
            warnings=[],
            activity_ids=[],
            calculated_at=NOW,
        )
        values.update(overrides)
        row = AthleteDailyTrainingLoad(**values)
        session.add(row)
        session.commit()
        row_id = row.id
    TrackingSession.commits = 0
    return row_id


def add_status(factory, athlete_id, offset=0, **overrides):
    with factory() as session:
        values = dict(
            athlete_profile_id=athlete_id,
            local_date=DAY + timedelta(days=offset),
            timezone_name="Europe/Madrid",
            training_load_algorithm_version="0.7b.1",
            manual_strength_algorithm_version="0.7e.1",
            training_status_algorithm_version="0.7f.1",
            total_load=Decimal("100"),
            fitness=Decimal("20"),
            fatigue=Decimal("30"),
            form=Decimal("-10"),
            history_day_number=offset + 1,
            is_warmup=offset < 84,
            calculated_at=NOW,
        )
        values.update(overrides)
        row = AthleteDailyTrainingStatus(**values)
        session.add(row)
        session.commit()
    TrackingSession.commits = 0
    return row


def test_get_empty_interval_returns_200_without_commit_or_recalculation(api_context, monkeypatch):
    client, _, _, _, _ = api_context
    recalculation = Mock(side_effect=AssertionError("GET must not recalculate"))
    monkeypatch.setattr(TrainingStatusApplication, "recalculate_training_status", recalculation)
    response = client.get("/training-status", params=params())
    assert response.status_code == 200
    assert response.json() == []
    assert TrackingSession.commits == 0
    recalculation.assert_not_called()


def test_get_serializes_all_public_fields_and_negative_form(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_status(factory, athlete_ids[0])
    response = client.get("/training-status", params=params())
    assert response.status_code == 200
    body = response.json()[0]
    assert body == {
        "date": "2026-01-01",
        "timezone_name": "Europe/Madrid",
        "total_load": 100.0,
        "fitness": 20.0,
        "fatigue": 30.0,
        "form": -10.0,
        "history_day_number": 1,
        "is_warmup": True,
        "training_load_algorithm_version": "0.7b.1",
        "manual_strength_algorithm_version": "0.7e.1",
        "training_status_algorithm_version": "0.7f.1",
        "calculated_at": "2026-08-03T10:00:00Z",
    }
    assert "athlete_profile_id" not in body
    assert isinstance(body["fitness"], float)


def test_get_is_ascending_and_interval_is_inclusive(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_status(factory, athlete_ids[0], 2)
    add_status(factory, athlete_ids[0], 0)
    add_status(factory, athlete_ids[0], 1)
    response = client.get(
        "/training-status",
        params=params(start_date="2026-01-02", end_date="2026-01-03"),
    )
    assert [row["date"] for row in response.json()] == ["2026-01-02", "2026-01-03"]


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"start_date": "2026-01-02", "end_date": "2026-01-01"}, "invalid_training_status_range"),
        ({"timezone_name": "Unknown/Zone"}, "invalid_timezone"),
        ({"training_load_algorithm_version": " "}, "invalid_algorithm_version"),
        ({"manual_strength_algorithm_version": " "}, "invalid_algorithm_version"),
        ({"training_status_algorithm_version": " "}, "invalid_algorithm_version"),
    ],
)
def test_get_rejects_invalid_query_values(api_context, overrides, code):
    client, _, _, _, _ = api_context
    response = client.get("/training-status", params=params(**overrides))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_get_isolated_by_athlete_timezone_and_versions(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_status(factory, athlete_ids[1], total_load=1)
    add_status(factory, athlete_ids[0], timezone_name="UTC", total_load=2)
    add_status(factory, athlete_ids[0], training_load_algorithm_version="other", total_load=3)
    add_status(factory, athlete_ids[0], manual_strength_algorithm_version="other", total_load=4)
    add_status(factory, athlete_ids[0], training_status_algorithm_version="other", total_load=5)
    assert client.get("/training-status", params=params()).json() == []


def test_latest_returns_exact_most_recent_status(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_status(factory, athlete_ids[0], 0)
    add_status(factory, athlete_ids[0], 2)
    add_status(factory, athlete_ids[1], 4)
    response = client.get("/training-status/latest", params=latest_params())
    assert response.status_code == 200
    assert response.json()["date"] == "2026-01-03"
    assert TrackingSession.commits == 0


def test_latest_isolated_by_timezone_and_versions(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_status(factory, athlete_ids[0], 3, timezone_name="UTC")
    add_status(factory, athlete_ids[0], 4, training_status_algorithm_version="other")
    response = client.get("/training-status/latest", params=latest_params())
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "training_status_not_found"


def test_latest_does_not_mix_authenticated_athletes(api_context):
    client, factory, active, user_ids, athlete_ids = api_context
    add_status(factory, athlete_ids[0], 0)
    active["user_id"] = user_ids[1]
    assert client.get("/training-status/latest", params=latest_params()).status_code == 404


def test_recalculate_creates_requested_interval_from_aggregated_total(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_source(factory, athlete_ids[0], 0, 70)
    add_source(factory, athlete_ids[0], 2, 30)
    response = client.post(
        "/training-status/recalculate",
        params=params(end_date="2026-01-03"),
    )
    assert response.status_code == 200
    body = response.json()
    assert [row["total_load"] for row in body] == [70.0, 0.0, 30.0]
    assert [row["history_day_number"] for row in body] == [1, 2, 3]
    assert all(row["is_warmup"] for row in body)
    assert TrackingSession.commits == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus)) == 3


def test_recalculate_marks_day_84_and_85_correctly(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_source(factory, athlete_ids[0], 0, 10)
    response = client.post(
        "/training-status/recalculate",
        params=params(end_date=(DAY + timedelta(days=84)).isoformat()),
    )
    body = response.json()
    assert len(body) == 85
    assert body[83]["is_warmup"] is True
    assert body[84]["is_warmup"] is False


def test_recalculate_is_idempotent_without_duplicates_or_drift(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_source(factory, athlete_ids[0], 0, 1)
    request = params(end_date="2026-01-10")
    first = client.post("/training-status/recalculate", params=request).json()
    second = client.post("/training-status/recalculate", params=request).json()
    assert [(row["fitness"], row["fatigue"], row["form"], row["history_day_number"]) for row in first] == [
        (row["fitness"], row["fatigue"], row["form"], row["history_day_number"]) for row in second
    ]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus)) == 10


def test_recalculate_uses_total_load_and_does_not_modify_source(api_context):
    client, factory, _, _, athlete_ids = api_context
    source_id = add_source(factory, athlete_ids[0], 0, 50)
    with factory() as session:
        source = session.get(AthleteDailyTrainingLoad, source_id)
        snapshot = (source.total_load, source.endurance_load, source.strength_load, source.calculated_at)
    assert client.post("/training-status/recalculate", params=params()).json()[0]["total_load"] == 50
    with factory() as session:
        source = session.get(AthleteDailyTrainingLoad, source_id)
        assert (source.total_load, source.endurance_load, source.strength_load, source.calculated_at) == snapshot


def test_historical_change_updates_later_statuses(api_context):
    client, factory, _, _, athlete_ids = api_context
    source_id = add_source(factory, athlete_ids[0], 0, 10)
    add_source(factory, athlete_ids[0], 2, 20)
    request = params(end_date="2026-01-03")
    before = client.post("/training-status/recalculate", params=request).json()[-1]["fitness"]
    with factory() as session:
        session.get(AthleteDailyTrainingLoad, source_id).total_load = 100
        session.commit()
    TrackingSession.commits = 0
    client.post("/training-status/recalculate", params=params())
    after = client.get("/training-status/latest", params=latest_params()).json()["fitness"]
    assert after != before


def test_recalculate_without_sources_returns_empty_and_removes_matching_only(api_context):
    client, factory, _, _, athlete_ids = api_context
    add_status(factory, athlete_ids[0])
    add_status(factory, athlete_ids[1])
    add_status(factory, athlete_ids[0], training_status_algorithm_version="other")
    response = client.post("/training-status/recalculate", params=params())
    assert response.status_code == 200
    assert response.json() == []
    with factory() as session:
        rows = session.scalars(select(AthleteDailyTrainingStatus)).all()
        assert len(rows) == 2
        assert {row.athlete_profile_id for row in rows} == {athlete_ids[0], athlete_ids[1]}


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"start_date": "2026-01-02", "end_date": "2026-01-01"}, "invalid_training_status_range"),
        ({"timezone_name": "Unknown/Zone"}, "invalid_timezone"),
        ({"manual_strength_algorithm_version": " "}, "invalid_algorithm_version"),
    ],
)
def test_recalculate_maps_validation_errors(api_context, overrides, code):
    client, _, _, _, _ = api_context
    response = client.post("/training-status/recalculate", params=params(**overrides))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code
    assert TrackingSession.rollbacks == 1


def test_recalculate_rolls_back_and_hides_persistence_details(api_context, monkeypatch):
    client, _, _, _, _ = api_context
    monkeypatch.setattr(
        TrainingStatusApplication,
        "recalculate_training_status",
        Mock(side_effect=TrainingStatusPersistenceError("SQL table secret")),
    )
    response = client.post("/training-status/recalculate", params=params())
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "training_status_persistence_error"}}
    assert "SQL" not in response.text
    assert TrackingSession.commits == 0
    assert TrackingSession.rollbacks == 1


def test_missing_athlete_is_404_and_not_editable(api_context):
    client, _, active, _, _ = api_context
    active["user_id"] = uuid4()
    response = client.get("/training-status", params=params())
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "athlete_not_found"


def test_openapi_documents_routes_schema_defaults_and_no_athlete_id(api_context):
    client, _, _, _, _ = api_context
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]["/training-status"]) == {"get"}
    assert set(schema["paths"]["/training-status/latest"]) == {"get"}
    assert set(schema["paths"]["/training-status/recalculate"]) == {"post"}
    response_schema = schema["components"]["schemas"]["DailyTrainingStatusResponse"]
    assert "fitness" in response_schema["properties"]
    assert "42 días" in response_schema["properties"]["fitness"]["description"]
    assert "7 días" in response_schema["properties"]["fatigue"]["description"]
    assert "athlete_id" not in response_schema["properties"]
    operation = schema["paths"]["/training-status"]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["training_load_algorithm_version"]["schema"]["default"] == "0.7b.1"
    assert parameters["manual_strength_algorithm_version"]["schema"]["default"] == "0.7e.1"
    assert parameters["training_status_algorithm_version"]["schema"]["default"] == "0.7f.1"
    assert "athlete_id" not in parameters


def test_no_new_sawarnings_and_existing_health_route():
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", SAWarning)
        application = create_app()
    assert not [item for item in captured if issubclass(item.category, SAWarning)]
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
