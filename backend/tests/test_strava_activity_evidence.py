import asyncio
from datetime import timedelta
from uuid import uuid4
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine,select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from app.application.queries.activity_evidence import ActivityEvidenceQuery
from app.db.base import Base,utc_now
from app.db.models import ActivityEvidenceState,ActivityLap,ActivityRouteEvidence,ActivityStream,AthleteProfile,CompletedActivity,IntegrationAccount,OAuthCredential,User
from app.integrations.strava.activity_evidence import EvidenceSelectionError,StravaActivityEvidenceManager
from app.providers.base import AuthenticationError,TemporaryProviderError
from app.providers.strava.activity_client import StravaActivityDetail,StravaActivityLaps,StravaActivityRateLimitError,StravaActivityStreams,StravaRateLimitSnapshot
EMPTY=StravaRateLimitSnapshot(None,None,None,None)
class Tokens:
 def __init__(self,error=None):self.error=error
 async def access_token(self,_):
  if self.error:raise self.error
  return SecretStr("stored-secret")
class Client:
 def __init__(self,error=None,malformed=False):self.error=error;self.malformed=malformed;self.calls=[]
 async def fetch_activity_laps(self,**kw):
  self.calls.append(("laps",kw["external_activity_id"]));
  if self.error:raise self.error
  return StravaActivityLaps(({"id":1,"lap_index":1,"elapsed_time":60,"moving_time":55,"distance":400.0},),EMPTY)
 async def fetch_activity_streams(self,**kw):
  self.calls.append(("streams",kw["stream_types"]));
  if self.error:raise self.error
  hr=[100,"bad",120] if self.malformed else [100,110,120]
  return StravaActivityStreams({"time":{"data":[0,30,60]},"distance":{"data":[0,200,400]},"heartrate":{"data":hr},"latlng":{"data":[[40,-3],[40.1,-3.1],[40.2,-3.2]]}},EMPTY)
 async def fetch_activity_detail(self,**kw):return StravaActivityDetail({"map":{"summary_polyline":"encoded-route"}},EMPTY)
@pytest.fixture
def db(tmp_path):
 engine=create_engine(f"sqlite+pysqlite:///{tmp_path/'evidence.sqlite3'}",connect_args={"check_same_thread":False});Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False);now=utc_now()
 with factory() as s:
  user=User(email="a@x.invalid",normalized_email="a@x.invalid",auth_subject="a");athlete=AthleteProfile(user=user);account=IntegrationAccount(athlete=athlete,provider="strava",external_account_id="456",status="active",scopes=[]);credential=OAuthCredential(integration_account=account,access_token="secret",refresh_token="refresh",expires_at=now+timedelta(hours=1),scopes=[]);a1=CompletedActivity(athlete=athlete,source_integration_account=account,external_activity_id="101",source_summary="strava",sport="running",name="Run",start_at=now,timezone="UTC",elapsed_time_s=60,enrichment_status="succeeded",provider_updated_at=now);a2=CompletedActivity(athlete=athlete,source_integration_account=account,external_activity_id="102",source_summary="strava",sport="cycling",name="Ride",start_at=now-timedelta(days=1),timezone="UTC",elapsed_time_s=60,enrichment_status="succeeded",provider_updated_at=now);other=User(email="b@x.invalid",normalized_email="b@x.invalid",auth_subject="b");oa=AthleteProfile(user=other);foreign=CompletedActivity(athlete=oa,external_activity_id="999",source_summary="strava",sport="running",name="Secret",start_at=now,timezone="UTC",elapsed_time_s=1,enrichment_status="succeeded");s.add_all([user,athlete,account,credential,a1,a2,other,oa,foreign]);s.commit();ids=user.id,a1.id,a2.id,foreign.id,account.id
 yield factory,ids;engine.dispose()
def manager(db,client=None,**kw):return StravaActivityEvidenceManager(session_factory=db[0],client=client or Client(),token_service=kw.pop("tokens",Tokens()),**kw)
def test_first_import_and_repeat_upsert_are_idempotent(db):
 factory,(user,a1,_,_,_)=db;m=manager(db);job=m.create_job(user,activity_ids=[a1],include_laps=True,include_streams=True,include_location=False);asyncio.run(m.run(job.job_id));view=m.job_for_user(user,job.job_id);assert view.status=="succeeded" and view.laps_imported==1 and view.streams_imported==3
 with factory() as s:assert len(s.scalars(select(ActivityLap)).all())==1 and len(s.scalars(select(ActivityStream)).all())==3
 m2=manager(db);j2=m2.create_job(user,activity_ids=[a1],include_laps=True,include_streams=True,include_location=False);asyncio.run(m2.run(j2.job_id))
 with factory() as s:assert len(s.scalars(select(ActivityLap)).all())==1 and len(s.scalars(select(ActivityStream)).all())==3
