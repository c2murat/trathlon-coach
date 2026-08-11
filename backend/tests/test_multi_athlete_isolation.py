from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.db.base import Base, utc_now
from app.db.models import (
    ActivityMetric,
    ActivityTrainingLoad,
    AthleteDailyTrainingLoad,
    AthleteDailyTrainingStatus,
    AthletePerformanceReference,
    AthleteProfile,
    CompletedActivity,
    ManualStrengthSession,
    ManualStrengthTrainingLoad,
    User,
    UserAthleteMembership,
)
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture
def multi_athlete_context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        del record
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    now = utc_now()
    today = now.date()

    with Session(engine) as session:
        user_a = User(
            id=LOCAL_MVP_USER_ID,
            email="multi-a@example.invalid",
            normalized_email="multi-a@example.invalid",
            auth_subject="multi-a",
        )
        user_b = User(
            email="multi-b@example.invalid",
            normalized_email="multi-b@example.invalid",
            auth_subject="multi-b",
        )
        athlete_a1 = AthleteProfile(display_name="Test athlete", timezone="UTC")
        athlete_b1 = AthleteProfile(display_name="Test athlete", timezone="UTC")
        session.add_all([athlete_a1, athlete_b1])
        session.flush()

        # B2 keeps B as its legacy owner, while A receives a shared membership.
        user_b2 = User(
            email="multi-b2-owner@example.invalid",
            normalized_email="multi-b2-owner@example.invalid",
            auth_subject="multi-b2-owner",
        )
        athlete_b2 = AthleteProfile(display_name="Test athlete", timezone="UTC")
        session.add(athlete_b2)
        session.flush()
        session.add_all(
            [
                UserAthleteMembership(
                    user=user_a,
                    athlete_profile=athlete_a1,
                    role="owner",
                    is_active=True,
                    is_default=True,
                ),
                UserAthleteMembership(
                    user=user_a,
                    athlete_profile=athlete_b2,
                    role="editor",
                    is_active=True,
                    is_default=False,
                ),
                UserAthleteMembership(
                    user=user_b,
                    athlete_profile=athlete_b1,
                    role="owner",
                    is_active=True,
                    is_default=True,
                ),
                UserAthleteMembership(
                    user=user_b,
                    athlete_profile=athlete_b2,
                    role="owner",
                    is_active=True,
                    is_default=False,
                ),
            ]
        )

        activities = {}
        for key, athlete, sport, distance in (
            ("a1", athlete_a1, "running", 1000),
            ("b1", athlete_b1, "swimming", 2000),
            ("b2", athlete_b2, "cycling", 3000),
        ):
            activity = CompletedActivity(
                athlete=athlete,
                source_summary="manual",
                sport=sport,
                name=f"activity-{key}",
                start_at=now,
                timezone="UTC",
                elapsed_time_s=distance,
                moving_time_s=distance,
                distance_m=distance,
            )
            session.add(activity)
            session.flush()
            activities[key] = activity
            session.add_all(
                [
                    ActivityMetric(
                        completed_activity_id=activity.id,
                        metric_key="distance",
                        algorithm_version="0.6c.1",
                        status="available",
                        value=float(distance),
                        unit="m",
                        source="activity_summary",
                        quality_notes=[],
                        calculated_at=now,
                    ),
                    ActivityTrainingLoad(
                        completed_activity_id=activity.id,
                        load_value=float(distance / 100),
                        method="duration_only",
                        unit="load_points",
                        coverage="complete",
                        quality="low",
                        algorithm_version="0.7b.1",
                        source_metrics={},
                        warnings=[],
                        calculated_at=now,
                    ),
                ]
            )

        strength_sessions = {}
        for key, athlete, minutes in (
            ("a1", athlete_a1, 20),
            ("b1", athlete_b1, 30),
            ("b2", athlete_b2, 40),
        ):
            strength = ManualStrengthSession(
                athlete_id=athlete.id,
                started_at=now,
                timezone_name="UTC",
                duration_minutes=minutes,
                body_regions=["core"],
                perceived_exertion=5,
                notes=f"strength-{key}",
            )
            session.add(strength)
            session.flush()
            strength_sessions[key] = strength
            session.add(
                ManualStrengthTrainingLoad(
                    session_id=strength.id,
                    load_value=Decimal(minutes),
                    method="strength_rpe",
                    unit="load_points",
                    quality="medium",
                    warnings=[],
                    algorithm_version="0.7e.1",
                    calculated_at=now,
                )
            )

        for key, athlete, total in (
            ("a1", athlete_a1, 10),
            ("b1", athlete_b1, 20),
            ("b2", athlete_b2, 30),
        ):
            session.add(
                AthleteDailyTrainingLoad(
                    athlete_profile_id=athlete.id,
                    local_date=today,
                    timezone_name="UTC",
                    source_load_algorithm_version="0.7b.1",
                    manual_strength_algorithm_version="0.7e.1",
                    aggregation_algorithm_version="0.7c.1",
                    total_load=Decimal(total),
                    endurance_load=Decimal(total),
                    strength_load=Decimal(0),
                    strength_session_count=0,
                    activity_count=1,
                    loaded_activity_count=1,
                    null_load_activity_count=0,
                    total_duration_seconds=Decimal(600),
                    coverage="complete",
                    quality="high",
                    warnings=[],
                    activity_ids=[str(activities[key].id)],
                    calculated_at=now,
                )
            )
            session.add(
                AthleteDailyTrainingStatus(
                    athlete_profile_id=athlete.id,
                    local_date=today,
                    timezone_name="UTC",
                    training_load_algorithm_version="0.7b.1",
                    manual_strength_algorithm_version="0.7e.1",
                    training_status_algorithm_version="0.7f.1",
                    total_load=Decimal(total),
                    fitness=Decimal(total),
                    fatigue=Decimal(total),
                    form=Decimal(0),
                    history_day_number=1,
                    is_warmup=True,
                    calculated_at=now,
                )
            )

        foreign_reference = AthletePerformanceReference(
            athlete_profile_id=athlete_b1.id,
            sport="cycling",
            metric_type="power",
            value=Decimal(999),
            unit="W",
            data_origin="manual",
            quality_level="high",
            effective_from=now,
            algorithm_version="0.7a.3",
        )
        session.add(foreign_reference)
        session.commit()
        ids = {
            "athlete_a1": athlete_a1.id,
            "athlete_b1": athlete_b1.id,
            "athlete_b2": athlete_b2.id,
            "activity_a1": activities["a1"].id,
            "activity_b1": activities["b1"].id,
            "activity_b2": activities["b2"].id,
            "strength_a1": strength_sessions["a1"].id,
            "strength_b1": strength_sessions["b1"].id,
            "strength_b2": strength_sessions["b2"].id,
            "foreign_reference": foreign_reference.id,
            "today": today,
        }

    def database_override():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = database_override
    with TestClient(app) as client:
        yield client, engine, ids
    engine.dispose()


