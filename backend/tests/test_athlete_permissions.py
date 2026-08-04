from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.athlete_permissions import (
    AthleteCapability,
    athlete_has_capability,
    require_athlete_capability,
)
from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.db.models import (
    ActivityMetric,
    ActivityTrainingLoad,
    AthleteDailyTrainingLoad,
    AthleteDailyTrainingStatus,
    AthletePerformanceProfileVersion,
    AthletePerformanceReference,
    ManualStrengthSession,
    ManualStrengthTrainingLoad,
    UserAthleteMembership,
)
from test_multi_athlete_isolation import multi_athlete_context


EXPECTED = {
    "owner": set(AthleteCapability),
    "editor": set(AthleteCapability),
    "coach": set(AthleteCapability) - {
        AthleteCapability.DELETE_MANUAL_STRENGTH,
        AthleteCapability.MANAGE_STRAVA_CONNECTION,
        AthleteCapability.DELETE_STRAVA_LOCATION_EVIDENCE,
    },
    "viewer": {
        AthleteCapability.READ_ATHLETE_DATA,
        AthleteCapability.READ_STRAVA_INTEGRATION,
    },
    "unknown": set(),
}


def _context(role: str) -> CurrentAthleteContext:
    return CurrentAthleteContext(
        user_id=uuid4(),
        athlete_id=uuid4(),
        role=role,
        athlete_profile=None,  # type: ignore[arg-type]
        membership=None,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("role", EXPECTED)
@pytest.mark.parametrize("capability", list(AthleteCapability))
def test_complete_role_capability_matrix(role, capability):
    assert athlete_has_capability(_context(role), capability) is (
        capability in EXPECTED[role]
    )


def test_capability_dependency_returns_the_unchanged_context():
    context = _context("coach")
    dependency = require_athlete_capability(
        AthleteCapability.RECALCULATE_ATHLETE_DATA
    )
    assert dependency(context) is context


def test_capability_dependency_uses_uniform_denial_for_unknown_role():
    dependency = require_athlete_capability(
        AthleteCapability.CREATE_PERFORMANCE_PROFILE
    )
    with pytest.raises(HTTPException) as captured:
        dependency(_context("corrupt-role"))
    assert captured.value.status_code == 403
    assert captured.value.detail["code"] == "athlete_permission_denied"
    assert "role" not in str(captured.value.detail).lower()


def _set_shared_role(engine, ids, role: str, *, active: bool = True):
    with Session(engine) as session:
        membership = session.scalar(
            select(UserAthleteMembership).where(
                UserAthleteMembership.user_id == LOCAL_MVP_USER_ID,
                UserAthleteMembership.athlete_profile_id == ids["athlete_b2"],
            )
        )
        membership.role = role
        membership.is_active = active
        session.commit()


def _headers(ids):
    return {"X-TriCoach-Athlete-Id": str(ids["athlete_b2"])}


def _date_params(ids):
    day = ids["today"].isoformat()
    return {"start_date": day, "end_date": day, "timezone_name": "UTC"}


def _profile_payload(value=310):
    return {
        "effective_from": "2026-02-01T00:00:00Z",
        "data_origin": "manual",
        "cycling_ftp_watts": value,
    }


def _reference_payload(value=315):
    return {
        "sport": "cycling",
        "metric_type": "power",
        "value": value,
        "unit": "W",
        "data_origin": "manual",
        "quality_level": "high",
        "effective_from": "2026-02-02T00:00:00Z",
    }


def _strength_payload(minutes=25):
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timezone_name": "UTC",
        "duration_minutes": minutes,
        "body_regions": ["core"],
        "perceived_exertion": 5,
    }


def _snapshot(session: Session):
    def rows(model, *fields):
        entities = (model.id, *fields)
        return tuple(session.execute(select(*entities).order_by(model.id)).all())

    return (
        rows(ActivityMetric, ActivityMetric.value, ActivityMetric.calculated_at),
        rows(ActivityTrainingLoad, ActivityTrainingLoad.load_value, ActivityTrainingLoad.calculated_at),
        rows(AthleteDailyTrainingLoad, AthleteDailyTrainingLoad.total_load, AthleteDailyTrainingLoad.calculated_at),
        rows(AthleteDailyTrainingStatus, AthleteDailyTrainingStatus.total_load, AthleteDailyTrainingStatus.calculated_at),
        rows(ManualStrengthSession, ManualStrengthSession.duration_minutes, ManualStrengthSession.notes, ManualStrengthSession.updated_at),
        rows(ManualStrengthTrainingLoad, ManualStrengthTrainingLoad.load_value, ManualStrengthTrainingLoad.calculated_at),
        rows(AthletePerformanceProfileVersion, AthletePerformanceProfileVersion.cycling_ftp_watts),
        rows(AthletePerformanceReference, AthletePerformanceReference.value),
    )