def test_default_selection_uses_freshness_state(db):
 factory,(user,a1,a2,_,_)=db;now=utc_now()
 with factory() as s:s.add(ActivityEvidenceState(completed_activity_id=a1,status="succeeded",source_updated_at=now,laps_fetched_at=now,streams_fetched_at=now));s.add(ActivityEvidenceState(completed_activity_id=a2,status="succeeded",source_updated_at=now,laps_fetched_at=now,streams_fetched_at=now));s.commit()
 assert manager(db).create_job(user,activity_ids=None,include_laps=True,include_streams=True,include_location=False).selected_count==0
 with factory() as s:s.get(CompletedActivity,a2).provider_updated_at=now+timedelta(seconds=1);s.commit()
 assert manager(db).create_job(user,activity_ids=None,include_laps=True,include_streams=True,include_location=False).selected_count==1
def test_partial_stream_success_keeps_valid_aligned_streams(db):
 factory,(user,a1,_,_,_)=db;m=manager(db,Client(malformed=True));j=m.create_job(user,activity_ids=[a1],include_laps=False,include_streams=True,include_location=False);asyncio.run(m.run(j.job_id));view=m.job_for_user(user,j.job_id);assert view.status=="partially_succeeded" and view.error_category=="invalid_stream"
 with factory() as s:assert {x.stream_type for x in s.scalars(select(ActivityStream)).all()}=={"time","distance"}
@pytest.mark.parametrize("error,category",[(TemporaryProviderError("temp"),"provider_temporary"),(StravaActivityRateLimitError(retry_after_seconds=20,rate_limit=EMPTY),"rate_limited")])
def test_temporary_and_rate_limit_pause(db,error,category):
 _,(user,a1,_,_,_)=db;m=manager(db,Client(error));j=m.create_job(user,activity_ids=[a1],include_laps=True,include_streams=False,include_location=False);asyncio.run(m.run(j.job_id));v=m.job_for_user(user,j.job_id);assert v.status=="retry_scheduled" and v.error_category==category and v.next_resume_at
def test_invalid_credentials_require_reconnect(db):
 factory,(user,a1,_,_,account)=db;m=manager(db,tokens=Tokens(AuthenticationError("no")));j=m.create_job(user,activity_ids=[a1],include_laps=True,include_streams=False,include_location=False);asyncio.run(m.run(j.job_id));assert m.job_for_user(user,j.job_id).status=="failed"
 with factory() as s:assert s.get(IntegrationAccount,account).status=="refresh_required"
def test_ownership_and_detail_enrichment_required(db):
 _,(user,a1,_,foreign,_)=db;m=manager(db)
 with pytest.raises(EvidenceSelectionError):m.create_job(user,activity_ids=[foreign],include_laps=True,include_streams=False,include_location=False)
def test_location_disabled_rejects_request_and_cleans_existing(db):
 factory,(user,a1,_,_,_)=db
 with factory() as s:s.add(ActivityStream(completed_activity_id=a1,stream_type="latlng",original_sample_count=1,sample_count=1,values=[[40,-3]],fetched_at=utc_now(),retention_class="location",checksum="x",version=1));s.add(ActivityRouteEvidence(completed_activity_id=a1,available=True,summary_polyline="secret-route",sample_count=1,fetched_at=utc_now(),retention_class="location",version=1));s.commit()
 m=manager(db,location_retention_enabled=False)
 with pytest.raises(EvidenceSelectionError):m.create_job(user,activity_ids=[a1],include_laps=False,include_streams=True,include_location=True)
 m.cleanup_location_for_user(user)
 with factory() as s:assert not s.scalars(select(ActivityStream).where(ActivityStream.stream_type=="latlng")).all() and s.scalar(select(ActivityRouteEvidence)) is None
def test_location_enabled_persists_route_and_read_api_hides_when_disabled(db):
 factory,(user,a1,_,_,_)=db;m=manager(db,location_retention_enabled=True);j=m.create_job(user,activity_ids=[a1],include_laps=False,include_streams=True,include_location=True);asyncio.run(m.run(j.job_id))
 with factory() as s:
  visible=ActivityEvidenceQuery(s,location_enabled=True,max_samples=10).for_user(user,a1);hidden=ActivityEvidenceQuery(s,location_enabled=False,max_samples=10).for_user(user,a1)
  assert visible["route"]["polyline"]=="encoded-route" and "latlng" not in visible["streams"]
  assert hidden["route"]["polyline"] is None and hidden["location_status"]=="privacy_disabled"
def test_database_failure_rolls_back_current_activity_only(db):
 factory,(user,a1,a2,_,_)=db;m=manager(db);original=m._persist;calls=0
 def fail_first(*args,**kwargs):
  nonlocal calls;calls+=1
  if calls==1:raise SQLAlchemyError("db")
  return original(*args,**kwargs)
 m._persist=fail_first;j=m.create_job(user,activity_ids=[a1,a2],include_laps=True,include_streams=False,include_location=False);asyncio.run(m.run(j.job_id));v=m.job_for_user(user,j.job_id);assert v.status=="partially_succeeded" and v.activities_completed==1 and v.failed_count==1
 with factory() as s:assert not s.scalars(select(ActivityLap).where(ActivityLap.completed_activity_id==a1)).all() and s.scalars(select(ActivityLap).where(ActivityLap.completed_activity_id==a2)).all()
