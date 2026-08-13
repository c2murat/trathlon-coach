from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.multi_athlete_integrity import MultiAthleteIntegrityError,validate_activity_ids
from app.db.base import Base,utc_now
from app.db.models import AthleteProfile,CompletedActivity,IntegrationAccount,User,UserAthleteMembership
from scripts.audit_multi_athlete_integrity import audit
from scripts.backfill_training_load import BackfillOptions


@pytest.fixture
def integrity_session():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine) as session:
        u1=User(email="a@x.invalid",normalized_email="a@x.invalid",auth_subject="a");u2=User(email="b@x.invalid",normalized_email="b@x.invalid",auth_subject="b");a1=AthleteProfile(display_name="Test athlete");a2=AthleteProfile(display_name="Test athlete");activity=CompletedActivity(athlete=a1,source_summary="manual",sport="running",name="Run",start_at=utc_now(),timezone="UTC",elapsed_time_s=1);session.add_all([u1,u2,a1,a2,activity]);session.commit();yield session,a1.id,a2.id,activity.id
    engine.dispose()


def test_activity_ids_require_existing_unique_same_athlete(integrity_session):
    session,a1,a2,activity=integrity_session;validate_activity_ids(session,athlete_id=a1,activity_ids=[activity])
    with pytest.raises(MultiAthleteIntegrityError,match="duplicate"):validate_activity_ids(session,athlete_id=a1,activity_ids=[activity,activity])
    with pytest.raises(MultiAthleteIntegrityError,match="not_found"):validate_activity_ids(session,athlete_id=a1,activity_ids=[uuid4()])
    with pytest.raises(MultiAthleteIntegrityError,match="tenant_mismatch"):validate_activity_ids(session,athlete_id=a2,activity_ids=[activity])


def test_partial_unique_index_blocks_second_active_account(integrity_session):
    session,a1,_,_=integrity_session;session.add(IntegrationAccount(athlete_id=a1,provider="strava",external_account_id="1",status="active"));session.commit();session.add(IntegrationAccount(athlete_id=a1,provider="strava",external_account_id="2",status="active"))
    with pytest.raises(IntegrityError):session.commit()
    session.rollback();assert session.query(IntegrationAccount).count()==1


def test_auditor_is_read_only_and_reports_clean_scope(integrity_session):
    session,a1,_,_=integrity_session;before=session.new.copy();result=audit(session,athlete_id=a1);assert result["issue_count"]==0;assert session.new==before and not session.dirty and not session.deleted


def test_auditor_reports_integration_linked_to_deleted_athlete(integrity_session):
    session,a1,_,_=integrity_session;athlete=session.get(AthleteProfile,a1);athlete.deleted_at=utc_now();account=IntegrationAccount(athlete_id=a1,provider="strava",external_account_id="deleted-athlete",status="active");session.add(account);session.commit();result=audit(session,athlete_id=a1);assert result["checks"]["integration_accounts_deleted_athlete"]==[{"account_id":str(account.id),"athlete_id":str(a1)}]

def test_athlete_only_profile_is_a_valid_controller_and_non_controller_is_reported(integrity_session):
    session,a1,a2,_=integrity_session;user=session.query(User).first();session.add_all([UserAthleteMembership(user_id=user.id,athlete_profile_id=a1,role="athlete",is_active=True),UserAthleteMembership(user_id=user.id,athlete_profile_id=a2,role="viewer",is_active=True)]);session.commit();result=audit(session);assert not any(row["athlete_id"]==str(a1) for row in result["checks"]["athletes_without_active_controller"]);assert any(row["athlete_id"]==str(a2) for row in result["checks"]["athletes_without_active_controller"])


def test_backfill_scope_and_global_confirmation_are_mandatory():
    with pytest.raises(ValueError,match="exactly one"):BackfillOptions()
    with pytest.raises(ValueError,match="exactly one"):BackfillOptions(athlete_id=uuid4(),all_athletes=True)
    with pytest.raises(ValueError,match="confirm"):BackfillOptions(all_athletes=True)
    assert BackfillOptions(all_athletes=True,dry_run=True).dry_run
    assert BackfillOptions(all_athletes=True,confirm_all_athletes=True).all_athletes


def test_auditor_reports_invalid_membership_role(integrity_session):
    session,a1,_,_=integrity_session
    user=session.query(User).first()
    session.execute(text("PRAGMA ignore_check_constraints = ON"))
    membership=UserAthleteMembership(user_id=user.id,athlete_profile_id=a1,role="unexpected",is_active=True)
    session.add(membership)
    session.commit()
    result=audit(session)
    assert result["checks"]["invalid_membership_roles"]==[{"membership_id":str(membership.id),"role":"unexpected"}]


def test_auditor_reports_multiple_active_athlete_identities(integrity_session):
    session,a1,_,_=integrity_session
    session.execute(text("DROP INDEX uq_user_athlete_memberships_active_self_athlete"))
    users=session.query(User).all()
    session.add_all([
        UserAthleteMembership(user_id=users[0].id,athlete_profile_id=a1,role="athlete",is_active=True),
        UserAthleteMembership(user_id=users[1].id,athlete_profile_id=a1,role="athlete",is_active=True),
    ])
    session.commit()
    assert audit(session)["checks"]["multiple_active_athlete_memberships"]==[{"athlete_id":str(a1),"count":2}]
