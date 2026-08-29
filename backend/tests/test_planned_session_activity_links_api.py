from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.routes import planned_session_activity_links as routes
from app.db.session import get_db_session
from app.main import create_app
from tests.test_planned_session_activity_matching import activity, athlete, db, planned


def api_client(db: Session, owner, role="athlete"):
    current=CurrentAthleteContext(user_id=owner.id,athlete_id=owner.id,role=role,athlete_profile=owner,membership=None)
    app=create_app();app.dependency_overrides[get_db_session]=lambda:db;app.dependency_overrides[routes.read]=lambda:current;app.dependency_overrides[routes.manage]=lambda:current
    return TestClient(app)


def test_link_list_candidates_and_idempotent_unlink_api(db):
    owner=athlete(db);session=planned(db,owner);actual=activity(db,owner);db.commit();client=api_client(db,owner)
    candidates=client.get(f"/training-plans/sessions/{session.id}/activity-candidates")
    assert candidates.status_code==200 and candidates.json()[0]["id"]==str(actual.id)
    created=client.post(f"/training-plans/sessions/{session.id}/activity-links",json={"completed_activity_id":str(actual.id)})
    assert created.status_code==201 and created.json()["match_source"]=="manual"
    retry=client.post(f"/training-plans/sessions/{session.id}/activity-links",json={"completed_activity_id":str(actual.id)})
    assert retry.status_code==201 and retry.json()["id"]==created.json()["id"]
    assert len(client.get(f"/training-plans/sessions/{session.id}/activity-links").json())==1
    assert client.delete(f"/training-plans/sessions/{session.id}/activity-links/{actual.id}").status_code==204
    assert client.delete(f"/training-plans/sessions/{session.id}/activity-links/{actual.id}").status_code==204


def test_api_scope_conflict_and_automatic_ambiguity(db):
    owner=athlete(db);other=athlete(db,"B");session=planned(db,owner);foreign=activity(db,other);activity(db,owner,duration=2640);activity(db,owner,hour=10,duration=2760);db.commit();client=api_client(db,owner)
    assert client.get(f"/training-plans/sessions/{planned(db,other).id}/activity-links").status_code==404
    response=client.post(f"/training-plans/sessions/{session.id}/activity-links",json={"completed_activity_id":str(foreign.id)})
    assert response.status_code==404 and response.json()["detail"]["code"]=="activity_not_found"
    automatic=client.post(f"/training-plans/sessions/{session.id}/auto-match")
    assert automatic.status_code==200 and automatic.json()["classification"]=="ambiguous" and automatic.json()["link"] is None
