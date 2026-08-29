from alembic import command
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Event
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session
from app.application.planned_session_activity_matching import PlannedSessionActivityMatching
from app.db.models import AthleteProfile, CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession
from test_athlete_onboarding_migration import migrated_database


def test_0026_upgrade_schema_and_downgrade(monkeypatch):
    with migrated_database(monkeypatch) as (engine,cfg):
        command.upgrade(cfg,"0026_session_activity_links")
        inspector=inspect(engine);table="planned_session_activity_links"
        assert table in inspector.get_table_names()
        assert {item["name"] for item in inspector.get_indexes(table)} >= {"ix_planned_session_activity_links_athlete","ix_planned_session_activity_links_session","ix_planned_session_activity_links_activity"}
        assert {item["name"] for item in inspector.get_unique_constraints(table)} == {"uq_planned_session_activity_link_pair"}
        foreign={item["referred_table"]:item["options"].get("ondelete") for item in inspector.get_foreign_keys(table)}
        assert foreign=={"athlete_profiles":"CASCADE","planned_training_sessions":"CASCADE","completed_activities":"CASCADE"}
        command.downgrade(cfg,"0025_training_plan_previews")
        assert table not in inspect(engine).get_table_names()


def test_concurrent_same_pair_creates_one_link(monkeypatch):
    with migrated_database(monkeypatch) as (engine,cfg):
        command.upgrade(cfg,"0026_session_activity_links")
        with Session(engine) as session:
            owner=AthleteProfile(display_name="Concurrent",timezone="UTC",unit_system="metric");session.add(owner);session.flush()
            planned=PlannedTrainingSession(athlete_profile_id=owner.id,scheduled_date=date(2026,1,1),timezone="UTC",sport="running",title="Run",planned_duration_seconds=3600,status="planned",origin="human")
            activity=CompletedActivity(athlete_id=owner.id,source_summary="manual",sport="running",name="Run",start_at=datetime(2026,1,1,8,tzinfo=timezone.utc),timezone="UTC",elapsed_time_s=3600,moving_time_s=3600)
            session.add_all([planned,activity]);session.commit();ids=(owner.id,planned.id,activity.id)
        def create():
            with Session(engine) as session:
                row=PlannedSessionActivityMatching(session).create_link(ids[0],ids[1],ids[2],source="manual");session.commit();return row.id
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:create(),range(2)))
        with Session(engine) as session: count=session.scalar(select(func.count()).select_from(PlannedSessionActivityLink))
        assert results[0]==results[1] and count==1


def _seed_pair(engine):
    with Session(engine) as session:
        owner=AthleteProfile(display_name="Priority",timezone="UTC",unit_system="metric");session.add(owner);session.flush()
        planned=PlannedTrainingSession(athlete_profile_id=owner.id,scheduled_date=date(2026,1,1),timezone="UTC",sport="running",title="Run",planned_duration_seconds=3600,status="planned",origin="human")
        activity=CompletedActivity(athlete_id=owner.id,source_summary="manual",sport="running",name="Run",start_at=datetime(2026,1,1,8,tzinfo=timezone.utc),timezone="UTC",elapsed_time_s=3600,moving_time_s=3600)
        session.add_all([planned,activity]);session.commit();return owner.id,planned.id,activity.id


def _assert_manual_pair(engine,ids):
    with Session(engine) as session:
        rows=session.scalars(select(PlannedSessionActivityLink).where(PlannedSessionActivityLink.planned_training_session_id==ids[1],PlannedSessionActivityLink.completed_activity_id==ids[2])).all()
        assert len(rows)==1 and rows[0].match_source=="manual" and rows[0].match_confidence=="high" and rows[0].algorithm_version is None
        return rows[0].id


def test_concurrent_manual_first_keeps_manual_priority(monkeypatch):
    with migrated_database(monkeypatch) as (engine,cfg):
        command.upgrade(cfg,"0026_session_activity_links");ids=_seed_pair(engine);started=Event()
        with Session(engine) as first:
            first.scalar(select(AthleteProfile).where(AthleteProfile.id==ids[0]).with_for_update())
            def automatic():
                started.set()
                with Session(engine) as session:
                    _,row=PlannedSessionActivityMatching(session,today=date(2026,1,2)).auto_match(ids[0],ids[1]);session.commit();return row.id if row else None
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(automatic);started.wait();manual=PlannedSessionActivityMatching(first).create_link(ids[0],ids[1],ids[2],source="manual");manual_id=manual.id;first.commit();automatic_id=future.result()
        assert automatic_id==manual_id==_assert_manual_pair(engine,ids)


def test_concurrent_automatic_first_is_promoted_to_manual(monkeypatch):
    with migrated_database(monkeypatch) as (engine,cfg):
        command.upgrade(cfg,"0026_session_activity_links");ids=_seed_pair(engine);started=Event()
        with Session(engine) as first:
            first.scalar(select(AthleteProfile).where(AthleteProfile.id==ids[0]).with_for_update())
            def manual():
                started.set()
                with Session(engine) as session:
                    row=PlannedSessionActivityMatching(session).create_link(ids[0],ids[1],ids[2],source="manual");session.commit();return row.id
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(manual);started.wait();_,automatic=PlannedSessionActivityMatching(first,today=date(2026,1,2)).auto_match(ids[0],ids[1]);automatic_id=automatic.id if automatic else None;first.commit();manual_id=future.result()
        assert automatic_id is not None and automatic_id==manual_id==_assert_manual_pair(engine,ids)
