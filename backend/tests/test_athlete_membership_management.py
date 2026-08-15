from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.athlete_permissions import AthleteCapability, capabilities_for_role
from app.api.dependencies.auth import AuthenticatedUser
from app.api.dependencies.current_athlete import resolve_current_athlete
from app.application.athlete_membership_management import AthleteMembershipRoleChangeError, revoke_athlete_membership, set_athlete_membership_role, validate_athlete_membership_revocation, validate_athlete_membership_role_change
from app.db.base import Base
from app.db.models import AthleteProfile, User, UserAthleteMembership
from scripts import revoke_athlete_membership as revoke_cli
from scripts import set_athlete_membership_role as cli


@pytest.fixture
def role_env():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine);session=Session(engine)
    carlos_user=User(email="carlos@example.test",normalized_email="carlos@example.test",auth_subject="carlos")
    jenny_user=User(email="jenny@example.test",normalized_email="jenny@example.test",auth_subject="jenny")
    carlos=AthleteProfile(display_name="Carlos");jenny=AthleteProfile(display_name="Jenny")
    session.add_all([carlos_user,jenny_user,carlos,jenny]);session.flush()
    carlos_self=UserAthleteMembership(user_id=carlos_user.id,athlete_profile_id=carlos.id,role="owner",is_active=True,is_default=True)
    carlos_jenny=UserAthleteMembership(user_id=carlos_user.id,athlete_profile_id=jenny.id,role="owner",is_active=True,is_default=False)
    jenny_self=UserAthleteMembership(user_id=jenny_user.id,athlete_profile_id=jenny.id,role="athlete",is_active=True,is_default=True)
    session.add_all([carlos_self,carlos_jenny,jenny_self]);session.commit()
    yield session,engine,carlos_user,jenny_user,carlos,jenny,carlos_self,carlos_jenny,jenny_self
    session.close();Base.metadata.drop_all(engine);engine.dispose()


def test_owner_to_coach_preserves_membership_when_athlete_controller_exists(role_env):
    session,_,_,_,_,jenny,_,membership,_=role_env
    before=(membership.id,membership.is_active,membership.is_default,membership.created_at)
    result=set_athlete_membership_role(session,user_id=membership.user_id,athlete_id=jenny.id,new_role="coach");session.commit();session.refresh(membership)
    assert result.changed and membership.role=="coach"
    assert (membership.id,membership.is_active,membership.is_default,membership.created_at)==before


def test_rejects_removing_the_only_controller(role_env):
    session,_,carlos_user,_,carlos,_,_,_,_=role_env
    with pytest.raises(AthleteMembershipRoleChangeError,match="athlete_controller_required"):
        set_athlete_membership_role(session,user_id=carlos_user.id,athlete_id=carlos.id,new_role="viewer")
    session.rollback()
    assert session.scalar(select(UserAthleteMembership.role).where(UserAthleteMembership.user_id==carlos_user.id,UserAthleteMembership.athlete_profile_id==carlos.id))=="owner"


def test_same_role_is_idempotent(role_env):
    session,_,carlos_user,_,carlos,_,membership,_,_=role_env
    result=set_athlete_membership_role(session,user_id=carlos_user.id,athlete_id=carlos.id,new_role="owner")
    assert not result.changed and membership.role=="owner"


@pytest.mark.parametrize("case,code",[
    ("membership","membership_not_found"),("athlete","athlete_deleted"),("user","user_not_found"),("inactive","membership_inactive"),
])
def test_missing_deleted_and_inactive_inputs_are_rejected(role_env,case,code):
    session,_,carlos_user,_,carlos,jenny,_,membership,_=role_env
    user_id=carlos_user.id;athlete_id=jenny.id
    if case=="membership":
        unrelated=AthleteProfile(display_name="Unrelated");session.add(unrelated);session.commit();athlete_id=unrelated.id
    if case=="athlete":jenny.deleted_at=datetime.now(timezone.utc);session.commit()
    if case=="user":user_id=uuid4()
    if case=="inactive":
        target=session.scalar(select(UserAthleteMembership).where(UserAthleteMembership.user_id==carlos_user.id,UserAthleteMembership.athlete_profile_id==carlos.id));target.is_active=False;session.commit();athlete_id=carlos.id
    with pytest.raises(AthleteMembershipRoleChangeError,match=code):
        validate_athlete_membership_role_change(session,user_id=user_id,athlete_id=athlete_id,new_role="coach")


def test_rejects_second_active_athlete_before_database_constraint(role_env):
    session,_,carlos_user,_,_,jenny,_,_,_=role_env
    with pytest.raises(AthleteMembershipRoleChangeError,match="athlete_self_membership_already_exists"):
        set_athlete_membership_role(session,user_id=carlos_user.id,athlete_id=jenny.id,new_role="athlete")


