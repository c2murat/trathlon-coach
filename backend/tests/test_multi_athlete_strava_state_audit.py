from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base,utc_now
from app.db.models import AthleteProfile,CompletedActivity,IntegrationAccount,OAuthCredential,SyncJob
from scripts.audit_multi_athlete_strava_state import audit

@pytest.fixture
def state_session():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine) as session:
        a=AthleteProfile(display_name="Carlos",timezone="Europe/Madrid",unit_system="metric");b=AthleteProfile(display_name="Jenny",timezone="Europe/Madrid",unit_system="metric");session.add_all([a,b]);session.flush();yield session,a,b
    engine.dispose()

def connect(session,athlete,external):
    account=IntegrationAccount(athlete_id=athlete.id,provider="strava",external_account_id=external,status="active",scopes=["read"]);credential=OAuthCredential(integration_account=account,access_token=f"fake-{external}",refresh_token=f"fake-refresh-{external}",expires_at=utc_now()+timedelta(hours=1),scopes=["read"]);session.add_all([account,credential]);session.commit();return account

def test_reports_connected_a_and_disconnected_b_without_secrets(state_session):
    session,a,_=state_session;connect(session,a,"external-a");before=(session.new.copy(),session.dirty.copy(),session.deleted.copy());result=audit(session,all_athletes=True);assert result["issue_count"]==0;assert [row["active_strava_accounts"] for row in result["athletes"]]==[1,0];assert result["strava"]=={"accounts":1,"distinct_external_identities":1};assert "fake-external-a" not in str(result) and before==(session.new.copy(),session.dirty.copy(),session.deleted.copy())

def test_reports_two_distinct_connections(state_session):
    session,a,b=state_session;connect(session,a,"external-a");connect(session,b,"external-b");result=audit(session,all_athletes=True);assert result["issue_count"]==0;assert result["strava"]=={"accounts":2,"distinct_external_identities":2};assert all(row["oauth_credentials"]==1 for row in result["athletes"])

def test_detects_job_and_activity_cross_account_mismatches(state_session):
    session,a,b=state_session;account=connect(session,a,"external-a");job=SyncJob(athlete_id=b.id,integration_account_id=account.id,job_type="strava_historical_summary",status="succeeded",idempotency_key="cross",attempt_count=0);activity=CompletedActivity(athlete_id=b.id,source_integration_account_id=account.id,external_activity_id="activity-b",source_summary="strava",sport="running",name="B",start_at=utc_now(),timezone="UTC",elapsed_time_s=60);session.add_all([job,activity]);session.commit();result=audit(session,all_athletes=True);assert len(result["checks"]["job_account_athlete_mismatch"])==1;assert len(result["checks"]["activity_account_athlete_mismatch"])==1

def test_detects_integration_for_deleted_athlete(state_session):
    session,a,_=state_session;connect(session,a,"external-a");a.deleted_at=utc_now();session.commit();result=audit(session,all_athletes=True);assert len(result["checks"]["integration_account_deleted_athlete"])==1

def test_requires_one_explicit_scope(state_session):
    session,_,_=state_session
    with pytest.raises(ValueError,match="exactly one"):audit(session)
    with pytest.raises(ValueError,match="exactly one"):audit(session,all_athletes=True,athlete_id=__import__("uuid").uuid4())
