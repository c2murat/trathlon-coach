from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.api.dependencies.athlete_permissions import capabilities_for_role
from app.db.base import Base
from app.db.models import AthleteProfile,User,UserAthleteMembership
from app.db.session import get_db_session
from app.main import create_app
@pytest.fixture
def context_client():
 e=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(e)
 with Session(e) as s:s.add(User(id=LOCAL_MVP_USER_ID,email="current@test",normalized_email="current@test",auth_subject="current",display_name="Ana"));s.commit()
 def override():
  with Session(e) as s:yield s
 app=create_app();app.dependency_overrides[get_db_session]=override
 with TestClient(app) as c:yield c,e
def add(e,role="owner",default=False,active=True):
 with Session(e) as s:
  token=str(uuid4());u=User(email=f"{token}@test",normalized_email=f"{token}@test",auth_subject=token);a=AthleteProfile(display_name="Test athlete");s.add_all([u,a,UserAthleteMembership(user_id=LOCAL_MVP_USER_ID,athlete_profile=a,role=role,is_default=default,is_active=active)]);s.commit();return a.id
def test_empty_single_and_inactive(context_client):
 c,e=context_client;b=c.get("/session/context").json();assert b["athletes"]==[] and not b["selection_required"];a=add(e,"viewer");add(e,active=False);b=c.get("/session/context").json();assert b["selected_athlete_id"]==str(a);assert b["athletes"][0]["capabilities"]==["read_athlete_data","read_strava_integration"]
def test_ambiguous_and_explicit(context_client):
 c,e=context_client;add(e,"coach");b=add(e,"editor");body=c.get("/session/context").json();assert body["selection_required"] and body["selected_athlete_id"] is None;assert c.get("/session/context",headers={"X-TriCoach-Athlete-Id":str(b)}).json()["selected_athlete_id"]==str(b)
def test_default_and_header_errors(context_client):
 c,e=context_client;add(e);d=add(e,default=True);body=c.get("/session/context").json();assert body["selected_athlete_id"]==str(d) and body["athletes"][0]["athlete_id"]==str(d);assert c.get("/session/context",headers={"X-TriCoach-Athlete-Id":"bad"}).status_code==422;assert c.get("/session/context",headers={"X-TriCoach-Athlete-Id":str(uuid4())}).status_code==403
def test_multiple_defaults_are_rejected_and_unknown_role(context_client):
 c,e=context_client;add(e,default=True)
 with pytest.raises(IntegrityError):add(e,default=True)
 assert capabilities_for_role("unknown")==()
