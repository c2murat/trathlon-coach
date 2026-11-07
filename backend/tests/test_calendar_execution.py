from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.routes import dashboard
from app.application.calendar_execution import CalendarExecutionApplication
from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.application.planned_session_activity_matching import PlannedSessionActivityMatching
from app.db.models import ActivityLap, ManualStrengthSession, StructuredWorkout, User, UserAthleteMembership
from app.db.session import get_db_session
from tests.test_planned_session_activity_matching import db, athlete, planned, activity
from tests.test_execution_evidence import workout, alternating

NOW=datetime(2026,1,11,12,tzinfo=timezone.utc)
START=date(2026,1,1)
END=date(2026,12,31)

def calendar(db,owner,start=START,end=END,now=NOW):
    return CalendarExecutionApplication(db).assemble(athlete_id=owner.id,start_date=start,end_date=end,
        timezone_name=owner.timezone,now=now)

@pytest.mark.parametrize('duration,planned_duration,status',[
    (2700,2700,'COMPLETED'),(1000,2700,'PARTIAL'),(4000,2700,'OVER_DURATION'),
    (None,2700,'UNMATCHED'),(2700,None,'UNKNOWN'),
])
def test_past_statuses_are_exactly_c1(db,duration,planned_duration,status):
    owner=athlete(db);p=planned(db,owner,duration=planned_duration)
    if duration is not None:
        a=activity(db,owner,duration=duration)
        PlannedSessionActivityMatching(db).create_link(owner.id,p.id,a.id,source='manual')
    db.commit();result=calendar(db,owner)
    expected=PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=owner.id,as_of_date=NOW.date())
    assert result.sessions[0].evidence==expected.sessions[0]
    assert result.sessions[0].evidence.completion_status==status
    assert result.model_dump_json()==calendar(db,owner).model_dump_json()

def test_today_future_and_sessions_outside_range_not_evaluated(db):
    owner=athlete(db);planned(db,owner,day=NOW.date());planned(db,owner,day=date(2026,1,12))
    old=planned(db,owner,day=date(2025,1,1));db.commit()
    assert calendar(db,owner).sessions==()
    historical=calendar(db,owner,start=date(2025,1,1),end=date(2025,12,31))
    assert [x.id for x in historical.sessions]==[old.id]
    assert historical.sessions[0].evidence.completion_status=='UNMATCHED'
    assert PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=owner.id,as_of_date=NOW.date()).window_start_date==date(2025,10,19)

def test_multiple_activities_manual_automatic_provenance_and_tenant_scope(db):
    owner=athlete(db);foreign=athlete(db,'Other');p=planned(db,owner)
    matching=PlannedSessionActivityMatching(db)
    a=activity(db,owner,duration=1000);b=activity(db,owner,hour=9,duration=1700)
    matching.create_link(owner.id,p.id,a.id,source='manual')
    matching.create_link(owner.id,p.id,b.id,source='manual')
    automatic=planned(db,owner,day=date(2026,1,7));auto_activity=activity(db,owner,day=7)
    matching.create_link(owner.id,automatic.id,auto_activity.id,source='automatic')
    foreign_p=planned(db,foreign);foreign_a=activity(db,foreign)
    matching.create_link(foreign.id,foreign_p.id,foreign_a.id,source='manual')
    db.commit();result=calendar(db,owner);views={v.id:v for v in result.sessions}
    assert views[p.id].evidence.actual_duration_seconds==2700
    assert {v.id for v in views[p.id].activities}=={a.id,b.id}
    assert views[p.id].evidence.completion_status=='COMPLETED'
    assert all(v.match_source=='manual' and v.match_confidence=='high' for v in views[p.id].evidence.link_provenance)
    assert views[automatic.id].evidence.link_provenance[0].match_source=='automatic'
    assert foreign_p.id not in views and str(foreign_a.id) not in result.model_dump_json()

def test_manual_strength_session_appears_as_duration_only_activity(db):
    owner=athlete(db);p=planned(db,owner,day=date(2026,1,10),sport='strength',duration=2400)
    manual=ManualStrengthSession(athlete_id=owner.id,started_at=datetime(2026,1,10,18,tzinfo=timezone.utc),
        timezone_name='Europe/Madrid',duration_minutes=40,body_regions=['full_body'],perceived_exertion=None)
    db.add(manual);db.commit()
    result=calendar(db,owner);view=result.sessions[0]
    assert view.id==p.id
    assert view.evidence.completion_status=='COMPLETED'
    assert view.evidence.actual_duration_seconds==2400
    assert view.evidence.target_comparison is None
    assert [(item.id,item.name,item.duration_seconds,item.distance_meters) for item in view.activities]==[(manual.id,'Fuerza manual',2400,None)]

