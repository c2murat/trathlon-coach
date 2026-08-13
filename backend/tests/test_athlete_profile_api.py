from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.api.dependencies.athlete_permissions import AthleteCapability,capabilities_for_role
from app.application.athlete_profile import AthleteProfileApplication,AthleteProfileValidationError,get_athlete_profile_completeness
from app.db.models import AthletePerformanceProfileVersion,CompletedActivity,IntegrationAccount,UserAthleteMembership
from tests.test_athlete_creation_api import add_athlete,add_user,athlete_env,authenticated_client,mutation_headers
H="X-TriCoach-Athlete-Id"
def update(c,a,p,headers=None):return c.patch("/athlete/profile",json=p,headers=headers if headers is not None else mutation_headers(c,**{H:str(a.id)}))
def test_get_and_deterministic_completeness(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"get-profile");a=add_athlete(s,u,"Jenny",default=True);r=authenticated_client(app,u).get("/athlete/profile",headers={H:str(a.id)});assert r.status_code==200;b=r.json();assert set(b)=={"id","display_name","timezone","unit_system","birth_year","sex_for_training_context","height_m","weight_kg","updated_at","completeness"};assert b["completeness"]=={"status":"minimal","missing_recommended_fields":["birth_year","sex_for_training_context","height_m","weight_kg"]}
def test_partial_normalization_decimal_contextual_and_null_clear(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"patch-profile");a=add_athlete(s,u,"Jenny",default=True);c=authenticated_client(app,u);r=update(c,a,{"display_name":"  Jenny   Ruiz ","timezone":"Europe/Madrid","unit_system":"imperial","birth_year":1900,"sex_for_training_context":" existing-value ","height_m":1.789,"weight_kg":63.125});assert r.status_code==200;assert r.json()["display_name"]=="Jenny Ruiz" and r.json()["completeness"]=={"status":"contextual","missing_recommended_fields":[]};r=update(c,a,{"birth_year":None,"sex_for_training_context":None,"height_m":None,"weight_kg":None});assert r.json()["completeness"]["status"]=="minimal" and r.json()["timezone"]=="Europe/Madrid"
@pytest.mark.parametrize("role,code",[("owner",200),("athlete",200),("editor",200),("coach",403),("viewer",403)])
def test_role_matrix(athlete_env,role,code):
 s,_,app=athlete_env;u=add_user(s,"role-"+role);a=add_athlete(s,u,role,role=role,default=True);c=authenticated_client(app,u);assert c.get("/athlete/profile",headers={H:str(a.id)}).status_code==200;assert update(c,a,{"birth_year":2000}).status_code==code;assert (AthleteCapability.EDIT_ATHLETE_PROFILE in capabilities_for_role(role))is(code==200)
@pytest.mark.parametrize("payload",[{}, {"display_name":None},{"timezone":None},{"unit_system":None},{"display_name":"   "},{"display_name":"x"*201},{"timezone":"Madrid"},{"timezone":"x"*65},{"unit_system":"other"},{"birth_year":1899},{"birth_year":date.today().year+1},{"sex_for_training_context":" "},{"sex_for_training_context":"x"*33},{"height_m":0},{"height_m":-1},{"height_m":100},{"weight_kg":0},{"weight_kg":1000},{"user_id":str(uuid4())},{"role":"owner"},{"is_default":True},{"ftp":250},{"unknown_field":True}])
def test_invalid_payload_is_422_and_atomic(athlete_env,payload):
 s,_,app=athlete_env;u=add_user(s,uuid4().hex);a=add_athlete(s,u,"Original",default=True);r=update(authenticated_client(app,u),a,payload);assert r.status_code==422;s.refresh(a);assert a.display_name=="Original";assert r.json()["detail"].get("code")=="athlete_profile_update_empty" if payload=={} else True
def test_birth_year_boundaries_with_clock(athlete_env):
 s,_,_=athlete_env;u=add_user(s,"clock");a=add_athlete(s,u,"A",default=True);service=AthleteProfileApplication(s,today=lambda:date(2026,1,1));service.update(a,{"birth_year":1900});service.update(a,{"birth_year":2026});
 for bad in (1899,2027):
  with pytest.raises(AthleteProfileValidationError):service.update(a,{"birth_year":bad})
