from datetime import datetime,timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.api.dependencies.providers import get_strava_evidence_manager
from app.db.base import Base,utc_now
from app.db.models import ActivityEvidenceState,ActivityStream,AthleteProfile,CompletedActivity,User
from app.db.session import get_db_session
from app.integrations.strava.activity_evidence import EvidenceJobView,EvidenceJobNotFoundError
from app.main import create_app
class Manager:
 def __init__(self):self.id=uuid4();self.scheduled=[]
 def create_job(self,*a,**kw):now=datetime.now(timezone.utc);return EvidenceJobView(self.id,"queued",1,0,0,0,0,0,None,None,now,None,None,None,False)
 def schedule(self,j):self.scheduled.append(j)
 def job_for_user(self,user,j):
  if j!=self.id:raise EvidenceJobNotFoundError
  now=datetime.now(timezone.utc);return EvidenceJobView(j,"succeeded",1,2,3,1,0,0,str(uuid4()),now,now,now,None,None,False)
def test_evidence_job_endpoints_are_safe_and_bounded():
 app=create_app();m=Manager();app.dependency_overrides[get_strava_evidence_manager]=lambda:m
 with TestClient(app) as c:
  started=c.post("/integrations/strava/evidence",json={"activity_ids":[str(uuid4())],"include_laps":True,"include_streams":True,"include_location":False});assert started.status_code==202 and set(started.json())=={"job_id","status"}
  status=c.get(f"/integrations/strava/evidence/{m.id}");assert status.status_code==200 and "streams" not in status.json() and "laps" not in status.json();assert "no-store" in status.headers["cache-control"]
def test_evidence_read_is_owned_bounded_and_coordinate_free_when_disabled():
 engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);now=utc_now()
 with Session(engine) as s:
  user=User(id=LOCAL_MVP_USER_ID,email="a@x.invalid",normalized_email="a@x.invalid",auth_subject="a");athlete=AthleteProfile(user=user);activity=CompletedActivity(athlete=athlete,external_activity_id="1",source_summary="strava",sport="running",name="Run",start_at=now,timezone="UTC",elapsed_time_s=1);s.add_all([user,athlete,activity]);s.flush();s.add(ActivityStream(completed_activity_id=activity.id,stream_type="time",original_sample_count=2000,sample_count=2,values=[0,1],fetched_at=now,retention_class="standard",checksum="x",version=1));s.add(ActivityStream(completed_activity_id=activity.id,stream_type="latlng",original_sample_count=2,sample_count=2,values=[[40,-3],[41,-4]],fetched_at=now,retention_class="location",checksum="y",version=1));s.add(ActivityEvidenceState(completed_activity_id=activity.id,status="succeeded",streams_fetched_at=now,location_retained=True));s.commit();aid=activity.id
 app=create_app()
 def db():
  with Session(engine) as s:yield s
 app.dependency_overrides[get_db_session]=db
 with TestClient(app) as c:
  response=c.get(f"/activities/{aid}/evidence");assert response.status_code==200;body=response.json();assert body["streams"]["time"]["values"]==[0,1];assert "latlng" not in body["streams"] and body["route"]["polyline"] is None and body["location_status"]=="privacy_disabled"
  assert c.get(f"/activities/{uuid4()}/evidence").status_code==404
 engine.dispose()
