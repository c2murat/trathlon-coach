from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.api.v1.routes import performance_profiles
from app.api.v1.schemas.capability_reassessment import CapabilityReassessmentResponse
from app.db.models import AthleteProfile, AthletePerformanceProfileVersion, UserAthleteMembership
from tests.test_performance_references_api import performance_client
from tests.test_capability_reassessment import run, rows

PATH = "/athlete/performance-profile/reassessment"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(performance_profiles, "utc_now", lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc))


@pytest.mark.parametrize("role", ["owner", "athlete", "coach", "editor", "viewer"])
def test_existing_read_roles_and_zero_evidence(performance_client, role):
    client, engine = performance_client
    with Session(engine) as db:
        membership = db.scalar(select(UserAthleteMembership))
        membership.role = role
        athlete_id = str(membership.athlete_profile_id)
        db.commit()
    response = client.get(PATH, headers={"X-TriCoach-Athlete-Id": athlete_id})
    assert response.status_code == 200
    body = response.json()
    assert body["athlete_profile_id"] == athlete_id
    assert body["as_of_date"] == "2026-09-14"
    assert body["api_version"] == "0.8G.2C.8" and body["algorithm_version"] == "0.8G.2C.7"
    assert len(body["candidates"]) == 3 and body["summary"]["candidate_count"] == 0
    assert all(item["status"] == "REFERENCE_UNAVAILABLE" for item in body["candidates"])
    assert "supporting_session_ids" not in response.text and "profile_version_id" not in response.text


def test_unauthorized_and_revoked_membership(performance_client):
    client, engine = performance_client
    with Session(engine) as db:
        other = AthleteProfile(display_name="Other")
        db.add(other)
        db.flush()
        other_id = str(other.id)
        db.commit()
    assert client.get(PATH, headers={"X-TriCoach-Athlete-Id": other_id}).status_code == 403
    with Session(engine) as db:
        member = db.scalar(select(UserAthleteMembership))
        own_id = str(member.athlete_profile_id)
        member.is_active = False
        db.commit()
    assert client.get(PATH, headers={"X-TriCoach-Athlete-Id": own_id}).status_code == 403
    assert client.get(PATH).status_code == 404


def test_unauthenticated(performance_client):
    client, _ = performance_client
    def denied(): raise HTTPException(401, "authentication_required")
    client.app.dependency_overrides[get_current_user] = denied
    assert client.get(PATH).status_code == 401


@pytest.mark.parametrize("cutoff", ["bad", "2026-02-30", "2026-09-15", "1999-12-31"])
def test_invalid_or_future_cutoff(performance_client, cutoff):
    assert performance_client[0].get(PATH, params={"as_of_date": cutoff}).status_code == 422


def test_explicit_cutoff_and_reference_metadata_readonly(performance_client):
    client, engine = performance_client
    with Session(engine) as db:
        athlete = db.scalar(select(AthleteProfile))
        db.add(AthletePerformanceProfileVersion(athlete_profile_id=athlete.id,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc), data_origin="manual", algorithm_version="test",
            cycling_ftp_watts=200, running_threshold_pace_seconds_per_km=250, swimming_css_seconds_per_100m=110))
        db.commit()
    statements = []
    def check(connection, cursor, statement, *args):
        assert statement.lstrip().upper().startswith("SELECT")
        statements.append(statement)
    def no_commit(*args): raise AssertionError("GET must not commit")
    event.listen(engine, "before_cursor_execute", check)
    event.listen(engine, "commit", no_commit)
    try:
        first = client.get(PATH, params={"as_of_date": "2026-09-07"})
        assert first.status_code == 200
        assert len(statements) == 3  # membership + empty C.1 + C.7 profile/provenance
        assert client.get(PATH, params={"as_of_date": "2026-09-07"}).json() == first.json()
        body = first.json()
        assert body["window_start_date"] == "2026-06-15"
        assert [item["current_reference"]["value"] for item in body["candidates"]] == ["200.00", "250.00", "110.00"]
        assert all(item["status"] == "INSUFFICIENT_EVIDENCE" for item in body["candidates"])
        assert all(item["current_reference"]["quality"] is None for item in body["candidates"])
    finally:
        event.remove(engine, "before_cursor_execute", check)
        event.remove(engine, "commit", no_commit)


