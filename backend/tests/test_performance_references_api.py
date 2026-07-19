from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.db.base import Base, utc_now
from app.db.models import AthleteProfile, User
from app.db.session import get_db_session
from app.main import create_app

@pytest.fixture
def performance_client():
 e=create_engine("sqlite+pysqlite:///:memory:",connect_args={"check_same_thread":False},poolclass=StaticPool); Base.metadata.create_all(e)
 with Session(e) as s:
  u=User(id=LOCAL_MVP_USER_ID,email="a@a.invalid",normalized_email="a@a.invalid",auth_subject="local"); s.add(AthleteProfile(user=u)); s.commit()
 def override():
  with Session(e) as s: yield s
 app=create_app(); app.dependency_overrides[get_db_session]=override
 with TestClient(app) as c: yield c,e
 app.dependency_overrides.clear(); e.dispose()

def payload(**kw):
 p={"sport":"cycling","metric_type":"power","value":250,"unit":"W","data_origin":"manual","quality_level":"high","effective_from":"2026-01-01T00:00:00Z"}; p.update(kw); return p

def test_post_and_get_reference(performance_client):
 c,_=performance_client; r=c.post("/athlete/performance-references",json=payload()); assert r.status_code==201; body=r.json(); assert body["id"] and body["athlete_profile_id"]; assert c.get("/athlete/performance-references/"+body["id"]).status_code==200
@pytest.mark.parametrize("changes", [{"value":0},{"value":-1},{"data_origin":"measured"},{"data_origin":"derived"},{"sport":"running"},{"sport":"cycling","metric_type":"power","unit":"bpm"}])
def test_invalid_references_are_422(performance_client,changes):
 c,_=performance_client; assert c.post("/athlete/performance-references",json=payload(**changes)).status_code==422

def test_zones_use_granular_reference(performance_client):
 c,_=performance_client; c.post("/athlete/performance-references",json=payload()); r=c.get("/athlete/performance-zones"); assert r.status_code==200; assert any(x["source_type"]=="granular_reference" and x["metric_type"]=="power" for x in r.json())
from datetime import datetime

def test_valid_origins_and_metadata(performance_client):
 c,_=performance_client
 cases=[{"data_origin":"measured","measured_at":"2026-01-02T00:00:00Z"},{"data_origin":"imported","source_note":"Strava"},{"data_origin":"derived","calculation_method":"ftp_percent","algorithm_version":"x"},{"data_origin":"estimated"}]
 for i,extra in enumerate(cases):
  p=payload(effective_from=f"2026-0{i+1}-01T00:00:00Z",**extra); r=c.post("/athlete/performance-references",json=p); assert r.status_code==201; b=r.json(); assert b["data_origin"]==extra["data_origin"] and b["unit"]=="W"

def test_reference_filters_history_and_effective_at(performance_client):
 c,_=performance_client
 c.post("/athlete/performance-references",json=payload(effective_from="2026-01-01T00:00:00Z")); c.post("/athlete/performance-references",json=payload(effective_from="2026-03-01T00:00:00Z",value=300)); c.post("/athlete/performance-references",json=payload(sport="running",metric_type="pace",unit="s/km",value=250,effective_from="2026-02-01T00:00:00Z"))
 assert len(c.get("/athlete/performance-references").json())==2
 assert len(c.get("/athlete/performance-references",params={"sport":"cycling","metric_type":"power"}).json())==1
 assert len(c.get("/athlete/performance-references/history",params={"sport":"cycling"}).json())==2
 assert len(c.get("/athlete/performance-references",params={"effective_at":"2026-02-01T00:00:00Z"}).json())==2
 assert c.get("/athlete/performance-references/history").json()[0]["effective_from"] > c.get("/athlete/performance-references/history").json()[1]["effective_from"]

def test_detail_not_found(performance_client):
 c,_=performance_client; assert c.get("/athlete/performance-references/00000000-0000-0000-0000-000000000000").status_code==404

def test_historical_profile_fallback(performance_client):
 c,_=performance_client
 profile={"effective_from":"2026-01-01T00:00:00Z","data_origin":"manual","algorithm_version":"0.7a.2","cycling_ftp_watts":250,"maximum_heart_rate_bpm":180,"cycling_threshold_heart_rate_bpm":160,"running_threshold_pace_seconds_per_km":270,"running_threshold_heart_rate_bpm":165,"swimming_css_seconds_per_100m":120}
 assert c.post("/athlete/performance-profile/versions",json=profile).status_code in (200,201)
 zones=c.get("/athlete/performance-zones").json(); assert any(z["source_type"]=="historical_profile" and z["reference"]["reference_id"] is None for z in zones)

def test_granular_precedes_historical(performance_client):
 c,_=performance_client
 profile={"effective_from":"2026-01-01T00:00:00Z","data_origin":"manual","algorithm_version":"0.7a.2","cycling_ftp_watts":200}
 assert c.post("/athlete/performance-profile/versions",json=profile).status_code in (200,201)
 r=c.post("/athlete/performance-references",json=payload(value=300)); assert r.status_code==201
 zones=c.get("/athlete/performance-zones").json(); power=[z for z in zones if z["metric_type"]=="power"]; assert len(power)==1 and power[0]["source_type"]=="granular_reference" and power[0]["reference"]["value"]==300
