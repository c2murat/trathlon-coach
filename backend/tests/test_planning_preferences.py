from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.application.planning_preferences import PlanningPreferencesApplication, preferences_from_row
from app.db.models import AthletePlanningPreferenceVersion, UserAthleteMembership
from app.domains.planning.contracts import AvailabilitySlot, PlanningPreferences, PlanningRequest
from tests.test_athlete_creation_api import add_athlete, add_user, athlete_env, authenticated_client, mutation_headers


H = "X-TriCoach-Athlete-Id"


def payload(minutes=60):
    return {
        "availability_slots": [
            {"weekday": 0, "available_minutes": 0, "max_sessions": 0},
            {"weekday": 1, "available_minutes": minutes, "max_sessions": 1},
        ],
        "max_sessions_per_day": 1,
        "max_sessions_per_week": 6,
        "preferred_rest_days": [0],
        "preferred_long_run_day": 6,
        "preferred_long_bike_day": 5,
        "strength_sessions_per_week": 2,
    }


def test_put_get_versions_zero_minutes_and_soft_preferences(athlete_env):
    session, _, app = athlete_env
    user = add_user(session, "planning-preferences", account_plan="athlete")
    athlete = add_athlete(session, user, "A", role="athlete", default=True)
    client = authenticated_client(app, user)
    headers = mutation_headers(client, **{H: str(athlete.id)})
    first = client.put("/planning/preferences", json=payload(), headers=headers)
    repeated = client.put("/planning/preferences", json=payload(), headers=headers)
    second = client.put("/planning/preferences", json=payload(90), headers=headers)
    repeated_second = client.put("/planning/preferences", json=payload(90), headers=headers)
    assert first.status_code == repeated.status_code == second.status_code == repeated_second.status_code == 200
    assert first.json()["version_number"] == 1
    assert repeated.json()["id"] == first.json()["id"]
    assert second.json()["version_number"] == 2
    assert repeated_second.json()["id"] == second.json()["id"]
    result = client.get("/planning/preferences", headers={H: str(athlete.id)})
    assert result.status_code == 200
    assert result.json()["preferences"]["availability_slots"][0] == {
        "weekday": 0, "available_minutes": 0, "max_sessions": 0,
        "earliest_time": None, "latest_time": None,
    }
    assert result.json()["preferences"]["preferred_rest_days"] == [0]
    assert session.scalar(select(AthletePlanningPreferenceVersion).where(
        AthletePlanningPreferenceVersion.athlete_profile_id == athlete.id,
        AthletePlanningPreferenceVersion.version_number == 1,
    )) is not None
    assert session.scalar(select(func.count()).select_from(AthletePlanningPreferenceVersion).where(
        AthletePlanningPreferenceVersion.athlete_profile_id == athlete.id,
    )) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_sessions_per_day", 2),
        ("max_sessions_per_week", 5),
        ("preferred_rest_days", [0, 3]),
        ("preferred_long_run_day", 4),
        ("preferred_long_bike_day", 4),
        ("strength_sessions_per_week", 3),
    ],
)
def test_each_real_global_preference_change_creates_a_version(athlete_env, field, value):
    session, _, app = athlete_env
    user = add_user(session, f"planning-change-{field}", account_plan="athlete")
    athlete = add_athlete(session, user, "A", role="athlete", default=True)
    client = authenticated_client(app, user)
    headers = mutation_headers(client, **{H: str(athlete.id)})
    assert client.put("/planning/preferences", json=payload(), headers=headers).json()["version_number"] == 1
    changed = payload()
    changed[field] = value
    assert client.put("/planning/preferences", json=changed, headers=headers).json()["version_number"] == 2


@pytest.mark.parametrize(("field", "value"), [("available_minutes", 75), ("max_sessions", 2)])
def test_each_real_slot_change_creates_a_version(athlete_env, field, value):
    session, _, app = athlete_env
    user = add_user(session, f"planning-slot-{field}", account_plan="athlete")
    athlete = add_athlete(session, user, "A", role="athlete", default=True)
    client = authenticated_client(app, user)
    headers = mutation_headers(client, **{H: str(athlete.id)})
    assert client.put("/planning/preferences", json=payload(), headers=headers).json()["version_number"] == 1
    changed = payload()
    changed["availability_slots"][1][field] = value
    assert client.put("/planning/preferences", json=changed, headers=headers).json()["version_number"] == 2


