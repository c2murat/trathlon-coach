from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.db.base import Base, utc_now
from app.db.models import AthleteProfile, CompletedActivity, User
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture
def activity_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    now = utc_now()
    with Session(engine) as session:
        user = User(
            id=LOCAL_MVP_USER_ID,
            email="local@example.invalid",
            normalized_email="local@example.invalid",
            auth_subject="local",
            timezone="Europe/Madrid",
        )
        athlete = AthleteProfile(
            user=user, timezone="Europe/Madrid", unit_system="metric"
        )
        other_user = User(
            email="other@example.invalid",
            normalized_email="other@example.invalid",
            auth_subject="other",
        )
        other_athlete = AthleteProfile(user=other_user)
        session.add_all([user, athlete, other_user, other_athlete])
        session.flush()
        for index in range(3):
            session.add(
                CompletedActivity(
                    athlete=athlete,
                    external_activity_id=str(100 + index),
                    source_summary="strava",
                    sport="running",
                    name=f"Owned {index}",
                    start_at=now - timedelta(days=index),
                    timezone="Europe/Madrid",
                    elapsed_time_s=600 + index,
                    moving_time_s=580 + index,
                    distance_m=2000 + index,
                    elevation_gain_m=20 + index,
                    average_heart_rate_bpm=140 + index,
                    average_power_w=200 + index,
                    indoor=False,
                    manual=False,
                    visibility="everyone",
                )
            )
        session.add(
            CompletedActivity(
                athlete=other_athlete,
                external_activity_id="private-other-user",
                source_summary="strava",
                sport="cycling",
                name="Other athlete",
                start_at=now + timedelta(days=1),
                timezone="UTC",
                elapsed_time_s=100,
            )
        )
        session.commit()

    def session_override():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = session_override
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


def test_activities_are_newest_first_with_total_and_safe_fields(activity_client):
    client, _ = activity_client
    response = client.get("/activities")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert [item["name"] for item in body["items"]] == [
        "Owned 0",
        "Owned 1",
        "Owned 2",
    ]
    assert set(body["items"][0]) == {
        "id",
        "external_activity_id",
        "name",
        "sport_type",
        "start_time",
        "athlete_timezone",
        "distance_metres",
        "moving_time_seconds",
        "elapsed_time_seconds",
        "elevation_metres",
        "average_heart_rate",
        "average_watts",
        "trainer",
        "manual",
        "visibility",
    }
    serialized = response.text
    assert "private-other-user" not in serialized
    assert "integration_account" not in serialized
    assert "access_token" not in serialized


def test_activity_pagination_and_maximum_limit(activity_client):
    client, _ = activity_client
    response = client.get("/activities?limit=1&offset=1")
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert [item["name"] for item in response.json()["items"]] == ["Owned 1"]
    assert client.get("/activities?limit=100").status_code == 200
    assert client.get("/activities?limit=101").status_code == 422


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=-1", "limit=invalid", "offset=-1", "offset=invalid"],
)
def test_activity_query_rejects_invalid_limit_or_offset(activity_client, query):
    client, _ = activity_client
    assert client.get(f"/activities?{query}").status_code == 422


def test_empty_owned_activity_list(activity_client):
    client, engine = activity_client
    with Session(engine) as session:
        for activity in session.query(CompletedActivity).filter(
            CompletedActivity.name.like("Owned %")
        ):
            session.delete(activity)
        session.commit()
    response = client.get("/activities")
    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "limit": 20,
        "offset": 0,
        "items": [],
    }


def test_cors_allows_only_the_configured_frontend_origin(activity_client):
    client, _ = activity_client
    allowed = client.options(
        "/activities",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )

    localhost = client.options("/activities", headers={"Origin":"http://localhost:5173","Access-Control-Request-Method":"GET"})
    assert localhost.headers["access-control-allow-origin"] == "http://localhost:5173"

    rejected = client.options(
        "/activities",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_filters_combine_and_total_is_after_filtering(activity_client):
    client,_=activity_client
    assert client.get("/activities?sport=running&min_distance_metres=2001&max_distance_metres=2002&trainer=false&manual=false&visibility=everyone&search=OWNED").json()["total"]==2
    assert client.get("/activities?date_from=1900-01-01&date_to=2999-12-31").json()["total"]==3

def test_filter_validation(activity_client):
    client,_=activity_client
    for query in ["sport=bad","date_from=bad","date_from=2026-02-02&date_to=2026-01-01","min_distance_metres=-1","min_distance_metres=5&max_distance_metres=1","trainer=bad","manual=bad","visibility=private","search="]:
        assert client.get(f"/activities?{query}").status_code==422

def test_filter_options_are_owned_and_safe(activity_client):
    client,_=activity_client;body=client.get("/activities/filter-options").json()
    assert body["sport_types"]==["running"] and body["visibility_values"]==["everyone"]
    assert body["minimum_activity_date"] and body["maximum_activity_date"]

def test_owned_activity_detail_and_safe_serialization(activity_client):
    client,engine=activity_client
    with Session(engine) as session: activity=session.query(CompletedActivity).filter_by(name="Owned 0").one();activity_id=activity.id
    response=client.get(f"/activities/{activity_id}");assert response.status_code==200;body=response.json()
    assert body["name"]=="Owned 0" and "max_heart_rate" in body and "created_at" in body
    assert "access_token" not in response.text and "integration_account" not in response.text

def test_missing_foreign_and_deleted_details_are_404(activity_client):
    client,engine=activity_client
    with Session(engine) as session:
        foreign=session.query(CompletedActivity).filter_by(name="Other athlete").one()
        owned=session.query(CompletedActivity).filter_by(name="Owned 2").one();owned.deleted_at=utc_now();foreign_id=foreign.id;deleted_id=owned.id;session.commit()
    assert client.get(f"/activities/{foreign_id}").status_code==404
    assert client.get(f"/activities/{deleted_id}").status_code==404
    assert client.get("/activities/00000000-0000-4000-8000-000000000099").status_code==404
