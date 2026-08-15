from datetime import date,timedelta
from uuid import UUID,uuid4
from sqlalchemy import select
from app.db.models import CompetitionGoal,UserAthleteMembership
from tests.test_athlete_creation_api import add_athlete,add_user,athlete_env,authenticated_client,mutation_headers
H="X-TriCoach-Athlete-Id"
def payload(name="10K",priority="A"):return {"name":name,"event_date":str(date.today()+timedelta(days=30)),"event_category":"running","event_format":"10k","priority":priority,"distance_m":10000,"target_finish_time_seconds":2700,"notes":"Preparación"}
def post(client,athlete,data=None):return client.post("/competition-goals",json=data or payload(),headers=mutation_headers(client,**{H:str(athlete.id)}))
def test_athlete_crud_multiobjective_and_cancel(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"goals-athlete",account_plan="athlete");a=add_athlete(s,u,"Self",role="athlete",default=True);c=authenticated_client(app,u)
 goals=[post(c,a,payload(f"Goal {p}",p)) for p in "ABC"];assert all(x.status_code==201 for x in goals);listed=c.get("/competition-goals",headers={H:str(a.id)}).json();assert len(listed)==3 and [x["priority"] for x in listed]==list("ABC")
 goal_id=goals[0].json()["id"];updated=c.patch(f"/competition-goals/{goal_id}",json={"name":"Updated"},headers=mutation_headers(c,**{H:str(a.id)}));assert updated.status_code==200 and updated.json()["name"]=="Updated"
 assert c.delete(f"/competition-goals/{goal_id}",headers=mutation_headers(c,**{H:str(a.id)})).status_code==204;assert len(c.get("/competition-goals",headers={H:str(a.id)}).json())==2;assert s.get(CompetitionGoal,UUID(goal_id)).status=="cancelled"
def test_past_and_arbitrary_athlete_id_rejected(athlete_env):
 s,_,app=athlete_env;u=add_user(s,"past-goal",account_plan="athlete");a=add_athlete(s,u,"Self",role="athlete",default=True);c=authenticated_client(app,u);data=payload();data["event_date"]=str(date.today()-timedelta(days=1));data["athlete_profile_id"]=str(uuid4());assert post(c,a,data).status_code==422;data.pop("athlete_profile_id");assert post(c,a,data).json()["detail"]["code"]=="competition_goal_date_in_past"
def test_owner_scoped_and_cross_athlete_isolation(athlete_env):
 s,_,app=athlete_env;owner=add_user(s,"goals-owner");a=add_athlete(s,owner,"A",default=True);b=add_athlete(s,owner,"B");c=authenticated_client(app,owner);created=post(c,a).json();assert c.get(f"/competition-goals/{created['id']}",headers={H:str(b.id)}).status_code==404
 foreign=add_user(s,"goals-foreign",account_plan="athlete");fa=add_athlete(s,foreign,"Foreign",role="athlete",default=True);fc=authenticated_client(app,foreign);assert fc.get(f"/competition-goals/{created['id']}",headers={H:str(fa.id)}).status_code==404
def test_assigned_coach_reads_but_cannot_write_and_revocation_is_immediate(athlete_env):
 s,_,app=athlete_env;owner=add_user(s,"goal-owner");a=add_athlete(s,owner,"A",default=True);oc=authenticated_client(app,owner);goal=post(oc,a).json();coach=add_user(s,"goal-coach",account_plan="coach");membership=UserAthleteMembership(user_id=coach.id,athlete_profile_id=a.id,role="coach",is_active=True,is_default=True);s.add(membership);s.commit();cc=authenticated_client(app,coach);assert len(cc.get("/competition-goals",headers={H:str(a.id)}).json())==1;assert post(cc,a).status_code==403;assert cc.patch(f"/competition-goals/{goal['id']}",json={"name":"No"},headers=mutation_headers(cc,**{H:str(a.id)})).status_code==403;assert cc.delete(f"/competition-goals/{goal['id']}",headers=mutation_headers(cc,**{H:str(a.id)})).status_code==403
 membership.is_active=False;s.commit();assert cc.get("/competition-goals",headers={H:str(a.id)}).status_code==403
def test_unassigned_coach_denied(athlete_env):
 s,_,app=athlete_env;coach=add_user(s,"unassigned-goal-coach",account_plan="coach");owner=add_user(s,"unassigned-owner");a=add_athlete(s,owner,"A",default=True);assert authenticated_client(app,coach).get("/competition-goals",headers={H:str(a.id)}).status_code==403
