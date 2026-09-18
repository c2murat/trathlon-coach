from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.routes.dashboard import router
from app.application.execution_overview import ExecutionOverviewApplication
from app.application.planned_session_activity_matching import PlannedSessionActivityMatching
from app.db.models import ActivityLap, StructuredWorkout, User, UserAthleteMembership
from app.db.session import get_db_session
from tests.test_planned_session_activity_matching import db, athlete, activity, planned
from tests.test_execution_evidence import workout, alternating

CUTOFF=date(2026,1,11)


def overview(db,owner):
    return ExecutionOverviewApplication(db).assemble(athlete_id=owner.id,as_of_date=CUTOFF,timezone_name=owner.timezone)


@pytest.mark.parametrize("duration,expected",[(2700,"COMPLETED"),(1000,"PARTIAL"),(4000,"OVER_DURATION")])
def test_overview_reuses_c1_duration_evidence(db,duration,expected):
    owner=athlete(db);session=planned(db,owner);actual=activity(db,owner,duration=duration)
    PlannedSessionActivityMatching(db).create_link(owner.id,session.id,actual.id,source="manual")
    db.commit();result=overview(db,owner)
    assert result.recent_sessions[0].evidence.completion_status==expected
    assert result.latest_activity_sessions[0].id==session.id
    assert result.latest_activity.duration_seconds==duration
    assert "score" not in result.model_dump_json()


def test_unmatched_unknown_multiple_activities_and_scope(db):
    owner=athlete(db);other=athlete(db,"B")
    missing=planned(db,owner);unknown=planned(db,owner,duration=None)
    foreign=planned(db,other);activity(db,other)
    first=activity(db,owner,duration=1000);second=activity(db,owner,hour=9,duration=1700)
    app=PlannedSessionActivityMatching(db)
    app.create_link(owner.id,unknown.id,first.id,source="manual")
    app.create_link(owner.id,unknown.id,second.id,source="manual")
    db.commit();views={item.id:item for item in overview(db,owner).recent_sessions}
    assert views[missing.id].evidence.completion_status=="UNMATCHED"
    assert views[unknown.id].evidence.completion_status=="UNKNOWN"
    assert views[unknown.id].evidence.actual_duration_seconds==2700
    assert len(views[unknown.id].activities)==2
    assert len(views[unknown.id].evidence.link_provenance)==2
    assert foreign.id not in views


@pytest.mark.parametrize("with_laps",[True,False])
def test_structured_evidence_uses_persisted_laps_only(db,with_laps):
    owner=athlete(db);session=planned(db,owner);actual=activity(db,owner)
    definition=workout(reps=5)
    db.add(StructuredWorkout(planned_training_session_id=session.id,schema_version=1,definition=definition.model_dump(mode="json")))
    PlannedSessionActivityMatching(db).create_link(owner.id,session.id,actual.id,source="manual")
    if with_laps:
        for lap in alternating(actual.id,"running",[220]*5):
            db.add(ActivityLap(completed_activity_id=actual.id,provider_index=lap.lap_index,lap_index=lap.lap_index,
                moving_time_seconds=lap.duration_seconds,elapsed_time_seconds=lap.duration_seconds,distance_metres=float(lap.distance_m)))
    actual.average_speed_mps=1000/220
    db.commit();item=overview(db,owner).recent_sessions[0]
    assert item.workout==definition
    if with_laps:
        assert item.evidence.target_comparison.matched_repetitions==5
        assert item.evidence.target_comparison.target_hit_fraction==1
    else: assert item.evidence.target_comparison is None


def test_api_readonly_deterministic_authorized_and_bounded(db):
    owner=athlete(db);other=athlete(db,"B");actual=activity(db,owner)
    for day in range(1,10): planned(db,owner,day=date(2026,1,day))
    planned(db,owner,day=date(2026,1,12))
    user=User(email="q@example.invalid",normalized_email="q@example.invalid",auth_subject="q",timezone="UTC")
    db.add(user);db.flush()
    db.add(UserAthleteMembership(user_id=user.id,athlete_profile_id=owner.id,role="athlete",is_active=True,is_default=True))
    db.commit();app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_current_user]=lambda:AuthenticatedUser(id=user.id)
    app.dependency_overrides[get_db_session]=lambda:db
    statements=[]
    def check(conn,cursor,sql,*args):
        assert sql.lstrip().upper().startswith("SELECT")
        statements.append(sql)
    # Load expired fixture identities before installing the read-only SQL guard.
    user.id;owner.id;other_id=str(other.id)
    event.listen(db.bind,"before_cursor_execute",check)
    try:
        client=TestClient(app);first=client.get("/dashboard/execution-overview?as_of_date=2026-01-11")
        assert first.status_code==200
        assert len(statements)<=8  # Constant batch reads, never one query per session.
        assert len(first.json()["recent_sessions"])==5
        assert first.json()==client.get("/dashboard/execution-overview?as_of_date=2026-01-11").json()
        assert client.get("/dashboard/execution-overview",headers={"X-TriCoach-Athlete-Id":other_id}).status_code==403
        assert client.get("/dashboard/execution-overview?as_of_date=2999-01-01").status_code==422
        assert not db.new and not db.dirty and not db.deleted
    finally:event.remove(db.bind,"before_cursor_execute",check)


def test_today_link_is_evaluated_by_c1_without_including_unelapsed_today_in_recent(db):
    owner=athlete(db);session=planned(db,owner,day=CUTOFF);actual=activity(db,owner,day=11)
    PlannedSessionActivityMatching(db).create_link(owner.id,session.id,actual.id,source="manual")
    db.commit();result=overview(db,owner)
    assert result.recent_sessions==()
    assert result.latest_activity_sessions[0].id==session.id
    assert result.latest_activity_sessions[0].evidence.completion_status=="COMPLETED"