def test_rollback_restores_original_role(role_env):
    session,_,carlos_user,_,_,jenny,_,membership,_=role_env
    with pytest.raises(RuntimeError):
        set_athlete_membership_role(session,user_id=carlos_user.id,athlete_id=jenny.id,new_role="coach")
        raise RuntimeError("after role mutation")
    session.rollback();session.refresh(membership)
    assert membership.role=="owner"


def test_dry_run_persists_nothing(role_env,monkeypatch,capsys):
    session,engine,carlos_user,_,_,jenny,_,membership,_=role_env
    membership_id=membership.id
    monkeypatch.setattr(cli,"SessionLocal",lambda:Session(engine))
    code=cli.main(["--user-id",str(carlos_user.id),"--athlete-id",str(jenny.id),"--role","coach","--dry-run"])
    with Session(engine) as verification:
        assert verification.get(UserAthleteMembership,membership_id).role=="owner"
    assert code==0
    output=capsys.readouterr().out
    assert "Current role: owner" in output and "Requested role: coach" in output
    assert "Controller after transition: true" in output and "No changes persisted." in output


def test_capabilities_are_scoped_to_selected_membership(role_env):
    session,_,carlos_user,jenny_user,carlos,jenny,_,membership,_=role_env
    membership.role="coach";session.commit()
    carlos_context=resolve_current_athlete(session,AuthenticatedUser(carlos_user.id),str(carlos.id))
    jenny_for_carlos=resolve_current_athlete(session,AuthenticatedUser(carlos_user.id),str(jenny.id))
    jenny_context=resolve_current_athlete(session,AuthenticatedUser(jenny_user.id),str(jenny.id))
    assert set(capabilities_for_role(carlos_context.role))==set(AthleteCapability)
    coach=set(capabilities_for_role(jenny_for_carlos.role))
    assert coach==set(capabilities_for_role("coach"))
    assert not coach.intersection({AthleteCapability.EDIT_ATHLETE_PROFILE,AthleteCapability.MANAGE_STRAVA_CONNECTION,AthleteCapability.DELETE_MANUAL_STRENGTH,AthleteCapability.DELETE_STRAVA_LOCATION_EVIDENCE})
    assert set(capabilities_for_role(jenny_context.role))==set(capabilities_for_role("athlete"))
    with pytest.raises(HTTPException) as error:
        resolve_current_athlete(session,AuthenticatedUser(jenny_user.id),str(carlos.id))
    assert error.value.status_code==403 and error.value.detail["code"]=="athlete_not_authorized"

def test_revoke_coach_preserves_athlete_controller(role_env):
    session, _, _, _, _, jenny, _, membership, _ = role_env
    membership.role = "coach"
    session.commit()
    result = revoke_athlete_membership(session, user_id=membership.user_id, athlete_id=jenny.id)
    session.commit()
    session.refresh(membership)
    assert result.changed
    assert not membership.is_active
    assert not membership.is_default


def test_revoke_is_idempotent_when_already_inactive(role_env):
    session, _, _, _, _, jenny, _, membership, _ = role_env
    membership.role = "coach"
    membership.is_active = False
    session.commit()
    result = revoke_athlete_membership(session, user_id=membership.user_id, athlete_id=jenny.id)
    assert not result.changed


def test_revoke_only_controller_is_rejected(role_env):
    session, _, carlos_user, _, carlos, _, membership, _, _ = role_env
    with pytest.raises(AthleteMembershipRoleChangeError, match="athlete_controller_required"):
        revoke_athlete_membership(session, user_id=carlos_user.id, athlete_id=carlos.id)
    session.rollback()
    assert membership.is_active


def test_revoke_unknown_membership_is_controlled(role_env):
    session, _, carlos_user, _, _, _, _, _, _ = role_env
    unrelated = AthleteProfile(display_name="Unrelated")
    session.add(unrelated)
    session.commit()
    with pytest.raises(AthleteMembershipRoleChangeError, match="membership_not_found"):
        validate_athlete_membership_revocation(session, user_id=carlos_user.id, athlete_id=unrelated.id)


def test_revoke_rollback_preserves_original(role_env):
    session, _, _, _, _, jenny, _, membership, _ = role_env
    membership.role = "coach"
    session.commit()
    revoke_athlete_membership(session, user_id=membership.user_id, athlete_id=jenny.id)
    session.rollback()
    session.refresh(membership)
    assert membership.is_active


def test_revoke_cli_dry_run_persists_nothing(role_env, monkeypatch, capsys):
    session, engine, _, _, _, jenny, _, membership, _ = role_env
    membership.role = "coach"
    session.commit()
    monkeypatch.setattr(revoke_cli, "SessionLocal", lambda: Session(engine))
    code = revoke_cli.main(["--user-id", str(membership.user_id), "--athlete-id", str(jenny.id), "--dry-run"])
    with Session(engine) as verification:
        assert verification.get(UserAthleteMembership, membership.id).is_active
    output = capsys.readouterr().out
    assert code == 0
    assert "Current role: coach" in output
    assert "Action: revoke" in output
    assert "Controller after transition: true" in output
    assert "No changes persisted." in output