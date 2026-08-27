from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.routes import planning_previews as routes
from app.db.models import AthleteProfile
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
        assert client.get(f"/training-plans/{plan_id}").status_code == 403
    finally:
        session.close()
