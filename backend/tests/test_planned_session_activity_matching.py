from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.planned_session_activity_matching import (
    ActivityNotFoundError, MatchClassification, PlannedSessionActivityMatching,
)
from app.db.base import Base
from app.db.models import AthleteProfile, CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession


@pytest.fixture
def db():
    engine=create_engine("sqlite+pysqlite:///:memory:",poolclass=StaticPool,connect_args={"check_same_thread":False})
    @event.listens_for(engine,"connect")
    def foreign_keys(connection,_): connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine); session=Session(engine); yield session; session.close(); engine.dispose()


def athlete(db,name="A"):
    row=AthleteProfile(display_name=name,timezone="Europe/Madrid",unit_system="metric");db.add(row);db.flush();return row


def planned(db,owner,day=date(2026,1,10),sport="running",duration=2700,distance=8000):
    row=PlannedTrainingSession(athlete_profile_id=owner.id,scheduled_date=day,timezone="Europe/Madrid",sport=sport,title="Session",planned_duration_seconds=duration,planned_distance_meters=distance,status="planned",origin="human");db.add(row);db.flush();return row


def activity(db,owner,day=10,hour=8,sport="running",duration=2700,distance=8000):
    row=CompletedActivity(athlete_id=owner.id,source_summary="manual",sport=sport,name="Activity",start_at=datetime(2026,1,day,hour,tzinfo=timezone.utc),timezone="Europe/Madrid",elapsed_time_s=duration,moving_time_s=duration,distance_m=distance);db.add(row);db.flush();return row


def test_clear_match_uses_local_date_duration_and_distance(db):
    owner=athlete(db); session=planned(db,owner); actual=activity(db,owner)
    app=PlannedSessionActivityMatching(db,today=date(2026,1,11)); candidates=app.find_candidates(owner.id,session); result=app.evaluate_match(owner.id,session,candidates)
    assert candidates[0].activity.id==actual.id and candidates[0].local_date==date(2026,1,10)
    assert result.classification is MatchClassification.CLEAR_MATCH


@pytest.mark.parametrize("day",[9,11])
def test_adjacent_day_is_candidate_with_penalty(db,day):
    owner=athlete(db); session=planned(db,owner); activity(db,owner,day=day)
    candidate=PlannedSessionActivityMatching(db,today=date(2026,1,12)).find_candidates(owner.id,session)[0]
    assert candidate.score<.85 and "adjacent_local_date" in candidate.evidence


def test_hard_filters_and_strength_ignores_distance(db):
    owner=athlete(db); other=athlete(db,"B"); session=planned(db,owner,sport="strength",distance=999999)
    good=activity(db,owner,sport="strength",distance=1);activity(db,owner,day=13,sport="strength");activity(db,owner,sport="cycling");activity(db,other,sport="strength")
    candidates=PlannedSessionActivityMatching(db,today=date(2026,1,11)).find_candidates(owner.id,session)
    assert [item.activity.id for item in candidates]==[good.id]
    assert not any(value.startswith("distance_error") for value in candidates[0].evidence)


def test_two_equivalent_activities_are_ambiguous(db):
    owner=athlete(db); session=planned(db,owner);activity(db,owner,duration=2640);activity(db,owner,hour=10,duration=2760)
    result=PlannedSessionActivityMatching(db,today=date(2026,1,11)).evaluate_match(owner.id,session)
    assert result.classification is MatchClassification.AMBIGUOUS and result.reason=="insufficient_margin"


def test_second_relevant_session_prevents_automatic_claim(db):
    owner=athlete(db); first=planned(db,owner);planned(db,owner);activity(db,owner)
    result=PlannedSessionActivityMatching(db,today=date(2026,1,11)).evaluate_match(owner.id,first)
    assert result.classification is MatchClassification.AMBIGUOUS and result.reason=="another_relevant_session"


def test_manual_nm_idempotency_priority_and_unlink(db):
    owner=athlete(db); one=planned(db,owner);two=planned(db,owner,day=date(2026,1,11));a=activity(db,owner);b=activity(db,owner,hour=10)
    app=PlannedSessionActivityMatching(db,today=date(2026,1,12))
    first=app.create_link(owner.id,one.id,a.id,source="manual");assert app.create_link(owner.id,one.id,a.id,source="manual").id==first.id
    app.create_link(owner.id,one.id,b.id,source="manual");app.create_link(owner.id,two.id,a.id,source="manual");db.commit()
    assert db.scalar(select(func.count()).select_from(PlannedSessionActivityLink))==3
    result,link=app.auto_match(owner.id,one.id);assert link is None and result.classification is MatchClassification.AMBIGUOUS
    app.unlink(owner.id,one.id,a.id);app.unlink(owner.id,one.id,a.id);db.commit()
    assert db.get(PlannedTrainingSession,one.id) and db.get(CompletedActivity,a.id)
    assert db.scalar(select(func.count()).select_from(PlannedSessionActivityLink))==2


def test_manual_promotes_same_automatic_link_in_place(db):
    owner=athlete(db);session=planned(db,owner);actual=activity(db,owner);app=PlannedSessionActivityMatching(db,today=date(2026,1,12))
    automatic=app.create_link(owner.id,session.id,actual.id,source="automatic");identifier=automatic.id;created_at=automatic.created_at
    promoted=app.create_link(owner.id,session.id,actual.id,source="manual")
    assert promoted.id==identifier and promoted.created_at==created_at
    assert promoted.match_source=="manual" and promoted.match_confidence=="high" and promoted.algorithm_version is None
    assert app.create_link(owner.id,session.id,actual.id,source="manual").id==identifier
    assert db.scalar(select(func.count()).select_from(PlannedSessionActivityLink).where(PlannedSessionActivityLink.planned_training_session_id==session.id,PlannedSessionActivityLink.completed_activity_id==actual.id))==1


def test_cross_athlete_is_hidden(db):
    owner=athlete(db);other=athlete(db,"B");session=planned(db,owner);foreign=activity(db,other)
    with pytest.raises(ActivityNotFoundError): PlannedSessionActivityMatching(db).create_link(owner.id,session.id,foreign.id,source="manual")


def test_future_session_never_auto_matches(db):
    owner=athlete(db); session=planned(db,owner);activity(db,owner)
    result=PlannedSessionActivityMatching(db,today=date(2026,1,9)).evaluate_match(owner.id,session)
    assert result.classification is MatchClassification.NO_MATCH and result.reason=="future_session"