def test_slot_order_is_contractually_canonical(athlete_env):
    session, _, app = athlete_env
    user = add_user(session, "planning-slot-order", account_plan="athlete")
    athlete = add_athlete(session, user, "A", role="athlete", default=True)
    client = authenticated_client(app, user)
    headers = mutation_headers(client, **{H: str(athlete.id)})
    unordered = payload()
    unordered["availability_slots"].reverse()
    assert client.put("/planning/preferences", json=unordered, headers=headers).status_code == 422
    assert session.scalar(select(func.count()).select_from(AthletePlanningPreferenceVersion)) == 0


def test_preferences_are_athlete_scoped_and_coach_read_only(athlete_env):
    session, _, app = athlete_env
    owner = add_user(session, "planning-owner")
    athlete_a = add_athlete(session, owner, "A", default=True)
    athlete_b = add_athlete(session, owner, "B")
    owner_client = authenticated_client(app, owner)
    assert owner_client.put("/planning/preferences", json=payload(), headers=mutation_headers(owner_client, **{H: str(athlete_a.id)})).status_code == 200
    assert owner_client.get("/planning/preferences", headers={H: str(athlete_b.id)}).status_code == 404
    coach = add_user(session, "planning-coach", account_plan="coach")
    session.add(UserAthleteMembership(user_id=coach.id, athlete_profile_id=athlete_a.id, role="coach", is_active=True, is_default=True))
    session.commit()
    coach_client = authenticated_client(app, coach)
    assert coach_client.get("/planning/preferences", headers={H: str(athlete_a.id)}).status_code == 200
    assert coach_client.put("/planning/preferences", json=payload(), headers=mutation_headers(coach_client, **{H: str(athlete_a.id)})).status_code == 403


def test_viewer_cannot_write_and_membership_does_not_leak_cross_athlete(athlete_env):
    session, _, app = athlete_env
    owner_a = add_user(session, "planning-owner-a")
    athlete_a = add_athlete(session, owner_a, "A", default=True)
    owner_b = add_user(session, "planning-owner-b")
    athlete_b = add_athlete(session, owner_b, "B", default=True)
    client_a = authenticated_client(app, owner_a)
    headers_a = mutation_headers(client_a, **{H: str(athlete_a.id)})
    assert client_a.put("/planning/preferences", json=payload(), headers=headers_a).status_code == 200
    assert client_a.get("/planning/preferences", headers={H: str(athlete_b.id)}).status_code in {403, 404}
    assert client_a.put(
        "/planning/preferences", json=payload(),
        headers=mutation_headers(client_a, **{H: str(athlete_b.id)}),
    ).status_code in {403, 404}
    assert session.scalar(select(func.count()).select_from(AthletePlanningPreferenceVersion).where(
        AthletePlanningPreferenceVersion.athlete_profile_id == athlete_b.id,
    )) == 0

    viewer = add_user(session, "planning-viewer")
    session.add(UserAthleteMembership(
        user_id=viewer.id, athlete_profile_id=athlete_a.id,
        role="viewer", is_active=True, is_default=True,
    ))
    session.commit()
    viewer_client = authenticated_client(app, viewer)
    assert viewer_client.get("/planning/preferences", headers={H: str(athlete_a.id)}).status_code == 200
    assert viewer_client.put(
        "/planning/preferences", json=payload(),
        headers=mutation_headers(viewer_client, **{H: str(athlete_a.id)}),
    ).status_code == 403


def test_request_contract_allows_persisted_preferences_fallback():
    assert PlanningRequest.model_fields["preferences"].default is None


def test_domain_rejects_invalid_zero_minutes_and_limits():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        AvailabilitySlot(weekday=0, available_minutes=0, max_sessions=1)
    with pytest.raises(ValidationError):
        PlanningPreferences(max_sessions_per_day=5, max_sessions_per_week=1, strength_sessions_per_week=0)
