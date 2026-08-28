from datetime import date
from threading import Barrier, Thread

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.training_plan_lifecycle import TrainingPlanActiveConflictError, TrainingPlanLifecycleApplication
from app.db.models import AthleteProfile, TrainingPlan
from tests.test_athlete_creation_concurrency import temporary_postgres


def test_two_drafts_for_same_athlete_activate_at_most_one(monkeypatch):
    with temporary_postgres(monkeypatch) as engine:
        with Session(engine) as session:
            athlete=AthleteProfile(display_name="Concurrent",timezone="UTC",unit_system="metric")
            session.add(athlete);session.flush()
            plans=[TrainingPlan(athlete_profile_id=athlete.id,title=name,start_date=date(2099,1,1),end_date=date(2099,1,7),status="draft",origin="human") for name in ("First","Second")]
            session.add_all(plans);session.commit();athlete_id=athlete.id;plan_ids=[item.id for item in plans]
        barrier=Barrier(2);results=[]
        def activate(plan_id):
            with Session(engine) as session:
                barrier.wait()
                try:TrainingPlanLifecycleApplication(session).transition(plan_id=plan_id,athlete_id=athlete_id,action="activate");results.append("active")
                except TrainingPlanActiveConflictError:results.append("conflict")
        threads=[Thread(target=activate,args=(plan_id,)) for plan_id in plan_ids]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=15)
        assert all(not thread.is_alive() for thread in threads)
        assert sorted(results)==["active","conflict"]
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(TrainingPlan).where(TrainingPlan.athlete_profile_id==athlete_id,TrainingPlan.status=="active"))==1


def test_drafts_for_different_athletes_can_activate_concurrently(monkeypatch):
    with temporary_postgres(monkeypatch) as engine:
        with Session(engine) as session:
            athletes=[AthleteProfile(display_name=name,timezone="UTC",unit_system="metric") for name in ("First athlete","Second athlete")]
            session.add_all(athletes);session.flush()
            plans=[TrainingPlan(athlete_profile_id=athlete.id,title="Draft",start_date=date(2099,1,1),end_date=date(2099,1,7),status="draft",origin="human") for athlete in athletes]
            session.add_all(plans);session.commit();pairs=[(athlete.id,plan.id) for athlete,plan in zip(athletes,plans,strict=True)]
        barrier=Barrier(2);results=[];errors=[]
        def activate(athlete_id,plan_id):
            try:
                with Session(engine) as session:
                    barrier.wait()
                    results.append(TrainingPlanLifecycleApplication(session).transition(plan_id=plan_id,athlete_id=athlete_id,action="activate").status)
            except Exception as error:errors.append(error)
        threads=[Thread(target=activate,args=pair) for pair in pairs]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=15)
        assert all(not thread.is_alive() for thread in threads)
        assert errors==[] and results==["active","active"]
        with Session(engine) as session:
            for athlete_id,_ in pairs:
                assert session.scalar(select(func.count()).select_from(TrainingPlan).where(TrainingPlan.athlete_profile_id==athlete_id,TrainingPlan.status=="active"))==1


def test_concurrent_activate_retry_for_same_plan_is_idempotent(monkeypatch):
    with temporary_postgres(monkeypatch) as engine:
        with Session(engine) as session:
            athlete=AthleteProfile(display_name="Retry",timezone="UTC",unit_system="metric")
            session.add(athlete);session.flush()
            plan=TrainingPlan(athlete_profile_id=athlete.id,title="Draft",start_date=date(2099,1,1),end_date=date(2099,1,7),status="draft",origin="human")
            session.add(plan);session.commit();athlete_id=athlete.id;plan_id=plan.id
        barrier=Barrier(2);results=[];errors=[]
        def activate():
            try:
                with Session(engine) as session:
                    barrier.wait()
                    results.append(TrainingPlanLifecycleApplication(session).transition(plan_id=plan_id,athlete_id=athlete_id,action="activate").status)
            except Exception as error:errors.append(error)
        threads=[Thread(target=activate) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=15)
        assert all(not thread.is_alive() for thread in threads)
        assert errors==[] and results==["active","active"]
        with Session(engine) as session:
            assert session.get(TrainingPlan,plan_id).status=="active"
            assert session.scalar(select(func.count()).select_from(TrainingPlan).where(TrainingPlan.athlete_profile_id==athlete_id,TrainingPlan.status=="active"))==1
            assert session.scalar(select(func.count()).select_from(TrainingPlan).where(TrainingPlan.athlete_profile_id==athlete_id))==1
