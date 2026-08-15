from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.coach_assignments import coach_membership_lock_statement
from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.models import AthleteProfile, User, UserAthleteMembership
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import hash_password

PASSWORD="a secure test password"

@pytest.fixture
def env():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine);session=Session(engine);app=create_app();settings=Settings(auth_mode="session",environment="test")
    app.dependency_overrides[get_db_session]=lambda:(yield session);app.dependency_overrides[get_settings]=lambda:settings
    yield session,app
    session.close();engine.dispose()

def user(session,name,plan="coach",status="active"):
    row=User(email=f"{name}@example.test",normalized_email=f"{name}@example.test",auth_subject=f"subject-{name}",display_name=name,password_hash=hash_password(PASSWORD),account_plan=plan,status=status);session.add(row);session.commit();return row

def athlete(session,name):
    row=AthleteProfile(display_name=name,timezone="UTC",unit_system="metric");session.add(row);session.commit();return row

def client(app,row):
    c=TestClient(app);assert c.post("/auth/login",json={"email":row.email,"password":PASSWORD}).status_code==200;return c

def headers(c):return {"X-CSRF-Token":c.cookies.get("tricoach_csrf")}
def payload(coach,athlete):return {"coach_user_id":str(coach.id),"athlete_profile_id":str(athlete.id)}

def test_revocation_lock_targets_only_membership_table():
    sql = str(coach_membership_lock_statement(uuid4()).compile(dialect=postgresql.dialect()))
    normalized_sql = " ".join(sql.upper().split())
    assert "FOR UPDATE OF USER_ATHLETE_MEMBERSHIPS" in normalized_sql
    assert " JOIN " not in normalized_sql

def test_owner_lists_candidates_assigns_idempotently_reactivates_and_revokes(env):
    session,app=env;owner=user(session,"owner","owner");coach=user(session,"coach");target=athlete(session,"Target");c=client(app,owner)
    candidates=c.get("/coach-assignments/candidates");assert candidates.status_code==200;assert candidates.json()["coaches"][0]["email"]==coach.email;assert candidates.json()["athletes"][0]["display_name"]=="Target"
    first=c.post("/coach-assignments",json=payload(coach,target),headers=headers(c));second=c.post("/coach-assignments",json=payload(coach,target),headers=headers(c));assert first.status_code==second.status_code==201;assert first.json()["membership_id"]==second.json()["membership_id"];assert session.scalar(select(func.count()).select_from(UserAthleteMembership))==1
    membership=session.get(UserAthleteMembership,UUID(first.json()["membership_id"]));assert membership.role=="coach" and membership.is_active and membership.is_default
    assert c.get("/coach-assignments").json()[0]["athlete_display_name"]=="Target"
    assert c.delete(f"/coach-assignments/{uuid4()}",headers=headers(c)).status_code==404
    revoked=c.delete(f"/coach-assignments/{membership.id}",headers=headers(c));assert revoked.status_code==200;session.refresh(membership);assert not membership.is_active and not membership.is_default
    again=c.post("/coach-assignments",json=payload(coach,target),headers=headers(c));assert again.status_code==201 and again.json()["membership_id"]==str(membership.id);assert session.scalar(select(func.count()).select_from(UserAthleteMembership))==1

def test_administration_is_owner_only(env):
    session,app=env;target=athlete(session,"Target");coach=user(session,"coach");athlete_user=user(session,"athlete-user","athlete")
    for actor in (coach,athlete_user):
        c=client(app,actor);assert c.get("/coach-assignments").status_code==403;assert c.get("/coach-assignments/candidates").status_code==403;assert c.post("/coach-assignments",json=payload(coach,target),headers=headers(c)).status_code==403;assert c.delete(f"/coach-assignments/{uuid4()}",headers=headers(c)).status_code==403
    assert session.scalar(select(func.count()).select_from(UserAthleteMembership))==0

@pytest.mark.parametrize("kind,expected",[("owner",409),("athlete",409),("disabled",409),("missing",404)])
def test_invalid_coach_targets_are_rejected(env,kind,expected):
    session,app=env;owner=user(session,"owner","owner");target=athlete(session,"Target")
    if kind=="missing":coach_id=uuid4()
    else:coach_id=user(session,f"target-{kind}","coach" if kind=="disabled" else kind,"disabled" if kind=="disabled" else "active").id
    c=client(app,owner);response=c.post("/coach-assignments",json={"coach_user_id":str(coach_id),"athlete_profile_id":str(target.id)},headers=headers(c));assert response.status_code==expected;assert session.scalar(select(func.count()).select_from(UserAthleteMembership))==0

def test_role_conflict_and_missing_athlete(env):
    session,app=env;owner=user(session,"owner","owner");coach=user(session,"coach");target=athlete(session,"Target");session.add(UserAthleteMembership(user_id=coach.id,athlete_profile_id=target.id,role="viewer",is_active=True,is_default=True));session.commit();c=client(app,owner)
    assert c.post("/coach-assignments",json=payload(coach,target),headers=headers(c)).status_code==409
    other=user(session,"other-coach");assert c.post("/coach-assignments",json={"coach_user_id":str(other.id),"athlete_profile_id":str(uuid4())},headers=headers(c)).status_code==404

def test_coach_context_multiple_isolated_and_revocation_immediate(env):
    session,app=env;owner=user(session,"owner","owner");coach=user(session,"coach");a=athlete(session,"A");b=athlete(session,"B");hidden=athlete(session,"Hidden");admin=client(app,owner)
    one=admin.post("/coach-assignments",json=payload(coach,a),headers=headers(admin)).json();admin.post("/coach-assignments",json=payload(coach,b),headers=headers(admin));cc=client(app,coach);context=cc.get("/session/context").json();assert {x["label"] for x in context["athletes"]}=={"A","B"};assert "Hidden" not in {x["label"] for x in context["athletes"]}
    assert cc.get("/activities",headers={"X-TriCoach-Athlete-Id":str(hidden.id)}).status_code==403
    admin.delete(f"/coach-assignments/{one['membership_id']}",headers=headers(admin));context=cc.get("/session/context",headers={"X-TriCoach-Athlete-Id":str(a.id)});assert context.status_code==403;assert cc.get("/activities",headers={"X-TriCoach-Athlete-Id":str(a.id)}).status_code==403
