from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.athlete_user_provisioning import AthleteUserProvisioningError, provision_athlete_user, validate_athlete_user_provisioning
from app.core.settings import Settings, get_settings
from app.db.base import Base, utc_now
from app.db.models import AthleteProfile, User, UserAthleteMembership
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import verify_password
from scripts import provision_athlete_user as cli

PASSWORD = "a secure provision password"


@pytest.fixture
def provisioning_env():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session=Session(engine)
    carlos=AthleteProfile(display_name="Carlos",timezone="Europe/Madrid",unit_system="metric")
    jenny=AthleteProfile(display_name="Jenny",timezone="Europe/Madrid",unit_system="metric")
    owner=User(email="owner@example.test",normalized_email="owner@example.test",auth_subject="owner",display_name="Owner")
    session.add_all([owner,carlos,jenny]);session.flush()
    session.add_all([
        UserAthleteMembership(user_id=owner.id,athlete_profile_id=carlos.id,role="owner",is_active=True,is_default=True),
        UserAthleteMembership(user_id=owner.id,athlete_profile_id=jenny.id,role="owner",is_active=True,is_default=False),
    ]);session.commit()
    yield session,engine,owner,carlos,jenny
    session.close();Base.metadata.drop_all(engine);engine.dispose()


def test_provisions_active_user_and_default_athlete_membership(provisioning_env):
    session,_,owner,_,jenny=provisioning_env
    before=[(m.user_id,m.athlete_profile_id,m.role,m.is_default) for m in session.scalars(select(UserAthleteMembership).where(UserAthleteMembership.user_id==owner.id))]
    user,membership=provision_athlete_user(session,athlete_id=jenny.id,email="  JENNY@Example.Test ",display_name=" Jenny   Ruiz ",timezone=" Europe/Madrid ",password=PASSWORD)
    session.commit()
    assert (user.email,user.normalized_email,user.status,user.display_name,user.timezone)==("jenny@example.test","jenny@example.test","active","Jenny Ruiz","Europe/Madrid")
    assert verify_password(PASSWORD,user.password_hash)
    assert (membership.role,membership.is_active,membership.is_default,membership.athlete_profile_id)==("athlete",True,True,jenny.id)
    assert [(m.user_id,m.athlete_profile_id,m.role,m.is_default) for m in session.scalars(select(UserAthleteMembership).where(UserAthleteMembership.user_id==owner.id))]==before


@pytest.mark.parametrize("case,code",[
    ("duplicate","user_email_already_exists"),
    ("deleted","athlete_deleted"),
    ("self","active_athlete_membership_already_exists"),
])
def test_conflicts_leave_database_unchanged(provisioning_env,case,code):
    session,_,owner,_,jenny=provisioning_env
    if case=="deleted":jenny.deleted_at=utc_now()
    if case=="self":
        other=User(email="self@example.test",normalized_email="self@example.test",auth_subject="self")
        session.add(other);session.flush();session.add(UserAthleteMembership(user_id=other.id,athlete_profile_id=jenny.id,role="athlete",is_active=True,is_default=True))
    session.commit();before=(session.scalar(select(func.count(User.id))),session.scalar(select(func.count(UserAthleteMembership.id))))
    email=owner.email if case=="duplicate" else "new@example.test"
    with pytest.raises(AthleteUserProvisioningError,match=code):
        provision_athlete_user(session,athlete_id=jenny.id,email=email,display_name="New",timezone="UTC",password=PASSWORD)
    session.rollback()
    assert (session.scalar(select(func.count(User.id))),session.scalar(select(func.count(UserAthleteMembership.id))))==before


def test_membership_failure_rolls_back_user(provisioning_env):
    session,_,_,_,jenny=provisioning_env
    before=session.scalar(select(func.count(User.id)))
    def fail(*_):raise RuntimeError("membership failure")
    event.listen(UserAthleteMembership,"before_insert",fail)
    try:
        with pytest.raises(RuntimeError):
            provision_athlete_user(session,athlete_id=jenny.id,email="atomic@example.test",display_name="Atomic",timezone="UTC",password=PASSWORD)
        session.rollback()
    finally:
        event.remove(UserAthleteMembership,"before_insert",fail)
    assert session.scalar(select(func.count(User.id)))==before


def test_database_prevents_two_active_self_identities(provisioning_env):
    session,_,_,_,jenny=provisioning_env
    first=User(email="one@example.test",normalized_email="one@example.test",auth_subject="one")
    second=User(email="two@example.test",normalized_email="two@example.test",auth_subject="two")
    session.add_all([first,second]);session.flush()
    session.add(UserAthleteMembership(user_id=first.id,athlete_profile_id=jenny.id,role="athlete",is_active=True,is_default=True));session.commit()
    session.add(UserAthleteMembership(user_id=second.id,athlete_profile_id=jenny.id,role="athlete",is_active=True,is_default=True))
    with pytest.raises(IntegrityError):session.commit()
    session.rollback()


def test_standard_login_context_and_cross_athlete_isolation(provisioning_env):
    session,_,_,carlos,jenny=provisioning_env
    user,_=provision_athlete_user(session,athlete_id=jenny.id,email="login@example.test",display_name="Jenny User",timezone="UTC",password=PASSWORD);session.commit()
    app=create_app();app.dependency_overrides[get_db_session]=lambda:(yield session);app.dependency_overrides[get_settings]=lambda:Settings(auth_mode="session",environment="test",session_cookie_secure=False)
    client=TestClient(app)
    assert client.post("/auth/login",json={"email":" LOGIN@example.test ","password":PASSWORD}).status_code==200
    assert client.get("/auth/me").json()["id"]==str(user.id)
    context=client.get("/session/context").json()
    assert context["selected_athlete_id"]==str(jenny.id)
    assert [(x["athlete_id"],x["role"]) for x in context["athletes"]]==[(str(jenny.id),"athlete")]
    assert client.get("/athlete/profile",headers={"X-TriCoach-Athlete-Id":str(jenny.id)}).status_code==200
    assert client.get("/athlete/profile",headers={"X-TriCoach-Athlete-Id":str(carlos.id)}).status_code==403


def test_dry_run_does_not_prompt_or_write(provisioning_env,monkeypatch,capsys):
    session,_,_,_,jenny=provisioning_env
    before=session.scalar(select(func.count(User.id)))
    monkeypatch.setattr(cli,"SessionLocal",lambda:session)
    monkeypatch.setattr(cli.getpass,"getpass",lambda *_:pytest.fail("dry-run requested a password"))
    assert cli.main(["--athlete-id",str(jenny.id),"--email","dry@example.test","--display-name","Dry Run","--dry-run"])==0
    assert session.scalar(select(func.count(User.id)))==before
    output=capsys.readouterr().out
    assert "d***@example.test" in output and "role: athlete" in output and "DRY-RUN" in output
    assert PASSWORD not in output and "password_hash" not in output
