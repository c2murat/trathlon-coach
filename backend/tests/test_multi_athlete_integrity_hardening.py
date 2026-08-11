from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.multi_athlete_integrity import MultiAthleteIntegrityError,validate_activity_ids
from app.db.base import Base,utc_now
from app.db.models import AthleteProfile,CompletedActivity,IntegrationAccount,User
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


def test_backfill_scope_and_global_confirmation_are_mandatory():
    with pytest.raises(ValueError,match="exactly one"):BackfillOptions()
    with pytest.raises(ValueError,match="exactly one"):BackfillOptions(athlete_id=uuid4(),all_athletes=True)
    with pytest.raises(ValueError,match="confirm"):BackfillOptions(all_athletes=True)
    assert BackfillOptions(all_athletes=True,dry_run=True).dry_run
    assert BackfillOptions(all_athletes=True,confirm_all_athletes=True).all_athletes
