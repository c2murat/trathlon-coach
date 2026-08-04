from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import AuthenticatedUser, LOCAL_MVP_USER_ID
from app.api.dependencies.current_athlete import resolve_current_athlete
from app.db.base import Base, utc_now
from app.db.models import (
    AthleteProfile,
    CompletedActivity,
    User,
    UserAthleteMembership,
)
from app.db.models.training_load import ActivityTrainingLoad
from app.db.models.training_load_aggregate import AthleteDailyTrainingLoad
from app.db.session import get_db_session
from app.main import create_app
from test_activity_reads import activity_client


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _identity(session: Session, suffix: str, *, user_id=None, athlete_id=None):
    user = User(
        id=user_id or uuid4(),
        email=f"{suffix}@example.invalid",
        normalized_email=f"{suffix}@example.invalid",
        auth_subject=f"auth-{suffix}",
    )
    athlete = AthleteProfile(id=athlete_id or uuid4(), user=user)
    session.add_all([user, athlete])
    session.flush()
    return user, athlete


def _membership(session, user, athlete, *, default=False, active=True, role="owner"):
    membership = UserAthleteMembership(
        user=user,
        athlete_profile=athlete,
        role=role,
        is_active=active,
        is_default=default,
    )
    session.add(membership)
    session.flush()
    return membership


def _error(session, user, requested=None):
    with pytest.raises(HTTPException) as captured:
        resolve_current_athlete(session, AuthenticatedUser(id=user.id), requested)
    return captured.value


def test_no_membership_returns_not_found(session):
    user, _ = _identity(session, "none")
    error = _error(session, user)
    assert error.status_code == 404
    assert error.detail == {"code": "athlete_profile_not_found"}


def test_single_membership_is_selected(session):
    user, athlete = _identity(session, "single")
    membership = _membership(session, user, athlete, role="viewer")
    context = resolve_current_athlete(session, AuthenticatedUser(id=user.id))
    assert context.athlete_id == athlete.id
    assert context.user_id == user.id
    assert context.role == "viewer"
    assert context.membership is membership


def test_exactly_one_default_is_selected_from_multiple_memberships(session):
    user, first = _identity(session, "default-user")
    _, second = _identity(session, "default-shared")
    _membership(session, user, first)
    _membership(session, user, second, default=True, role="coach")
    context = resolve_current_athlete(session, AuthenticatedUser(id=user.id))
    assert context.athlete_id == second.id
    assert context.role == "coach"


def test_multiple_memberships_without_default_require_selection(session):
    user, first = _identity(session, "ambiguous-user")
    _, second = _identity(session, "ambiguous-shared")
    _membership(session, user, first)
    _membership(session, user, second)
    error = _error(session, user)
    assert error.status_code == 409
    assert error.detail == {"code": "athlete_selection_required"}


def test_multiple_default_memberships_report_inconsistent_configuration(session):
    user, first = _identity(session, "invalid-default-user")
    _, second = _identity(session, "invalid-default-shared")
    _membership(session, user, first, default=True)
    _membership(session, user, second, default=True)
    error = _error(session, user)
    assert error.status_code == 409
    assert error.detail == {"code": "athlete_default_configuration_invalid"}


def test_explicit_owned_and_shared_memberships_are_allowed(session):
    user, owned = _identity(session, "header-user")
    _, shared = _identity(session, "header-shared")
    _membership(session, user, owned, default=True)
    _membership(session, user, shared, role="coach")

    owned_context = resolve_current_athlete(
        session, AuthenticatedUser(id=user.id), str(owned.id)
    )
    shared_context = resolve_current_athlete(
        session, AuthenticatedUser(id=user.id), str(shared.id)
    )
    assert owned_context.athlete_id == owned.id
    assert shared_context.athlete_id == shared.id
    assert shared_context.role == "coach"


def test_explicit_foreign_or_inactive_membership_is_forbidden(session):
    user, _ = _identity(session, "forbidden-user")
    _, foreign = _identity(session, "foreign")
    _, inactive = _identity(session, "inactive")
    _membership(session, user, inactive, active=False)

    for athlete in (foreign, inactive):
        error = _error(session, user, str(athlete.id))
        assert error.status_code == 403
        assert error.detail == {"code": "athlete_not_authorized"}


def test_invalid_explicit_athlete_uuid_is_rejected(session):
    user, _ = _identity(session, "invalid-header")
    error = _error(session, user, "not-a-uuid")
    assert error.status_code == 422
    assert error.detail == {"code": "invalid_athlete_id"}


