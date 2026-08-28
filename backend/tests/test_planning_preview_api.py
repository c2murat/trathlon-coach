from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi.testclient import TestClient

from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.routes import planning_previews as routes
from app.db.models import AthleteProfile, TrainingPlan, TrainingPlanPreview
from app.db.session import get_db_session
from app.main import create_app
from tests.test_planning_preview_application import seeded


def client_fixture():
    engine, preview_id, athlete_id, user_id, source = seeded()
    session = Session(engine)
    athlete = session.get(AthleteProfile, athlete_id)
    current = CurrentAthleteContext(user_id=user_id, athlete_id=athlete_id, role="athlete", athlete_profile=athlete, membership=None)
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[routes.read] = lambda: current
    app.dependency_overrides[routes.generate] = lambda: current
    return TestClient(app), session, preview_id, source


def test_get_preview_and_accept_api_return_same_artifact_and_plan():
    client, session, preview_id, source = client_fixture()
    try:
        response = client.get(f"/planning/previews/{preview_id}")
        assert response.status_code == 200
        assert response.json()["artifact"]["fingerprint"] == source.fingerprint
        accepted = client.post(
            f"/planning/previews/{preview_id}/accept",
            json={"expected_fingerprint": source.fingerprint},
        )
        assert accepted.status_code == 200
        plan_id = accepted.json()["training_plan_id"]
        assert client.post(f"/planning/previews/{preview_id}/accept", json={}).json()["training_plan_id"] == plan_id
        assert client.get(f"/planning/previews/{preview_id}").json()["accepted_training_plan_id"] == plan_id
        assert client.get(f"/training-plans/{plan_id}").status_code == 200
        activated = client.post(f"/training-plans/{plan_id}/activate")
        assert activated.status_code == 200
        assert activated.json()["status"] == "active"
        assert client.post(f"/training-plans/{plan_id}/activate").json()["status"] == "active"
        completed = client.post(f"/training-plans/{plan_id}/complete")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        invalid = client.post(f"/training-plans/{plan_id}/archive")
        assert invalid.status_code == 409
        assert invalid.json()["detail"]["code"] == "training_plan_invalid_transition"
    finally:
        session.close()


def test_accept_api_rejects_fingerprint_mismatch_without_plan():
    client, session, preview_id, _ = client_fixture()
    try:
        response = client.post(f"/planning/previews/{preview_id}/accept", json={"expected_fingerprint": "0" * 64})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "preview_fingerprint_mismatch"
    finally:
        session.close()


def test_accept_api_returns_controlled_overlap_conflict():
    client, session, preview_id, source = client_fixture()
    try:
        existing = TrainingPlan(
            athlete_profile_id=source.athlete_id, title="Existing",
            start_date=source.plan_start, end_date=source.plan_end,
            status="draft", origin="human",
        )
        session.add(existing); session.commit()
        response = client.post(f"/planning/previews/{preview_id}/accept", json={"expected_fingerprint": source.fingerprint})
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code": "training_plan_overlap",
            "existing_training_plan_id": str(existing.id),
            "existing_start_date": source.plan_start.isoformat(),
            "existing_end_date": source.plan_end.isoformat(),
        }
        assert session.get(TrainingPlanPreview, preview_id).status == "pending"
    finally:
        session.close()


def test_preview_and_training_plan_get_are_athlete_scoped():
    client, session, preview_id, source = client_fixture()
    try:
        plan_id = client.post(f"/planning/previews/{preview_id}/accept", json={"expected_fingerprint": source.fingerprint}).json()["training_plan_id"]
        other = AthleteProfile(display_name="Other API", timezone="Europe/Madrid", unit_system="metric")
        session.add(other); session.commit()
        original = client.app.dependency_overrides[routes.read]()
        foreign = CurrentAthleteContext(user_id=original.user_id, athlete_id=other.id, role="viewer", athlete_profile=other, membership=None)
        client.app.dependency_overrides[routes.read] = lambda: foreign
        assert client.get(f"/planning/previews/{preview_id}").status_code == 403
        assert client.get(f"/training-plans/{plan_id}").status_code == 404
        client.app.dependency_overrides[routes.generate] = lambda: foreign
        assert client.post(f"/training-plans/{plan_id}/activate").status_code == 404
    finally:
        session.close()


def test_planned_sessions_range_is_athlete_scoped_and_validated():
    client, session, preview_id, source = client_fixture()
    try:
        client.post(f"/planning/previews/{preview_id}/accept", json={"expected_fingerprint": source.fingerprint})
        response = client.get(f"/training-plans/sessions?start_date={source.plan_start}&end_date={source.plan_end}")
        assert response.status_code == 200
        assert response.json()
        assert all(source.plan_start.isoformat() <= row["scheduled_date"] <= source.plan_end.isoformat() for row in response.json())
        assert client.get(f"/training-plans/sessions?start_date={source.plan_end}&end_date={source.plan_start}").status_code == 422
        accepted_plan = session.scalar(select(TrainingPlan).where(TrainingPlan.source_preview_id == preview_id))
        accepted_plan.status = "active"; session.commit()
        assert client.get(f"/training-plans/sessions?start_date={source.plan_start}&end_date={source.plan_end}").json()
        accepted_plan.status = "completed"; session.commit()
        assert client.get(f"/training-plans/sessions?start_date={source.plan_start}&end_date={source.plan_end}").json() == []
        accepted_plan.status = "archived"; session.commit()
        assert client.get(f"/training-plans/sessions?start_date={source.plan_start}&end_date={source.plan_end}").json() == []

        other = AthleteProfile(display_name="Other range", timezone="Europe/Madrid", unit_system="metric")
        session.add(other); session.commit()
        original = client.app.dependency_overrides[routes.read]()
        client.app.dependency_overrides[routes.read] = lambda: CurrentAthleteContext(user_id=original.user_id, athlete_id=other.id, role="viewer", athlete_profile=other, membership=None)
        assert client.get(f"/training-plans/sessions?start_date={source.plan_start}&end_date={source.plan_end}").json() == []
    finally:
        session.close()


def test_activate_api_returns_controlled_active_conflict():
    client, session, preview_id, source = client_fixture()
    try:
        plan_id = client.post(f"/planning/previews/{preview_id}/accept", json={"expected_fingerprint": source.fingerprint}).json()["training_plan_id"]
        existing = TrainingPlan(athlete_profile_id=source.athlete_id,title="Active",start_date=source.plan_start,end_date=source.plan_end,status="active",origin="human")
        session.add(existing);session.commit()
        response = client.post(f"/training-plans/{plan_id}/activate")
        assert response.status_code == 409
        assert response.json()["detail"] == {
            "code":"training_plan_active_conflict",
            "existing_training_plan_id":str(existing.id),
            "existing_start_date":source.plan_start.isoformat(),
            "existing_end_date":source.plan_end.isoformat(),
        }
        assert session.get(TrainingPlan, UUID(plan_id)).status == "draft"
    finally:
        session.close()
