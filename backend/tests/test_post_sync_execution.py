import asyncio
from datetime import date

import pytest
from sqlalchemy import select

from app.application.execution_overview import ExecutionOverviewApplication
from app.application.planned_session_activity_matching import PlannedSessionActivityMatching, ActivityNotFoundError
from app.db.models import PlannedTrainingSession, PlannedSessionActivityLink, CompletedActivity, SyncJob, AthleteProfile
from app.providers.strava.activity_client import StravaActivityPage
from tests.test_strava_activity_import import database, manager, activity, EMPTY_RATE


def add_plan(factory,owner,**kwargs):
    with factory() as db:
        row=PlannedTrainingSession(athlete_profile_id=owner,scheduled_date=date(2026,7,1),timezone="Europe/Madrid",
            sport="running",title="RUN_EASY",planned_duration_seconds=600,planned_distance_meters=2000,
            status="planned",origin="human",**kwargs)
        db.add(row);db.commit();return row.id


def sync(database,payloads):
    importer,_,_=manager(database,[StravaActivityPage(tuple(payloads),EMPTY_RATE)])
    user=database[1][0];job=importer.create_or_resume_job(user)
    asyncio.run(importer.run_job(job.job_id))
    return job.job_id


def test_import_creates_automatic_link_and_overview_immediately_reflects_c1(database):
    factory,(_,owner,_,_)=database
    session_id=add_plan(factory,owner)
    job=sync(database,[activity(77)])
    with factory() as db:
        assert db.get(SyncJob,job).status=="succeeded"
        link=db.scalar(select(PlannedSessionActivityLink))
        assert link.planned_training_session_id==session_id and link.match_source=="automatic"
        result=ExecutionOverviewApplication(db).assemble(athlete_id=owner,as_of_date=date(2026,7,2),timezone_name="Europe/Madrid")
        evidence=result.latest_activity_sessions[0].evidence
        assert evidence.completion_status=="COMPLETED"
        assert evidence.link_provenance[0].match_source=="automatic"
        assert result.recent_sessions[0].activities[0].duration_seconds==580


def test_subsequent_sync_preserves_manual_link_and_provenance(database):
    factory,(_,owner,_,_)=database
    session_id=add_plan(factory,owner);sync(database,[activity(78)])
    with factory() as db:
        link=db.scalar(select(PlannedSessionActivityLink))
        PlannedSessionActivityMatching(db).create_link(owner,session_id,link.completed_activity_id,source="manual")
        identifier=link.id;created=link.created_at;db.commit()
    sync(database,[activity(78,moving_time=590),activity(79)])
    with factory() as db:
        links=db.scalars(select(PlannedSessionActivityLink)).all()
        assert len(links)==1 and links[0].id==identifier and links[0].created_at==created
        assert links[0].match_source=="manual" and links[0].algorithm_version is None


@pytest.mark.parametrize("multiple_sessions",[False,True])
def test_post_sync_ambiguity_never_forces_a_link(database,multiple_sessions):
    factory,(_,owner,_,_)=database
    add_plan(factory,owner)
    if multiple_sessions:add_plan(factory,owner)
    sync(database,[activity(80)] if multiple_sessions else [activity(80),activity(81)])
    with factory() as db:
        assert db.scalar(select(PlannedSessionActivityLink)) is None
        result=ExecutionOverviewApplication(db).assemble(athlete_id=owner,as_of_date=date(2026,7,2),timezone_name="Europe/Madrid")
        assert all(row.evidence.completion_status=="UNMATCHED" for row in result.recent_sessions)


def test_post_sync_cannot_claim_other_athletes_session(database):
    factory,(_,owner,_,_)=database
    with factory() as db:
        other=AthleteProfile(display_name="Other",timezone="UTC",unit_system="metric")
        db.add(other);db.commit();other_id=other.id
    foreign_plan=add_plan(factory,other_id);sync(database,[activity(83)])
    with factory() as db:
        assert db.scalar(select(PlannedSessionActivityLink)) is None
        actual=db.scalar(select(CompletedActivity))
        with pytest.raises(ActivityNotFoundError):
            PlannedSessionActivityMatching(db).create_link(other_id,foreign_plan,actual.id,source="manual")


def test_matching_failure_is_reported_before_sync_success_and_retry_recovers(database,monkeypatch):
    factory,(_,owner,_,_)=database
    add_plan(factory,owner)
    original=PlannedSessionActivityMatching.auto_match
    def fail(*args,**kwargs):raise RuntimeError("matching unavailable")
    monkeypatch.setattr(PlannedSessionActivityMatching,"auto_match",fail)
    job_id=sync(database,[activity(85)])
    with factory() as db:
        job=db.get(SyncJob,job_id)
        assert job.status=="partially_succeeded"
        assert job.error_code=="post_processing_activity_matching_failed"
        assert db.scalar(select(PlannedSessionActivityLink)) is None
        assert db.scalar(select(CompletedActivity)) is not None
    monkeypatch.setattr(PlannedSessionActivityMatching,"auto_match",original)
    retried=sync(database,[])
    with factory() as db:
        assert db.get(SyncJob,retried).status=="succeeded"
        assert db.scalar(select(PlannedSessionActivityLink)).match_source=="automatic"
