from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import AthleteDailyTrainingLoad, AthleteDailyTrainingStatus, AthleteProfile, User
from scripts.backfill_training_status import BackfillTrainingStatusOptions, backfill_training_status, main

DAY=date(2026,1,1)


@pytest.fixture
def context():
    engine=create_engine("sqlite+pysqlite:///:memory:",poolclass=StaticPool)
    @event.listens_for(engine,"connect")
    def foreign_keys(connection,record):del record;connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as session:
        user=User(email="backfill-status@example.com",normalized_email="backfill-status@example.com",auth_subject="backfill-status")
        athlete=AthleteProfile(display_name="Test athlete",timezone="Europe/Madrid",unit_system="metric");session.add(athlete);session.commit()
        yield session,athlete
    engine.dispose()


def add_source(session,athlete,offset=0,load=50):
    row=AthleteDailyTrainingLoad(athlete_profile_id=athlete.id,local_date=DAY+timedelta(days=offset),timezone_name="Europe/Madrid",source_load_algorithm_version="0.7b.1",manual_strength_algorithm_version="0.7e.1",aggregation_algorithm_version="0.7c.1",total_load=load,endurance_load=load,strength_load=0,strength_session_count=0,activity_count=1,loaded_activity_count=1,null_load_activity_count=0,total_duration_seconds=100,coverage="complete",quality="high",warnings=[],activity_ids=[],calculated_at=datetime.now(timezone.utc))
    session.add(row);session.commit();return row


def options(athlete,**overrides):
    values=dict(athlete_id=athlete.id,start_date=DAY,end_date=DAY+timedelta(days=2));values.update(overrides);return BackfillTrainingStatusOptions(**values)


def test_dry_run_calculates_reports_and_persists_nothing(context):
    session,athlete=context;add_source(session,athlete);messages=[]
    result=backfill_training_status(session,options(athlete,dry_run=True),reporter=messages.append)
    assert result.persisted_after==3
    assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus))==0
    assert any("dry-run" in message for message in messages)
    assert any("fitness=" in message for message in messages)


def test_dry_run_does_not_modify_existing_status(context):
    session,athlete=context;source=add_source(session,athlete)
    backfill_training_status(session,options(athlete),reporter=lambda _:None)
    before=[(row.id,row.fitness) for row in session.scalars(select(AthleteDailyTrainingStatus)).all()]
    source.total_load=100;session.commit()
    backfill_training_status(session,options(athlete,dry_run=True),reporter=lambda _:None)
    after=[(row.id,row.fitness) for row in session.scalars(select(AthleteDailyTrainingStatus)).all()]
    assert after==before


def test_real_run_fills_days_is_idempotent_and_uses_total_load(context):
    session,athlete=context;add_source(session,athlete,0,70);add_source(session,athlete,2,30)
    first=backfill_training_status(session,options(athlete),reporter=lambda _:None)
    rows=session.scalars(select(AthleteDailyTrainingStatus).order_by(AthleteDailyTrainingStatus.local_date)).all()
    snapshot=[(row.id,row.fitness,row.fatigue,row.form) for row in rows]
    second=backfill_training_status(session,options(athlete),reporter=lambda _:None)
    assert [row.total_load for row in rows]==[Decimal("70"),Decimal("0"),Decimal("30")]
    assert [(row.id,row.fitness,row.fatigue,row.form) for row in session.scalars(select(AthleteDailyTrainingStatus).order_by(AthleteDailyTrainingStatus.local_date))]==snapshot
    assert first.persisted_after==second.persisted_after==3


def test_default_range_starts_at_source_and_reaches_local_today(context):
    session,athlete=context;add_source(session,athlete,1,10)
    result=backfill_training_status(session,BackfillTrainingStatusOptions(athlete.id),reporter=lambda _:None,clock=lambda:datetime(2026,1,5,23,tzinfo=timezone.utc))
    assert result.requested_start_date==DAY+timedelta(days=1)
    assert result.effective_end_date==DAY+timedelta(days=5)
    assert result.persisted_after==5


def test_no_sources_real_removes_obsolete_but_dry_run_restores(context):
    session,athlete=context;add_source(session,athlete);backfill_training_status(session,options(athlete),reporter=lambda _:None)
    session.query(AthleteDailyTrainingLoad).delete();session.commit()
    backfill_training_status(session,options(athlete,dry_run=True),reporter=lambda _:None)
    assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus))==3
    result=backfill_training_status(session,options(athlete),reporter=lambda _:None)
    assert result.persisted_after==0


@pytest.mark.parametrize("overrides",[
    {"start_date":DAY+timedelta(days=1),"end_date":DAY},
    {"start_date":DAY,"end_date":None},
    {"timezone_name":"Unknown/Zone"},
])
def test_invalid_options_or_timezone_fail(context,overrides):
    session,athlete=context
    with pytest.raises(Exception):
        value=options(athlete,**overrides)
        backfill_training_status(session,value,reporter=lambda _:None)


def test_unknown_athlete_and_cli_exit_codes(context):
    session,_=context
    with pytest.raises(Exception):
        backfill_training_status(session,BackfillTrainingStatusOptions(uuid4(),start_date=DAY,end_date=DAY),reporter=lambda _:None)
    with pytest.raises(SystemExit) as error:
        main(["--athlete-id","invalid"])
    assert error.value.code==2


def test_backfill_does_not_modify_source(context):
    session,athlete=context;row=add_source(session,athlete);snapshot=(row.id,row.total_load,row.calculated_at)
    backfill_training_status(session,options(athlete),reporter=lambda _:None)
    assert (row.id,row.total_load,row.calculated_at)==snapshot

