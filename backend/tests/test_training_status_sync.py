from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.training_status import TrainingStatusApplication
from app.application.training_status_sync import (
    TrainingStatusSyncCoordinate,
    sync_training_status_after_load_change,
    sync_training_status_coordinates,
)
from app.db.base import Base
from app.db.models import AthleteDailyTrainingLoad, AthleteDailyTrainingStatus, AthleteProfile, User

DAY = date(2026, 3, 28)


@pytest.fixture
def context():
    engine=create_engine("sqlite+pysqlite:///:memory:",poolclass=StaticPool)
    @event.listens_for(engine,"connect")
    def foreign_keys(connection,record):
        del record;connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as session:
        athletes=[]
        for number in (1,2):
            user=User(email=f"sync{number}@example.com",normalized_email=f"sync{number}@example.com",auth_subject=f"sync-{number}")
            athlete=AthleteProfile(user=user,timezone="Europe/Madrid",unit_system="metric");session.add(athlete);athletes.append(athlete)
        session.commit()
        yield session,athletes
    engine.dispose()


def source(session,athlete,offset,load,**overrides):
    values=dict(athlete_profile_id=athlete.id,local_date=DAY+timedelta(days=offset),timezone_name="Europe/Madrid",source_load_algorithm_version="0.7b.1",manual_strength_algorithm_version="0.7e.1",aggregation_algorithm_version="0.7c.1",total_load=Decimal(str(load)),endurance_load=Decimal(str(load)),strength_load=0,strength_session_count=0,activity_count=1,loaded_activity_count=1,null_load_activity_count=0,total_duration_seconds=100,coverage="complete",quality="high",warnings=[],activity_ids=[],calculated_at=datetime.now(timezone.utc))
    values.update(overrides);row=AthleteDailyTrainingLoad(**values);session.add(row);session.commit();return row


def sync(session,athlete,**overrides):
    values=dict(athlete_id=athlete.id,affected_start_date=DAY,affected_end_date=DAY,timezone_name="Europe/Madrid",training_load_algorithm_version="0.7b.1",manual_strength_algorithm_version="0.7e.1",through_date=DAY+timedelta(days=2))
    values.update(overrides);return sync_training_status_after_load_change(session,**values)


def test_sync_extends_to_through_date_and_fills_rest_days(context):
    session,athletes=context;source(session,athletes[0],0,100)
    rows=sync(session,athletes[0])
    assert [row.total_load for row in rows]==[Decimal("100"),Decimal("0"),Decimal("0")]
    assert rows[-1].history_day_number==3


def test_historical_change_propagates_without_rounding_drift(context):
    session,athletes=context;row=source(session,athletes[0],0,1)
    first=sync(session,athletes[0]);snapshot=[(item.fitness,item.fatigue,item.form) for item in first];old_last_fitness=first[-1].fitness
    assert [(item.fitness,item.fatigue,item.form) for item in sync(session,athletes[0])]==snapshot
    row.total_load=10;session.flush()
    assert sync(session,athletes[0])[-1].fitness!=old_last_fitness


def test_removed_intermediate_source_becomes_rest(context):
    session,athletes=context;source(session,athletes[0],0,10);middle=source(session,athletes[0],1,20);source(session,athletes[0],2,30)
    sync(session,athletes[0]);session.delete(middle);session.flush()
    assert sync(session,athletes[0])[1].total_load==0


def test_no_sources_removes_only_exact_combination(context):
    session,athletes=context;row=source(session,athletes[0],0,10);source(session,athletes[1],0,20)
    sync(session,athletes[0]);sync(session,athletes[1]);session.delete(row);session.flush()
    assert sync(session,athletes[0])==()
    assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus).where(AthleteDailyTrainingStatus.athlete_profile_id==athletes[1].id))==3


def test_coordinates_are_deduplicated_and_date_ranges_merged(context,monkeypatch):
    session,athletes=context;source(session,athletes[0],0,10)
    original=TrainingStatusApplication.recalculate_training_status
    calls=[]
    def wrapped(application,*args,**kwargs):
        calls.append((args,kwargs))
        return original(application,*args,**kwargs)
    monkeypatch.setattr(TrainingStatusApplication,"recalculate_training_status",wrapped)
    common=dict(athlete_id=athletes[0].id,timezone_name="Europe/Madrid",training_load_algorithm_version="0.7b.1",manual_strength_algorithm_version="0.7e.1")
    coordinates=(TrainingStatusSyncCoordinate(affected_start_date=DAY,affected_end_date=DAY,**common),TrainingStatusSyncCoordinate(affected_start_date=DAY+timedelta(days=1),affected_end_date=DAY+timedelta(days=2),**common))
    sync_training_status_coordinates(session,coordinates,through_date=DAY+timedelta(days=2))
    assert len(calls)==1


def test_timezone_change_syncs_both_isolated_combinations(context):
    session,athletes=context;source(session,athletes[0],0,10);source(session,athletes[0],0,20,timezone_name="UTC")
    coordinates=tuple(TrainingStatusSyncCoordinate(athlete_id=athletes[0].id,affected_start_date=DAY,affected_end_date=DAY,timezone_name=zone,training_load_algorithm_version="0.7b.1",manual_strength_algorithm_version="0.7e.1") for zone in ("Europe/Madrid","UTC"))
    sync_training_status_coordinates(session,coordinates,through_date=DAY)
    assert {row.timezone_name for row in session.scalars(select(AthleteDailyTrainingStatus)).all()}=={"Europe/Madrid","UTC"}


def test_local_today_handles_midnight_dst_and_future_source(context):
    session,athletes=context;source(session,athletes[0],0,10);source(session,athletes[0],4,30)
    rows=sync_training_status_after_load_change(session,athlete_id=athletes[0].id,affected_start_date=DAY,affected_end_date=DAY,timezone_name="Europe/Madrid",training_load_algorithm_version="0.7b.1",manual_strength_algorithm_version="0.7e.1",clock=lambda:datetime(2026,3,28,23,30,tzinfo=timezone.utc))
    assert rows[-1].local_date==DAY+timedelta(days=1)
    assert not any(row.local_date>DAY+timedelta(days=1) for row in rows)


def test_sync_flushes_without_commit_and_does_not_modify_source(context,monkeypatch):
    session,athletes=context;row=source(session,athletes[0],0,10);snapshot=(row.id,row.total_load,row.calculated_at)
    commit=Mock(side_effect=AssertionError("no commit"));monkeypatch.setattr(session,"commit",commit)
    sync(session,athletes[0])
    commit.assert_not_called();assert (row.id,row.total_load,row.calculated_at)==snapshot