def test_viewer_can_read_every_domain_and_all_writes_are_atomic(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    _set_shared_role(engine, ids, "viewer")
    headers = _headers(ids)
    dates = _date_params(ids)
    with Session(engine) as session:
        before = _snapshot(session)

    reads = [
        client.get("/activities", headers=headers),
        client.get(f"/activities/{ids['activity_b2']}", headers=headers),
        client.get(f"/activities/{ids['activity_b2']}/metrics", headers=headers),
        client.get("/dashboard/summary", headers=headers),
        client.get("/manual-strength-sessions", headers=headers),
        client.get("/athlete/performance-profile", headers=headers),
        client.get("/athlete/performance-references", headers=headers),
        client.get("/athlete/performance-zones", headers=headers),
        client.get(f"/activities/{ids['activity_b2']}/training-load", headers=headers),
        client.get("/training-load/daily", params=dates, headers=headers),
        client.get("/training-status", params=dates, headers=headers),
    ]
    assert all(response.status_code == 200 for response in reads)

    writes = [
        client.post(f"/activities/{ids['activity_b2']}/metrics/recalculate", headers=headers),
        client.post(f"/activities/{ids['activity_b2']}/training-load/recalculate", headers=headers),
        client.post("/training-load/daily/recalculate", params=dates, headers=headers),
        client.post("/training-load/weekly/recalculate", params=dates, headers=headers),
        client.post("/training-load/recalculate", params=dates, headers=headers),
        client.post("/training-status/recalculate", params=dates, headers=headers),
        client.post("/manual-strength-sessions", json=_strength_payload(), headers=headers),
        client.patch(f"/manual-strength-sessions/{ids['strength_b2']}", json={"duration_minutes": 12}, headers=headers),
        client.delete(f"/manual-strength-sessions/{ids['strength_b2']}", headers=headers),
        client.post(f"/manual-strength-sessions/{ids['strength_b2']}/training-load/recalculate", headers=headers),
        client.post("/athlete/performance-profile/versions", json=_profile_payload(), headers=headers),
        client.post("/athlete/performance-references", json=_reference_payload(), headers=headers),
    ]
    assert all(response.status_code == 403 for response in writes)
    assert all(
        response.json()["detail"]["code"] == "athlete_permission_denied"
        for response in writes
    )
    with Session(engine) as session:
        assert _snapshot(session) == before
        assert session.get(ManualStrengthSession, ids["strength_b2"]).duration_minutes == 40


def test_coach_can_write_and_recalculate_but_cannot_delete_strength(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    _set_shared_role(engine, ids, "coach")
    headers = _headers(ids)
    dates = _date_params(ids)
    allowed = [
        client.post(f"/activities/{ids['activity_b2']}/metrics/recalculate", headers=headers),
        client.post(f"/activities/{ids['activity_b2']}/training-load/recalculate", headers=headers),
        client.post("/training-load/daily/recalculate", params=dates, headers=headers),
        client.post("/training-status/recalculate", params=dates, headers=headers),
        client.post("/manual-strength-sessions", json=_strength_payload(), headers=headers),
        client.patch(f"/manual-strength-sessions/{ids['strength_b2']}", json={"duration_minutes": 35}, headers=headers),
        client.post(f"/manual-strength-sessions/{ids['strength_b2']}/training-load/recalculate", headers=headers),
        client.post("/athlete/performance-profile/versions", json=_profile_payload(), headers=headers),
        client.post("/athlete/performance-references", json=_reference_payload(), headers=headers),
    ]
    assert all(response.status_code in {200, 201} for response in allowed)
    denied = client.delete(f"/manual-strength-sessions/{ids['strength_b2']}", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "athlete_permission_denied"
    with Session(engine) as session:
        strength = session.get(ManualStrengthSession, ids["strength_b2"])
        assert strength is not None
        assert strength.duration_minutes == 35
        assert session.scalar(select(func.count()).select_from(ManualStrengthTrainingLoad).where(ManualStrengthTrainingLoad.session_id == strength.id)) == 1


@pytest.mark.parametrize("role", ["owner", "editor"])
def test_owner_and_editor_can_delete_manual_strength(multi_athlete_context, role):
    client, engine, ids = multi_athlete_context
    _set_shared_role(engine, ids, role)
    response = client.delete(
        f"/manual-strength-sessions/{ids['strength_b2']}", headers=_headers(ids)
    )
    assert response.status_code == 204
    with Session(engine) as session:
        assert session.get(ManualStrengthSession, ids["strength_b2"]) is None
        assert session.scalar(select(func.count()).select_from(ManualStrengthTrainingLoad).where(ManualStrengthTrainingLoad.session_id == ids["strength_b2"])) == 0


def test_permission_denied_foreign_resource_and_unauthorized_selection_are_distinct(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    headers = _headers(ids)
    _set_shared_role(engine, ids, "viewer")
    viewer = client.patch(
        f"/manual-strength-sessions/{ids['strength_b2']}",
        json={"duration_minutes": 10},
        headers=headers,
    )
    assert viewer.status_code == 403
    assert viewer.json()["detail"]["code"] == "athlete_permission_denied"

    _set_shared_role(engine, ids, "editor")
    foreign = client.patch(
        f"/manual-strength-sessions/{ids['strength_b1']}",
        json={"duration_minutes": 10},
        headers=headers,
    )
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "manual_strength_session_not_found"

    unauthorized = client.patch(
        f"/manual-strength-sessions/{ids['strength_b1']}",
        json={"duration_minutes": 10},
        headers={"X-TriCoach-Athlete-Id": str(ids["athlete_b1"])},
    )
    assert unauthorized.status_code == 403
    assert unauthorized.json()["detail"]["code"] == "athlete_not_authorized"


def test_inactive_membership_is_rejected_before_read_or_permission_check(multi_athlete_context):
    client, engine, ids = multi_athlete_context
    _set_shared_role(engine, ids, "owner", active=False)
    response = client.get("/activities", headers=_headers(ids))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "athlete_not_authorized"


def test_openapi_has_one_athlete_header_and_no_role_input(multi_athlete_context):
    client, _, _ = multi_athlete_context
    schema = client.get("/openapi.json").json()
    for path, method in (
        ("/activities/{activity_id}/metrics/recalculate", "post"),
        ("/manual-strength-sessions/{session_id}", "patch"),
        ("/training-status/recalculate", "post"),
    ):
        parameters = schema["paths"][path][method].get("parameters", [])
        athlete_headers = [
            item for item in parameters if item["name"].lower() == "x-tricoach-athlete-id"
        ]
        assert len(athlete_headers) == 1
    assert '"role"' not in str(schema["components"]["schemas"])