def test_a_b_isolation_and_current_default_semantics(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"ab-profile");a=add_athlete(s,u,"Carlos",default=True);b=add_athlete(s,u,"Jenny");a.birth_year=1980;a.height_m=Decimal("1.800");a.weight_kg=Decimal("75");s.commit();c=authenticated_client(app,u);assert c.get("/athlete/profile").json()["id"]==str(a.id);assert c.get("/athlete/profile",headers={H:str(b.id)}).json()["birth_year"]is None;assert update(c,b,{"birth_year":1985,"height_m":1.7,"weight_kg":63.5}).status_code==200;s.refresh(a);assert(a.birth_year,a.height_m,a.weight_kg)==(1980,Decimal("1.800"),Decimal("75.000"));update(c,a,{"weight_kg":74});s.refresh(b);assert b.weight_kg==Decimal("63.500")
def test_cross_user_and_deleted_rejected(athlete_env):
 s,_,app=athlete_env;ua=add_user(s,"cross-pa");ub=add_user(s,"cross-pb");foreign=add_athlete(s,ub,"Foreign",default=True);deleted=add_athlete(s,ua,"Deleted",deleted=True);c=authenticated_client(app,ua)
 for a in(foreign,deleted):assert c.get("/athlete/profile",headers={H:str(a.id)}).status_code==403;assert update(c,a,{"birth_year":2000}).status_code==403
def test_capabilities_are_per_selected_membership_without_union(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"mixed-roles");a=add_athlete(s,u,"Self",role="athlete",default=True);b=add_athlete(s,u,"Read only",role="viewer");c=authenticated_client(app,u)
 assert update(c,a,{"birth_year":2000}).status_code==200
 assert c.get("/athlete/profile",headers={H:str(b.id)}).status_code==200
 assert update(c,b,{"birth_year":2001}).status_code==403
 ma=s.query(UserAthleteMembership).filter_by(user_id=u.id,athlete_profile_id=a.id).one();mb=s.query(UserAthleteMembership).filter_by(user_id=u.id,athlete_profile_id=b.id).one();ma.role="viewer";mb.role="athlete";s.commit()
 assert update(c,a,{"birth_year":2002}).status_code==403
 assert update(c,b,{"birth_year":2003}).status_code==200
def test_auth_csrf_origin(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"secure-profile");a=add_athlete(s,u,"A",default=True);assert TestClient(app).get("/athlete/profile",headers={H:str(a.id)}).status_code==401;c=authenticated_client(app,u);assert c.get("/athlete/profile",headers={H:str(a.id)}).status_code==200;assert c.patch("/athlete/profile",json={"birth_year":2000},headers={H:str(a.id)}).status_code==403;assert c.patch("/athlete/profile",json={"birth_year":2000},headers={H:str(a.id),"X-CSRF-Token":"bad"}).json()["detail"]["code"]=="csrf_validation_failed";bad=mutation_headers(c,Origin="https://evil.test",**{H:str(a.id)});assert c.patch("/athlete/profile",json={"birth_year":2000},headers=bad).json()["detail"]["code"]=="origin_validation_failed"
def test_independent_account_performance_activity_strava_and_context_rename(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"independent-profile");a=add_athlete(s,u,"Before",default=True);before=(u.display_name,u.email,u.timezone,u.password_hash);v=AthletePerformanceProfileVersion(athlete_profile_id=a.id,effective_from=datetime.now(timezone.utc),data_origin="athlete_entered",algorithm_version="0.7a.1",weight_kg=Decimal("70"));act=CompletedActivity(athlete_id=a.id,source_summary="manual",sport="running",name="Run",start_at=datetime.now(timezone.utc),timezone="UTC",elapsed_time_s=600);account=IntegrationAccount(athlete_id=a.id,provider="strava",external_account_id="external-1",status="disconnected",scopes=[]);s.add_all([v,act,account]);s.commit();c=authenticated_client(app,u);assert update(c,a,{"display_name":"After","timezone":"Europe/Madrid","unit_system":"imperial","weight_kg":75}).status_code==200;s.refresh(u);s.refresh(v);s.refresh(act);s.refresh(account);assert(u.display_name,u.email,u.timezone,u.password_hash)==before and v.weight_kg==Decimal("70.000");assert c.get("/session/context").json()["athletes"][0]["label"]=="After"
def test_completeness_pure_not_persisted(athlete_env):
 s,_,_=athlete_env;u=add_user(s,"pure-profile");a=add_athlete(s,u,"A",default=True);x=get_athlete_profile_completeness(a);assert x.missing_recommended_fields==("birth_year","sex_for_training_context","height_m","weight_kg");assert"profile_complete"not in a.__table__.columns
