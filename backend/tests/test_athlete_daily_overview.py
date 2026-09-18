from datetime import date, datetime, time, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.routes import dashboard
from app.application.athlete_daily_overview import AthleteDailyOverviewApplication
from app.application.training_status_interpretation import TrainingStatusOverviewAssembler
from app.application.planned_session_activity_matching import PlannedSessionActivityMatching
from app.db.models import CompetitionGoal, User, UserAthleteMembership, AthleteDailyTrainingStatus
from app.db.session import get_db_session
from tests.test_planned_session_activity_matching import db, athlete, planned, activity

NOW=datetime(2026,1,11,12,tzinfo=timezone.utc)

def overview(db,owner,now=NOW):
    return AthleteDailyOverviewApplication(db).assemble(athlete_id=owner.id,timezone_name=owner.timezone,now=now)

def user(db):
    email=f"{uuid4()}@example.invalid"
    value=User(email=email,normalized_email=email,auth_subject=str(uuid4()),timezone="UTC")
    db.add(value);db.flush();return value

def goal(db,owner,creator,day,status="active",name="Race"):
    value=CompetitionGoal(athlete_profile_id=owner.id,created_by_user_id=creator.id,name=name,
        event_date=day,event_category="running",event_format="10k",timezone=owner.timezone,
        priority="A",status=status,city="Madrid")
    db.add(value);db.flush();return value

def test_empty_partial_overview_and_determinism(db):
    owner=athlete(db);db.commit()
    result=overview(db,owner)
    assert result.today_sessions==() and result.next_session is None and result.next_goal is None
    assert result.interpretation.overall_state=="INSUFFICIENT_DATA"
    assert result.execution.latest_activity is None
    assert result.summary['activity_count']==0
    assert result.as_of_date==result.execution.as_of_date==result.interpretation.as_of_date
    assert result.model_dump_json()==overview(db,owner).model_dump_json()

@pytest.mark.parametrize('count',[1,3])
def test_all_today_sessions_sorted_by_time_then_id_including_status(db,count):
    owner=athlete(db)
    rows=[planned(db,owner,day=NOW.date()) for _ in range(count)]
    for index,row in enumerate(rows):row.scheduled_start_time=time(10-index);row.status='cancelled' if index==1 else 'planned'
    past=planned(db,owner);future=planned(db,owner,day=date(2026,1,12))
    db.commit();result=overview(db,owner)
    assert [x.id for x in result.today_sessions]==[x.id for x in reversed(rows)]
    assert result.next_session.id==future.id
    assert past.id not in [x.id for x in result.today_sessions]

def test_next_session_ties_and_goal_filters_and_isolation(db):
    owner=athlete(db);foreign=athlete(db,'Foreign');creator=user(db)
    early=planned(db,owner,day=date(2026,1,12));early.scheduled_start_time=time(8)
    late=planned(db,owner,day=date(2026,1,12));late.scheduled_start_time=time(9)
    planned(db,foreign,day=NOW.date());activity(db,foreign)
    for day,status in [(date(2026,1,1),'active'),(NOW.date(),'active'),(date(2026,1,12),'cancelled'),(date(2026,1,12),'completed')]:goal(db,owner,creator,day,status)
    goal(db,foreign,creator,date(2026,1,12),name='Foreign')
    expected=goal(db,owner,creator,date(2026,2,1));goal(db,owner,creator,date(2026,3,1))
    db.commit();result=overview(db,owner)
    assert result.next_session.id==early.id
    assert result.next_goal.id==expected.id and result.next_goal.days_remaining==21
    assert result.today_sessions==() and result.execution.latest_activity is None

@pytest.mark.parametrize('instant,local_day',[
    ('2026-07-10T22:30:00+00:00',date(2026,7,11)),
    ('2026-01-10T23:30:00+00:00',date(2026,1,11)),
    ('2026-01-10T22:30:00+00:00',date(2026,1,10)),
])
def test_single_local_date_with_summer_and_winter_dst(db,instant,local_day):
    owner=athlete(db);session=planned(db,owner,day=local_day);db.commit()
    result=overview(db,owner,datetime.fromisoformat(instant))
    assert result.as_of_date==result.execution.as_of_date==result.interpretation.as_of_date==local_day
    assert result.today_sessions[0].id==session.id
    assert result.timezone=='Europe/Madrid'

def test_reuses_exact_d1_interpretation_and_q_manual_link(db):
    owner=athlete(db);session=planned(db,owner);actual=activity(db,owner)
    link=PlannedSessionActivityMatching(db).create_link(owner.id,session.id,actual.id,source='manual')
    for day in range(1,12):
        db.add(AthleteDailyTrainingStatus(athlete_profile_id=owner.id,local_date=date(2026,1,day),timezone_name=owner.timezone,
            total_load=50,fitness=30,fatigue=35,form=-5,history_day_number=100,is_warmup=False,calculated_at=NOW,
            training_load_algorithm_version='0.7b.1',manual_strength_algorithm_version='0.7e.1',training_status_algorithm_version='0.7f.1'))
    db.commit();result=overview(db,owner)
    _,_,expected=TrainingStatusOverviewAssembler(db).assemble(athlete_id=owner.id,start_date=NOW.date(),as_of_date=NOW.date(),
        timezone_name=owner.timezone,training_load_algorithm_version='0.7b.1',manual_strength_algorithm_version='0.7e.1',training_status_algorithm_version='0.7f.1')
    assert result.interpretation==expected and result.interpretation.fitness==30
    assert result.execution.recent_sessions[0].evidence.completion_status=='COMPLETED'
    assert link.match_source=='manual' and not db.dirty and not db.new

@pytest.mark.parametrize('role',['athlete','coach'])
def test_endpoint_authorized_readonly_bounded_and_no_foreign_data(db,monkeypatch,role):
    owner=athlete(db);foreign=athlete(db,'Foreign');viewer=user(db)
    membership=UserAthleteMembership(user_id=viewer.id,athlete_profile_id=owner.id,role=role,is_active=True,is_default=True)
    db.add(membership)
    for _ in range(20):planned(db,owner,day=NOW.date())
    activity(db,owner);activity(db,foreign);db.commit()
    app=FastAPI();app.include_router(dashboard.router)
    app.dependency_overrides[get_db_session]=lambda:db
    viewer_id=viewer.id;foreign_id=str(foreign.id)
    app.dependency_overrides[get_current_user]=lambda:AuthenticatedUser(id=viewer_id)
    monkeypatch.setattr(dashboard,'utc_now',lambda:NOW)
    statements=[]
    def track(conn,cursor,sql,*args):
        assert sql.lstrip().upper().startswith('SELECT')
        statements.append(sql)
    event.listen(db.bind,'before_cursor_execute',track)
    try:
        with TestClient(app) as client:
            response=client.get('/dashboard/daily-overview')
            assert response.status_code==200,response.text
            assert len(statements)<=20
            assert response.headers['cache-control']=='private, no-store'
            assert len(response.json()['today_sessions'])==20
            assert response.json()==client.get('/dashboard/daily-overview').json()
            assert client.get('/dashboard/daily-overview',headers={'X-TriCoach-Athlete-Id':foreign_id}).status_code==403
    finally:event.remove(db.bind,'before_cursor_execute',track)
    assert not db.new and not db.dirty and not db.deleted
