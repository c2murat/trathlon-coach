import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,func,select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.settings import Settings,get_settings
from app.db.base import Base
from app.db.models import AthleteProfile,User,UserAthleteMembership,UserAuthSession
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import verify_password
PASSWORD="a secure registration password"
@pytest.fixture
def registration():
 engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);session=Session(engine);app=create_app();settings=Settings(auth_mode="session",environment="test",public_registration_enabled=True)
 def database_override():yield session
 app.dependency_overrides[get_db_session]=database_override;app.dependency_overrides[get_settings]=lambda:settings
 yield session,TestClient(app)
 session.close();engine.dispose()
def payload(plan="athlete",email="new@example.test"):
 return {"display_name":"Nueva Persona","email":email,"password":PASSWORD,"account_plan":plan,"timezone":"Europe/Madrid"}
def test_register_athlete_is_atomic_self_service_and_logs_in(registration):
 session,client=registration;response=client.post("/auth/register",json=payload());assert response.status_code==201;user=session.scalar(select(User));membership=session.scalar(select(UserAthleteMembership));athlete=session.scalar(select(AthleteProfile));assert user.account_plan=="athlete" and verify_password(PASSWORD,user.password_hash);assert membership.role=="athlete" and membership.is_active and membership.is_default and membership.user_id==user.id and membership.athlete_profile_id==athlete.id;assert client.cookies.get("tricoach_session") and client.cookies.get("tricoach_csrf");assert client.get("/session/context").json()["athletes"][0]["role"]=="athlete"
def test_register_coach_has_session_and_no_athletes(registration):
 session,client=registration;response=client.post("/auth/register",json=payload("coach"));assert response.status_code==201 and response.json()["account_plan"]=="coach";assert session.scalar(select(User)).account_plan=="coach";assert session.scalar(select(func.count(AthleteProfile.id)))==0 and session.scalar(select(func.count(UserAthleteMembership.id)))==0;context=client.get("/session/context").json();assert context["athletes"]==[] and context["selected_athlete_id"] is None and context["selection_required"] is False
@pytest.mark.parametrize("plan",["owner","editor","viewer","unknown"])
def test_public_registration_rejects_non_public_plans(registration,plan):
 session,client=registration;assert client.post("/auth/register",json=payload(plan)).status_code==422;assert session.scalar(select(func.count(User.id)))==0
def test_duplicate_normalized_email_and_extra_fields_are_safe(registration):
 session,client=registration;assert client.post("/auth/register",json=payload(email=" Person@Example.Test ")).status_code==201;client.cookies.clear();assert client.post("/auth/register",json=payload("coach","person@example.test")).status_code==409;bad=payload();bad["athlete_id"]="00000000-0000-0000-0000-000000000001";assert client.post("/auth/register",json=bad).status_code==422;assert session.scalar(select(func.count(User.id)))==1