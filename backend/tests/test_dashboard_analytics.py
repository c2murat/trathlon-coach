from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.db.base import Base
from app.db.models import AthleteProfile, CompletedActivity, User
from app.db.session import get_db_session
from app.main import create_app

@pytest.fixture
def dashboard_client():
    engine=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool);Base.metadata.create_all(engine)
    with Session(engine) as s:
        user=User(id=LOCAL_MVP_USER_ID,email="a@example.invalid",normalized_email="a@example.invalid",auth_subject="a",timezone="UTC"); athlete=AthleteProfile(user=user,timezone="UTC",unit_system="metric")
        other=User(email="b@example.invalid",normalized_email="b@example.invalid",auth_subject="b"); other_athlete=AthleteProfile(user=other)
        s.add_all([user,athlete,other,other_athlete]);s.flush(); now=datetime.now(timezone.utc)
        for days,sport,moving,distance in [(0,"running",3600,10000),(1,"cycling",7200,50000),(8,"swimming",1800,1500)]:
            s.add(CompletedActivity(athlete=athlete,source_summary="strava",sport=sport,name=sport,start_at=now-timedelta(days=days),timezone="UTC",elapsed_time_s=moving,moving_time_s=moving,distance_m=distance,elevation_gain_m=100))
        s.add(CompletedActivity(athlete=other_athlete,source_summary="strava",sport="running",name="secret",start_at=now,timezone="UTC",elapsed_time_s=1,moving_time_s=1))
        s.add(CompletedActivity(athlete=athlete,source_summary="strava",sport="running",name="deleted",start_at=now,timezone="UTC",elapsed_time_s=1,deleted_at=now))
        s.commit()
    def db():
        with Session(engine) as s: yield s
    app=create_app();app.dependency_overrides[get_db_session]=db
    with TestClient(app) as client: yield client
    engine.dispose()

def test_weekly_summary_breakdown_ownership_and_deleted(dashboard_client):
    body=dashboard_client.get("/dashboard/summary?period=week").json(); assert body["activity_count"] in {1,2}; assert len(body["sport_breakdown"])==4; assert "secret" not in str(body); assert body["active_days"]>=1
@pytest.mark.parametrize("period",["month","last_30_days","year"])
def test_supported_summaries(dashboard_client,period): assert dashboard_client.get(f"/dashboard/summary?period={period}").status_code==200
def test_invalid_period_and_limits(dashboard_client):
    assert dashboard_client.get("/dashboard/summary?period=bad").status_code==422
    assert dashboard_client.get("/dashboard/trends?weeks=3").status_code==422
    assert dashboard_client.get("/dashboard/consistency?weeks=53").status_code==422
def test_trends_order_iso_boundaries_and_safe_shape(dashboard_client):
    body=dashboard_client.get("/dashboard/trends?weeks=8").json(); assert len(body)==8; assert [x["week_start"] for x in body]==sorted(x["week_start"] for x in body); assert all(datetime.fromisoformat(x["week_start"]).weekday()==0 for x in body)
def test_consistency_streaks_and_serialization(dashboard_client):
    response=dashboard_client.get("/dashboard/consistency?weeks=12"); assert response.status_code==200; body=response.json(); assert body["active_weeks"]>=1; assert body["longest_training_streak_weeks"]>=1; assert "token" not in response.text
