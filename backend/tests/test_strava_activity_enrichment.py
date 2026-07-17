from __future__ import annotations
import asyncio
from datetime import timedelta
from uuid import uuid4
import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from app.db.base import Base, utc_now
from app.db.models import AthleteProfile, CompletedActivity, IntegrationAccount, OAuthCredential, User
from app.integrations.strava.activity_enrichment import EnrichmentSelectionError, StravaActivityEnrichmentManager
from app.providers.base import AuthenticationError, TemporaryProviderError
from app.providers.strava.activity_client import StravaActivityDetail, StravaActivityRateLimitError, StravaActivityUnavailableError, StravaRateLimitSnapshot
EMPTY=StravaRateLimitSnapshot(None,None,None,None)
def payload(external_id="101",**values):
 p={"id":int(external_id),"athlete":{"id":456},"description":"Provider description","calories":500.0,"device_name":"Edge","gear_id":"b1","perceived_exertion":6,"max_watts":350};p.update(values);return p
class Tokens:
 def __init__(self,error=None):self.error=error;self.calls=0
 async def access_token(self,_):
  self.calls+=1
  if self.error:raise self.error
  return SecretStr("stored-secret")
class Details:
 def __init__(self,values=None,error=None):self.values=list(values or []);self.error=error;self.calls=[]
 async def fetch_activity_detail(self,**kwargs):
  self.calls.append({k:v for k,v in kwargs.items() if k!="access_token"})
  if self.error:raise self.error
  value=self.values.pop(0) if self.values else payload(kwargs["external_activity_id"])
  if isinstance(value,Exception):raise value
  return StravaActivityDetail(value,EMPTY)
@pytest.fixture
def enrichment_db(tmp_path):
 engine=create_engine(f"sqlite+pysqlite:///{tmp_path/'enrichment.sqlite3'}",connect_args={"check_same_thread":False});Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,expire_on_commit=False);now=utc_now()
 with factory() as s:
  user=User(email="local@example.invalid",normalized_email="local@example.invalid",auth_subject="local",timezone="Europe/Madrid");athlete=AthleteProfile(user=user,timezone="Europe/Madrid",unit_system="metric");account=IntegrationAccount(athlete=athlete,provider="strava",external_account_id="456",status="active",scopes=["read","activity:read_all"]);credential=OAuthCredential(integration_account=account,access_token="stored-secret",refresh_token="refresh-secret",expires_at=now+timedelta(hours=1),scopes=["read","activity:read_all"]);other=User(email="other@example.invalid",normalized_email="other@example.invalid",auth_subject="other");other_athlete=AthleteProfile(user=other)
  a1=CompletedActivity(athlete=athlete,source_integration_account=account,external_activity_id="101",source_summary="strava",sport="cycling",name="Ride",start_at=now,timezone="UTC",elapsed_time_s=1000,description="Local note",rpe=8,provider_updated_at=now)
  a2=CompletedActivity(athlete=athlete,source_integration_account=account,external_activity_id="102",source_summary="strava",sport="running",name="Run",start_at=now-timedelta(days=1),timezone="UTC",elapsed_time_s=500)
  foreign=CompletedActivity(athlete=other_athlete,external_activity_id="999",source_summary="strava",sport="running",name="Secret",start_at=now,timezone="UTC",elapsed_time_s=1)
  s.add_all([user,athlete,account,credential,other,other_athlete,a1,a2,foreign]);s.commit();ids=(user.id,a1.id,a2.id,foreign.id,account.id)
 yield factory,ids;engine.dispose()
def make(db,values=None,error=None,tokens=None):
 factory,_=db;client=Details(values,error);manager=StravaActivityEnrichmentManager(session_factory=factory,activity_client=client,token_service=tokens or Tokens(),retry_seconds=30);return manager,client
def test_first_enrichment_preserves_local_fields_and_repeated_run_is_idempotent(enrichment_db):
 factory,(user,a1,_,_,_)=enrichment_db;m,client=make(enrichment_db,[payload()]);job=m.create_job(user,activity_ids=[a1]);asyncio.run(m.run(job.job_id))
 with factory() as s:
  a=s.get(CompletedActivity,a1);assert a.provider_description=="Provider description" and a.description=="Local note" and a.rpe==8;first=a.enriched_at
  view=m.job_for_user(user,job.job_id);assert view.status=="succeeded" and view.enriched_count==1 and view.updated_count==1
 m2,_=make(enrichment_db,[payload()]);job2=m2.create_job(user,activity_ids=[a1]);asyncio.run(m2.run(job2.job_id))
 with factory() as s:assert s.get(CompletedActivity,a1).enriched_at>=first
 assert m2.job_for_user(user,job2.job_id).skipped_count==1
