from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies.athlete_permissions import AthleteCapability, athlete_has_capability
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.routes import planned_session_activity_links as routes
from app.db.models import ManualStrengthSession, TrainingPlan, User
from app.db.session import get_db_session
from app.main import create_app
from tests.test_planned_session_activity_matching import activity, athlete, db, planned


def user(db: Session, suffix="api"):
    row=User(email=f"{suffix}@example.invalid",normalized_email=f"{suffix}@example.invalid",auth_subject=f"auth-{suffix}",timezone="Europe/Madrid")
    db.add(row);db.flush();return row


def api_client(db: Session, owner, role="athlete", actor=None):
    current=CurrentAthleteContext(user_id=(actor or owner).id,athlete_id=owner.id,role=role,athlete_profile=owner,membership=None)
    def read_current():
        if not athlete_has_capability(current,AthleteCapability.READ_TRAINING_PLANNING):
            raise HTTPException(403,detail={"code":"athlete_permission_denied"})
        return current
    def manage_current():
        if not athlete_has_capability(current,AthleteCapability.GENERATE_TRAINING_PLAN):
            raise HTTPException(403,detail={"code":"athlete_permission_denied"})
        return current
    app=create_app();app.dependency_overrides[get_db_session]=lambda:db;app.dependency_overrides[routes.read]=read_current;app.dependency_overrides[routes.manage]=manage_current
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


def test_completed_activity_candidates_cover_same_week_and_exclude_linked(db):
    owner=athlete(db);session=planned(db,owner,day=date(2026,1,10),sport="cycling",duration=3600,distance=30000)
    same_week=activity(db,owner,day=5,sport="cycling",duration=4320,distance=34800)
    activity(db,owner,day=5,sport="running",duration=4320,distance=10000)
    db.commit();client=api_client(db,owner)
    candidates=client.get(f"/training-plans/sessions/{session.id}/activity-candidates")
    assert candidates.status_code==200,candidates.text
    assert [item["id"] for item in candidates.json()]==[str(same_week.id)]
    linked=client.post(f"/training-plans/sessions/{session.id}/activity-links",json={"completed_activity_id":str(same_week.id)})
    assert linked.status_code==201,linked.text
    assert client.get(f"/training-plans/sessions/{session.id}/activity-candidates").json()==[]


def test_api_scope_conflict_and_automatic_ambiguity(db):
    owner=athlete(db);other=athlete(db,"B");session=planned(db,owner);foreign=activity(db,other);activity(db,owner,duration=2640);activity(db,owner,hour=10,duration=2760);db.commit();client=api_client(db,owner)
    assert client.get(f"/training-plans/sessions/{planned(db,other).id}/activity-links").status_code==404
    response=client.post(f"/training-plans/sessions/{session.id}/activity-links",json={"completed_activity_id":str(foreign.id)})
    assert response.status_code==404 and response.json()["detail"]["code"]=="activity_not_found"
    automatic=client.post(f"/training-plans/sessions/{session.id}/auto-match")
    assert automatic.status_code==200 and automatic.json()["classification"]=="ambiguous" and automatic.json()["link"] is None


def test_api_reschedules_same_week_and_blocks_readonly_role(db):
    owner=athlete(db);actor=user(db);plan=TrainingPlan(athlete_profile_id=owner.id,title="Plan",start_date=date(2026,9,21),end_date=date(2026,9,27),status="active",origin="ai")
    db.add(plan);db.flush();session=planned(db,owner,day=date(2026,9,21));session.training_plan_id=plan.id;db.commit()
    viewer=api_client(db,owner,role="viewer",actor=actor)
    assert viewer.post(f"/training-plans/sessions/{session.id}/reschedule",json={"date":"2026-09-23"}).status_code==403
    client=api_client(db,owner,actor=actor)
    response=client.post(f"/training-plans/sessions/{session.id}/reschedule",json={"date":"2026-09-23"})
    assert response.status_code==200,response.text
    assert response.json()["scheduled_date"]=="2026-09-23"
    assert db.get(type(session),session.id).scheduled_date==date(2026,9,23)
    outside=client.post(f"/training-plans/sessions/{session.id}/reschedule",json={"date":"2026-09-28"})
    assert outside.status_code==409 and outside.json()["detail"]["code"]=="new_date_outside_session_week"


def test_api_lists_and_links_manual_strength_candidate_across_days(db):
    owner=athlete(db);actor=user(db);plan=TrainingPlan(athlete_profile_id=owner.id,title="Plan",start_date=date(2026,9,21),end_date=date(2026,9,27),status="active",origin="ai")
    db.add(plan);db.flush();session=planned(db,owner,day=date(2026,9,21),sport="strength",duration=2400,distance=None);session.training_plan_id=plan.id
    manual=ManualStrengthSession(athlete_id=owner.id,started_at=datetime(2026,9,22,15,42,tzinfo=timezone.utc),timezone_name="Europe/Madrid",duration_minutes=60,body_regions=["full_body"],perceived_exertion=9)
    db.add(manual);db.commit();client=api_client(db,owner,actor=actor)
    candidates=client.get(f"/training-plans/sessions/{session.id}/activity-candidates")
    assert candidates.status_code==200,candidates.text
    body=candidates.json()
    assert any(item["id"]==str(manual.id) and item["source_type"]=="manual_strength" and item["local_date"]=="2026-09-22" for item in body)
    linked=client.post(f"/training-plans/sessions/{session.id}/manual-strength-links",json={"manual_strength_session_id":str(manual.id)})
    assert linked.status_code==201,linked.text
    assert linked.json()["completed_activity_id"] is None
    assert linked.json()["manual_strength_session_id"]==str(manual.id)
    links=client.get(f"/training-plans/sessions/{session.id}/activity-links").json()
    assert links[0]["activity"]["duration_seconds"]==3600