@pytest.mark.parametrize('with_laps',[True,False])
def test_structured_adherence_uses_only_existing_c1_laps(db,with_laps):
    owner=athlete(db);p=planned(db,owner);a=activity(db,owner);definition=workout(reps=5)
    db.add(StructuredWorkout(planned_training_session_id=p.id,schema_version=1,definition=definition.model_dump(mode='json')))
    PlannedSessionActivityMatching(db).create_link(owner.id,p.id,a.id,source='manual')
    a.average_speed_mps=1000/220
    if with_laps:
        for lap in alternating(a.id,'running',[220]*5):
            db.add(ActivityLap(completed_activity_id=a.id,provider_index=lap.lap_index,lap_index=lap.lap_index,
                moving_time_seconds=lap.duration_seconds,elapsed_time_seconds=lap.duration_seconds,distance_metres=float(lap.distance_m)))
    db.commit();target=calendar(db,owner).sessions[0].evidence.target_comparison
    if with_laps:assert target.matched_repetitions==5 and target.target_hit_fraction==1
    else:assert target is None

@pytest.mark.parametrize('instant,expected',[
    ('2026-07-10T22:30:00+00:00',date(2026,7,11)),
    ('2026-01-10T23:30:00+00:00',date(2026,1,11)),
    ('2026-01-10T22:30:00+00:00',date(2026,1,10)),
])
def test_athlete_local_cutoff_and_dst(db,instant,expected):
    owner=athlete(db);today=planned(db,owner,day=expected);past=planned(db,owner,day=expected.replace(day=expected.day-1));db.commit()
    result=calendar(db,owner,now=datetime.fromisoformat(instant))
    assert result.as_of_date==expected and result.timezone=='Europe/Madrid'
    assert [x.id for x in result.sessions]==[past.id] and today.id not in [x.id for x in result.sessions]

@pytest.mark.parametrize('role',['owner','athlete','coach'])
def test_endpoint_permissions_readonly_range_and_constant_queries(db,monkeypatch,role):
    owner=athlete(db);foreign=athlete(db,'Foreign')
    viewer=User(email='calendar@example.invalid',normalized_email='calendar@example.invalid',auth_subject='calendar',timezone='UTC')
    db.add(viewer);db.flush()
    db.add(UserAthleteMembership(user_id=viewer.id,athlete_profile_id=owner.id,role=role,is_active=True,is_default=True))
    p=planned(db,owner);a=activity(db,owner)
    PlannedSessionActivityMatching(db).create_link(owner.id,p.id,a.id,source='manual')
    for _ in range(100):planned(db,owner)
    db.commit();viewer_id=viewer.id;foreign_id=str(foreign.id)
    app=FastAPI();app.include_router(dashboard.router)
    app.dependency_overrides[get_db_session]=lambda:db
    app.dependency_overrides[get_current_user]=lambda:AuthenticatedUser(id=viewer_id)
    monkeypatch.setattr(dashboard,'utc_now',lambda:NOW)
    statements=[]
    def track(conn,cursor,sql,*args):
        assert sql.lstrip().upper().startswith('SELECT')
        statements.append(sql)
    event.listen(db.bind,'before_cursor_execute',track)
    try:
        with TestClient(app) as client:
            for end in ['2026-01-31','2026-12-31']:
                statements.clear()
                response=client.get(f'/dashboard/calendar-execution?start_date=2026-01-01&end_date={end}')
                assert response.status_code==200,response.text
                assert response.headers['cache-control']=='private, no-store'
                assert len(response.json()['sessions'])==101
                assert len(statements)<=6  # Membership + athlete, and five C.1 batch queries.
            assert client.get('/dashboard/calendar-execution?start_date=2026-01-01&end_date=2026-12-31',headers={'X-TriCoach-Athlete-Id':foreign_id}).status_code==403
            for query in ['start_date=2026-02-01&end_date=2026-01-01','start_date=2025-01-01&end_date=2026-01-02','start_date=1999-01-01&end_date=1999-01-02','start_date=no&end_date=2026-01-01']:
                assert client.get('/dashboard/calendar-execution?'+query).status_code==422
    finally:event.remove(db.bind,'before_cursor_execute',track)
    assert not db.new and not db.dirty and not db.deleted
