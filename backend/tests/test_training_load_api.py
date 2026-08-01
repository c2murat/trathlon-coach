from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.models import CompletedActivity, ActivityTrainingLoad
from app.db.base import utc_now
from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from test_activity_reads import activity_client

def row(a,version="0.7b.1",load=72.45): return ActivityTrainingLoad(completed_activity_id=a.id,algorithm_version=version,load_value=load,method="cycling_power",unit="load_points",coverage="complete",quality="high",reason=None,duration_seconds=3600,effective_intensity=.85,reference_value=250,reference_metric="W",source_metrics={"average_power_watts":True},warnings=[],calculated_at=utc_now())
def test_get_persisted_and_no_calculation(activity_client):
 c,e=activity_client
 with Session(e) as s: a=s.query(CompletedActivity).first(); s.add(row(a)); s.commit(); aid=str(a.id)
 r=c.get(f"/activities/{aid}/training-load"); assert r.status_code==200 and r.json()["load_value"]==72.45 and "athlete_id" not in r.json() and "completed_activity_id" not in r.json()

def test_get_missing_is_404_and_does_not_create(activity_client):
 c,e=activity_client
 with Session(e) as s: a=s.query(CompletedActivity).first(); aid=str(a.id)
 assert c.get(f"/activities/{aid}/training-load").status_code==404
 with Session(e) as s: assert s.query(ActivityTrainingLoad).count()==0

def test_get_version_and_invalid_version(activity_client):
 c,e=activity_client
 with Session(e) as s: a=s.query(CompletedActivity).first(); s.add(row(a,"old",1)); s.add(row(a,"0.7b.1",2)); s.commit(); aid=str(a.id)
 assert c.get(f"/activities/{aid}/training-load",params={"algorithm_version":"old"}).json()["load_value"]==1
 assert c.get(f"/activities/{aid}/training-load",params={"algorithm_version":"missing"}).status_code==404
 assert c.get(f"/activities/{aid}/training-load",params={"algorithm_version":"x"*33}).status_code==422

def test_get_other_activity_is_404(activity_client):
 c,e=activity_client
 with Session(e) as s: a=s.query(CompletedActivity).filter_by(external_activity_id="private-other-user").one()
 assert c.get(f"/activities/{a.id}/training-load").status_code==404

def test_post_calculates_and_is_idempotent(activity_client):
 c,e=activity_client
 with Session(e) as s: a=s.query(CompletedActivity).first(); aid=str(a.id)
 r=c.post(f"/activities/{aid}/training-load/recalculate"); assert r.status_code==200; first=r.json(); assert first["algorithm_version"]=="0.7b.1"
 r=c.post(f"/activities/{aid}/training-load/recalculate"); assert r.status_code==200
 with Session(e) as s: assert s.query(ActivityTrainingLoad).filter_by(completed_activity_id=a.id,algorithm_version="0.7b.1").count()==1

def test_post_other_activity_404(activity_client):
 c,e=activity_client
 with Session(e) as s: a=s.query(CompletedActivity).filter_by(external_activity_id="private-other-user").one()
 assert c.post(f"/activities/{a.id}/training-load/recalculate").status_code==404

def test_openapi_contract(activity_client):
 c,_=activity_client; schema=c.get("/openapi.json").json(); get=schema["paths"]["/activities/{activity_id}/training-load"]["get"]; assert "algorithm_version" in str(get); assert "TrainingLoadResponse" in str(get)