def test_header_selection_is_wired_to_membership_resolution(activity_client):
    client, engine = activity_client
    with Session(engine) as session:
        membership = session.scalar(select(UserAthleteMembership))
        athlete_id = membership.athlete_profile_id

    allowed = client.get(
        "/training-load/daily",
        params={"start_date": "2026-01-01", "end_date": "2026-01-02", "timezone_name": "UTC"},
        headers={"X-TriCoach-Athlete-Id": str(athlete_id)},
    )
    forbidden = client.get(
        "/training-load/daily",
        params={"start_date": "2026-01-01", "end_date": "2026-01-02", "timezone_name": "UTC"},
        headers={"X-TriCoach-Athlete-Id": str(uuid4())},
    )
    invalid = client.get(
        "/training-load/daily",
        params={"start_date": "2026-01-01", "end_date": "2026-01-02", "timezone_name": "UTC"},
        headers={"X-TriCoach-Athlete-Id": "invalid"},
    )
    assert allowed.status_code == 200
    assert forbidden.status_code == 403
    assert invalid.status_code == 422


def test_user_id_collision_never_grants_access_or_mutates_foreign_rows():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        current_user = User(
            id=LOCAL_MVP_USER_ID,
            email="collision-user@example.invalid",
            normalized_email="collision-user@example.invalid",
            auth_subject="collision-user",
        )
        foreign_user = User(
            email="collision-owner@example.invalid",
            normalized_email="collision-owner@example.invalid",
            auth_subject="collision-owner",
        )
        foreign_athlete = AthleteProfile(id=LOCAL_MVP_USER_ID, user=foreign_user)
        activity = CompletedActivity(
            athlete=foreign_athlete,
            source_summary="manual",
            sport="running",
            name="Foreign collision activity",
            start_at=utc_now(),
            timezone="UTC",
            elapsed_time_s=600,
            moving_time_s=600,
            distance_m=2000,
        )
        session.add_all([current_user, foreign_user, foreign_athlete, activity])
        session.flush()
        load = ActivityTrainingLoad(
            completed_activity_id=activity.id,
            load_value=10,
            method="duration_only",
            unit="load_points",
            coverage="complete",
            quality="low",
            algorithm_version="0.7b.1",
            source_metrics={},
            warnings=[],
            calculated_at=utc_now(),
        )
        aggregate = AthleteDailyTrainingLoad(
            athlete_profile_id=foreign_athlete.id,
            local_date=date(2026, 1, 1),
            timezone_name="UTC",
            source_load_algorithm_version="0.7b.1",
            manual_strength_algorithm_version="0.7e.1",
            aggregation_algorithm_version="0.7c.1",
            total_load=Decimal("10"),
            endurance_load=Decimal("10"),
            strength_load=Decimal("0"),
            strength_session_count=0,
            activity_count=1,
            loaded_activity_count=1,
            null_load_activity_count=0,
            total_duration_seconds=Decimal("600"),
            coverage="complete",
            quality="high",
            warnings=[],
            activity_ids=[str(activity.id)],
            calculated_at=utc_now(),
        )
        session.add_all([load, aggregate])
        session.commit()
        activity_id, load_id, aggregate_id = activity.id, load.id, aggregate.id

    def session_override():
        with Session(engine) as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = session_override
    params = {"start_date": "2026-01-01", "end_date": "2026-01-01", "timezone_name": "UTC"}
    with TestClient(app) as client:
        responses = [
            client.get(f"/activities/{activity_id}/training-load"),
            client.post(f"/activities/{activity_id}/training-load/recalculate"),
            client.get("/training-load/daily", params=params),
            client.post("/training-load/daily/recalculate", params=params),
            client.post("/training-load/weekly/recalculate", params=params),
            client.post("/training-load/recalculate", params=params),
        ]
    assert all(response.status_code == 404 for response in responses)
    assert all(response.json()["detail"]["code"] == "athlete_profile_not_found" for response in responses)

    with Session(engine) as session:
        assert session.get(ActivityTrainingLoad, load_id).load_value == 10
        assert session.get(AthleteDailyTrainingLoad, aggregate_id).total_load == 10
        assert session.scalar(select(func.count()).select_from(ActivityTrainingLoad)) == 1
        assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingLoad)) == 1
    engine.dispose()