def _shared(ids):
    return {"X-TriCoach-Athlete-Id": str(ids["athlete_b2"])}


def test_activities_options_and_dashboard_switch_completely(multi_athlete_context):
    client, _, ids = multi_athlete_context
    default = client.get("/activities").json()
    shared = client.get("/activities", headers=_shared(ids)).json()
    assert [row["name"] for row in default["items"]] == ["activity-a1"]
    assert [row["name"] for row in shared["items"]] == ["activity-b2"]
    assert client.get(f"/activities/{ids['activity_b1']}").status_code == 404
    assert client.get("/activities/filter-options").json()["sport_types"] == ["running"]
    assert client.get("/activities/filter-options", headers=_shared(ids)).json()["sport_types"] == ["cycling"]
    assert client.get("/dashboard/summary").json()["total_distance_metres"] == 1000
    assert client.get("/dashboard/summary", headers=_shared(ids)).json()["total_distance_metres"] == 3000
    assert client.get("/dashboard/trends?weeks=4").json() != client.get("/dashboard/trends?weeks=4", headers=_shared(ids)).json()
    assert client.get("/dashboard/consistency?weeks=4").json() != client.get("/dashboard/consistency?weeks=4", headers=_shared(ids)).json()


def test_metrics_allow_shared_and_reject_foreign_without_mutation(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    assert client.get(f"/activities/{ids['activity_a1']}/metrics").status_code == 200
    shared = client.get(f"/activities/{ids['activity_b2']}/metrics", headers=_shared(ids))
    assert shared.status_code == 200
    assert shared.json()["metrics"][0]["value"] == 3000
    foreign = client.post(f"/activities/{ids['activity_b1']}/metrics/recalculate", headers=_shared(ids))
    assert foreign.status_code == 404
    with Session(engine) as session:
        row = session.scalar(select(ActivityMetric).where(ActivityMetric.completed_activity_id == ids["activity_b1"]))
        assert row.value == 2000


def test_strength_crud_uses_selected_athlete_for_every_operation(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    assert [row["notes"] for row in client.get("/manual-strength-sessions").json()] == ["strength-a1"]
    assert [row["notes"] for row in client.get("/manual-strength-sessions", headers=_shared(ids)).json()] == ["strength-b2"]
    payload = {"started_at": datetime.now(timezone.utc).isoformat(), "timezone_name": "UTC", "duration_minutes": 15, "body_regions": ["core"], "perceived_exertion": 4}
    created = client.post("/manual-strength-sessions", json=payload, headers=_shared(ids))
    assert created.status_code == 201
    created_id = UUID(created.json()["id"])
    with Session(engine) as session:
        assert session.get(ManualStrengthSession, created_id).athlete_id == ids["athlete_b2"]
    assert client.patch(f"/manual-strength-sessions/{ids['strength_b1']}", json={"duration_minutes": 10}, headers=_shared(ids)).status_code == 404
    assert client.post(f"/manual-strength-sessions/{ids['strength_b1']}/training-load/recalculate", headers=_shared(ids)).status_code == 404
    assert client.delete(f"/manual-strength-sessions/{ids['strength_b1']}", headers=_shared(ids)).status_code == 404


def test_profiles_references_and_zones_support_shared_membership(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    profile = {"effective_from": "2026-01-01T00:00:00Z", "data_origin": "manual", "cycling_ftp_watts": 321}
    assert client.post("/athlete/performance-profile/versions", json=profile, headers=_shared(ids)).status_code == 201
    assert client.get("/athlete/performance-profile").json()["profile"] is None
    assert client.get("/athlete/performance-profile", headers=_shared(ids)).json()["profile"]["cycling_ftp_watts"] == 321
    reference = {"sport": "cycling", "metric_type": "power", "value": 333, "unit": "W", "data_origin": "manual", "quality_level": "high", "effective_from": "2026-01-02T00:00:00Z"}
    created = client.post("/athlete/performance-references", json=reference, headers=_shared(ids))
    assert created.status_code == 201
    assert created.json()["athlete_profile_id"] == str(ids["athlete_b2"])
    assert client.get("/athlete/performance-references/history").json() == []
    assert len(client.get("/athlete/performance-references/history", headers=_shared(ids)).json()) == 1
    assert client.get(f"/athlete/performance-references/{ids['foreign_reference']}", headers=_shared(ids)).status_code == 404
    zones = client.get("/athlete/performance-zones", headers=_shared(ids)).json()
    assert any(zone["metric_type"] == "power" for zone in zones)


def test_load_aggregates_and_status_never_mix_selected_athletes(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    day = ids["today"].isoformat()
    params = {"start_date": day, "end_date": day, "timezone_name": "UTC"}
    default_daily = client.get("/training-load/daily", params=params).json()
    shared_daily = client.get("/training-load/daily", params=params, headers=_shared(ids)).json()
    assert default_daily[0]["activity_ids"] == [str(ids["activity_a1"])]
    assert shared_daily[0]["activity_ids"] == [str(ids["activity_b2"])]
    assert client.get(f"/activities/{ids['activity_b1']}/training-load", headers=_shared(ids)).status_code == 404
    default_status = client.get("/training-status", params=params).json()
    shared_status = client.get("/training-status", params=params, headers=_shared(ids)).json()
    assert default_status[0]["total_load"] == 10
    assert shared_status[0]["total_load"] == 30
    assert client.get("/training-status/latest", params={"timezone_name": "UTC"}).json()["total_load"] == 10
    assert client.get("/training-status/latest", params={"timezone_name": "UTC"}, headers=_shared(ids)).json()["total_load"] == 30

    before = None
    with Session(engine) as session:
        before = session.scalar(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id == ids["athlete_a1"])).total_load
    response = client.post("/training-load/daily/recalculate", params=params, headers=_shared(ids))
    assert response.status_code == 200
    with Session(engine) as session:
        after = session.scalar(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id == ids["athlete_a1"])).total_load
        assert after == before