def test_default_selection_and_summary_update_trigger_reenrichment(enrichment_db):
 factory,(user,a1,a2,_,_)=enrichment_db
 with factory() as s:a=s.get(CompletedActivity,a1);a.enriched_at=utc_now();a.enrichment_status="succeeded";a.provider_updated_at=a.enriched_at-timedelta(seconds=1);s.commit()
 m,_=make(enrichment_db,[payload("102")]);job=m.create_job(user,limit=10);assert job.selected_count==1;asyncio.run(m.run(job.job_id))
 with factory() as s:a=s.get(CompletedActivity,a1);a.provider_updated_at=a.enriched_at+timedelta(seconds=1);s.commit()
 m2,_=make(enrichment_db,[payload("101")]);assert m2.create_job(user,limit=1).selected_count==1
def test_selected_ids_are_owned_and_batch_limits_apply(enrichment_db):
 _,(user,a1,_,foreign,_)=enrichment_db;m,_=make(enrichment_db)
 with pytest.raises(EnrichmentSelectionError):m.create_job(user,activity_ids=[foreign])
 with pytest.raises(EnrichmentSelectionError):m.create_job(user,limit=51)
 assert m.create_job(user,activity_ids=[a1],limit=1).selected_count==1
@pytest.mark.parametrize("error,expected",[(TemporaryProviderError("temporary"),"provider_temporary"),(StravaActivityRateLimitError(retry_after_seconds=17,rate_limit=EMPTY),"rate_limited")])
def test_temporary_and_rate_failures_pause_with_checkpoint(enrichment_db,error,expected):
 _,(user,a1,_,_,_)=enrichment_db;m,_=make(enrichment_db,error=error);job=m.create_job(user,activity_ids=[a1]);asyncio.run(m.run(job.job_id));view=m.job_for_user(user,job.job_id);assert view.status=="retry_scheduled" and view.next_resume_at and view.error_category==expected and view.enriched_count==0
def test_invalid_credentials_stop_and_require_reconnect(enrichment_db):
 factory,(user,a1,_,_,account_id)=enrichment_db;m,_=make(enrichment_db,tokens=Tokens(AuthenticationError("no")));job=m.create_job(user,activity_ids=[a1]);asyncio.run(m.run(job.job_id));assert m.job_for_user(user,job.job_id).error_category=="authentication_reconnect_required"
 with factory() as s:assert s.get(IntegrationAccount,account_id).status=="refresh_required"
def test_provider_deleted_and_malformed_detail_are_isolated(enrichment_db):
 factory,(user,a1,a2,_,_)=enrichment_db;m,_=make(enrichment_db,[StravaActivityUnavailableError("gone"),{"id":999,"athlete":{"id":456}}]);job=m.create_job(user,activity_ids=[a1,a2]);asyncio.run(m.run(job.job_id));view=m.job_for_user(user,job.job_id);assert view.status=="partially_succeeded" and view.failed_count==2 and view.error_category=="provider_unavailable"
 with factory() as s:assert s.get(CompletedActivity,a1).provider_deleted_at is not None;assert s.get(CompletedActivity,a1).enrichment_status=="unavailable";assert s.get(CompletedActivity,a2).enrichment_status=="failed"
def test_safe_job_view_contains_no_credentials_or_provider_payload(enrichment_db):
 _,(user,a1,_,_,_)=enrichment_db;m,_=make(enrichment_db,[payload(secret="must-not-escape")]);job=m.create_job(user,activity_ids=[a1]);asyncio.run(m.run(job.job_id));assert "secret" not in repr(m.job_for_user(user,job.job_id)) and "payload" not in repr(m.job_for_user(user,job.job_id))


def test_database_failure_rolls_back_current_activity_and_continues(enrichment_db):
 factory,(user,a1,a2,_,_)=enrichment_db;m,_=make(enrichment_db,[payload("101"),payload("102")]);original=m._persist;calls=0
 def flaky(job_id,activity_id,fields):
  nonlocal calls
  calls+=1
  if calls==1:raise SQLAlchemyError("bounded write failed")
  return original(job_id,activity_id,fields)
 m._persist=flaky
 job=m.create_job(user,activity_ids=[a1,a2]);asyncio.run(m.run(job.job_id));view=m.job_for_user(user,job.job_id);assert view.status=="partially_succeeded" and view.failed_count==1 and view.enriched_count==1 and view.error_category=="database_error"
 with factory() as s:assert s.get(CompletedActivity,a1).provider_description is None;assert s.get(CompletedActivity,a2).provider_description=="Provider description"


def test_isolated_mapping_failure_preserves_safe_job_category_and_logs_no_exception_text(enrichment_db,caplog):
 _,(user,a1,_,_,_)=enrichment_db;m,_=make(enrichment_db,[{"id":101,"athlete":{"id":456},"suffer_score":71.5,"description":"provider body must stay hidden"}]);job=m.create_job(user,activity_ids=[a1]);asyncio.run(m.run(job.job_id));view=m.job_for_user(user,job.job_id)
 assert view.status=="partially_succeeded" and view.failed_count==1 and view.error_category=="provider_payload"
 assert "stage=mapping" in caplog.text and "exception_class=InvalidPayloadError" in caplog.text
 assert "provider body must stay hidden" not in caplog.text and "stored-secret" not in caplog.text