@pytest.mark.parametrize("scenario", ["candidate", "inconsistent", "maintain"])
def test_c7_projection_preserves_decisions_and_omits_internal_ids(performance_client, monkeypatch, scenario):
    from app.domains.planning.execution_evidence import TargetExecutionRelation
    facts = rows() if scenario == "candidate" else rows(actual=150) if scenario == "inconsistent" else rows(
        relation=TargetExecutionRelation.WITHIN_TARGET, actual=220)
    context = run(facts)
    def assemble(self, *, athlete_profile_id, as_of_date):
        return context.model_copy(update={"athlete_profile_id": athlete_profile_id, "as_of_date": as_of_date})
    monkeypatch.setattr(performance_profiles.CapabilityReassessmentAssembler, "assemble", assemble)
    response = performance_client[0].get(PATH)
    assert response.status_code == 200
    candidate = response.json()["candidates"][1]
    original = context.candidates[1]
    assert candidate["status"] == original.status
    assert candidate["confidence"] == original.confidence
    assert candidate["reason_codes"] == list(original.reason_codes)
    assert candidate["evidence"]["recent"] == original.evidence.recent
    assert "supporting_session_ids" not in candidate


def test_endpoint_and_projection_cannot_modify_planning(performance_client):
    from tests.test_planning_preview_artifact import artifact
    before = artifact().model_dump_json()
    CapabilityReassessmentResponse.from_context(run(rows()))
    assert performance_client[0].get(PATH).status_code == 200
    assert artifact().model_dump_json() == before


def test_authorized_athlete_switch_keeps_references_separate_and_viewer_cannot_edit(performance_client):
    client, engine = performance_client
    with Session(engine) as db:
        member = db.scalar(select(UserAthleteMembership))
        member.role = "viewer"
        first_id = member.athlete_profile_id
        other = AthleteProfile(display_name="Second", timezone="UTC")
        db.add(other)
        db.flush()
        second_id = other.id
        db.add(UserAthleteMembership(user_id=member.user_id, athlete_profile_id=second_id,
            role="viewer", is_active=True, is_default=False))
        for athlete_id, value in ((first_id, 200), (second_id, 300)):
            db.add(AthletePerformanceProfileVersion(athlete_profile_id=athlete_id,
                effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc), data_origin="manual",
                algorithm_version="test", cycling_ftp_watts=value))
        db.commit()
    for athlete_id, value in ((first_id, "200.00"), (second_id, "300.00")):
        headers = {"X-TriCoach-Athlete-Id": str(athlete_id)}
        response = client.get(PATH, headers=headers)
        assert response.status_code == 200
        assert response.json()["athlete_profile_id"] == str(athlete_id)
        assert response.json()["candidates"][0]["current_reference"]["value"] == value
        assert client.post("/athlete/performance-profile/versions", headers=headers,
            json={"effective_from": "2026-01-02T00:00:00Z", "data_origin": "manual", "cycling_ftp_watts": 999}).status_code == 403


@pytest.mark.parametrize("count", [1, 7])
def test_query_budget_including_authorization_is_constant(performance_client, count):
    from tests.test_execution_evidence import add_session, workout
    client, engine = performance_client
    with Session(engine) as db:
        athlete = db.scalar(select(AthleteProfile))
        for _ in range(count):
            add_session(db, athlete, day=date(2026, 9, 1), definition=workout())
        db.commit()
    statements = []
    def record(*args): statements.append(args[2])
    event.listen(engine, "before_cursor_execute", record)
    try:
        assert client.get(PATH).status_code == 200
        assert len(statements) == 5  # membership + three C.1 statements + one C.7
        assert sum("FROM activity_laps" in sql for sql in statements) == 1
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_default_cutoff_uses_selected_athlete_timezone(performance_client, monkeypatch):
    client, engine = performance_client
    with Session(engine) as db:
        db.scalar(select(AthleteProfile)).timezone = "Asia/Tokyo"
        db.commit()
    monkeypatch.setattr(performance_profiles, "utc_now", lambda: datetime(2026, 9, 14, 23, tzinfo=timezone.utc))
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json()["as_of_date"] == "2026-09-15"
