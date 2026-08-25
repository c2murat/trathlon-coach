from datetime import date,timedelta,datetime,timezone
from uuid import UUID
from sqlalchemy import select
from app.api.v1.routes.competition_catalog import registry
from app.application.competition_catalog import CompetitionCatalogRegistry
from app.db.models import CompetitionGoal
from app.domains.competition_catalog.models import CatalogEvent,CatalogEvidence
from tests.test_athlete_creation_api import add_athlete,add_user,athlete_env,authenticated_client,mutation_headers
H="X-TriCoach-Athlete-Id"
class FakeProvider:
 name="fixture";label="Fixture catalog";configured=True;supported_categories=("triathlon","duathlon","aquathlon")
 def search(self,query):return [self.detail("event-1")]
 def detail(self,external_id):return CatalogEvent(provider=self.name,external_id=external_id,name="Duatlón Madrid",start_date=date.today()+timedelta(days=60),category="duathlon",event_format="special",city="Madrid",country="España",source_url="https://example.test/event-1",segments=[{"position":1,"sport":"run","distance_m":5000},{"position":2,"sport":"bike","distance_m":20000},{"position":3,"sport":"run","distance_m":2500}],retrieved_at=datetime.now(timezone.utc))
def fake_registry():return CompetitionCatalogRegistry([FakeProvider()])
def test_catalog_requires_authentication(athlete_env):
 _,_,app=athlete_env;from fastapi.testclient import TestClient;assert TestClient(app).get("/competition-catalog/providers").status_code==401
def test_search_detail_import_duplicate_snapshot_and_edit_immutability(athlete_env):
 session,_,app=athlete_env;user=add_user(session,"catalog-owner");athlete=add_athlete(session,user,"Owner",default=True);client=authenticated_client(app,user);app.dependency_overrides[registry]=fake_registry
 assert client.get("/competition-catalog/providers").json()[0]["configured"] is True
 found=client.get("/competition-catalog/search?text=Madrid").json()[0];assert found["category"]=="duathlon" and len(found["segments"])==3
 assert client.get("/competition-catalog/fixture/events/event-1").status_code==200
 headers=mutation_headers(client,**{H:str(athlete.id)});created=client.post("/competition-catalog/import",json={"provider":"fixture","external_id":"event-1","priority":"A"},headers=headers);assert created.status_code==201;body=created.json();assert [x["sport"] for x in body["segments"]]==["run","bike","run"]
 assert client.post("/competition-catalog/import",json={"provider":"fixture","external_id":"event-1","priority":"A"},headers=headers).status_code==409
 goal=session.get(CompetitionGoal,UUID(body["id"]));snapshot=dict(goal.source_snapshot);patched=client.patch(f"/competition-goals/{goal.id}",json={"name":"Nombre editado","segments":[{"sport":"run","distance_m":1000}]},headers=headers);assert patched.status_code==200;session.refresh(goal);assert goal.source_snapshot==snapshot
 app.dependency_overrides.pop(registry,None)
def test_coach_can_search_but_cannot_import(athlete_env):
 session,_,app=athlete_env;owner=add_user(session,"catalog-owner-2");athlete=add_athlete(session,owner,"A",default=True);coach=add_user(session,"catalog-coach",account_plan="coach");from app.db.models import UserAthleteMembership;session.add(UserAthleteMembership(user_id=coach.id,athlete_profile_id=athlete.id,role="coach",is_active=True,is_default=True));session.commit();client=authenticated_client(app,coach);app.dependency_overrides[registry]=fake_registry;assert client.get("/competition-catalog/search").status_code==200;assert client.post("/competition-catalog/import",json={"provider":"fixture","external_id":"event-1","priority":"B"},headers=mutation_headers(client,**{H:str(athlete.id)})).status_code==403;app.dependency_overrides.pop(registry,None)


class FakeAIWebProvider(FakeProvider):
 name="ai_web";label="Búsqueda web con IA";supported_categories=("running","cycling","swimming","triathlon","duathlon","aquathlon")
 def detail(self,external_id):
  event=super().detail(external_id);return event.model_copy(update={"provider":"ai_web","source_url":"https://organizer.example/event","confidence":"high","evidence":[{"url":"https://organizer.example/event","title":"Official event","official":True}]})
def fake_ai_registry():return CompetitionCatalogRegistry([FakeAIWebProvider()])
def test_ai_web_endpoints_search_detail_import_snapshot_and_duplicate(athlete_env):
 session,_,app=athlete_env;user=add_user(session,"ai-web-owner");athlete=add_athlete(session,user,"Owner",default=True);client=authenticated_client(app,user);app.dependency_overrides[registry]=fake_ai_registry
 providers=client.get("/competition-catalog/providers").json();assert providers[0]["provider"]=="ai_web" and providers[0]["search_mode"]=="structured" and providers[0]["supports_structured_import"] is True
 found=client.get("/competition-catalog/search?provider=ai_web&text=Madrid");assert found.status_code==200 and found.json()[0]["confidence"]=="high"
 assert client.get("/competition-catalog/ai_web/events/event-1").status_code==200
 headers=mutation_headers(client,**{H:str(athlete.id)});body={"provider":"ai_web","external_id":"event-1","priority":"B"};created=client.post("/competition-catalog/import",json=body,headers=headers);assert created.status_code==201 and created.json()["source_provider"]=="ai_web"
 goal=session.get(CompetitionGoal,UUID(created.json()["id"]));assert goal.source_snapshot["confidence"]=="high" and goal.source_snapshot["evidence"][0]["official"] is True
 assert client.post("/competition-catalog/import",json=body,headers=headers).status_code==409
 app.dependency_overrides.pop(registry,None)

class FakeTavilyProvider(FakeProvider):
 name="tavily";label="Búsqueda web · Tavily";supported_categories=("running","cycling","swimming","triathlon","duathlon","aquathlon")
 search_mode="web";supports_structured_detail=False;supports_structured_import=False;supports_search_to_manual_goal=True
 def search_web(self,query,phase):return ([{"id":"web-1","title":"Carrera Villa X","url":"https://calendar.example/event","snippet":"Inscripción carrera","source_domain":"calendar.example","source_label":"Calendar","source_kind":"web","result_kind":"event_candidate","hints":{}}],phase=="initial")
def fake_tavily_registry():return CompetitionCatalogRegistry([FakeTavilyProvider()])
def test_tavily_web_search_cannot_structured_detail_or_import(athlete_env):
 session,_,app=athlete_env;user=add_user(session,"tavily-owner");athlete=add_athlete(session,user,"Owner",default=True);client=authenticated_client(app,user);app.dependency_overrides[registry]=fake_tavily_registry
 providers=client.get("/competition-catalog/providers").json();assert providers[0]["provider"]=="tavily" and providers[0]["configured"] is True
 assert providers[0]["search_mode"]=="web" and providers[0]["supports_search_to_manual_goal"] is True
 found=client.get("/competition-catalog/web-search?provider=tavily&text=Madrid");assert found.status_code==200 and found.json()["results"][0]["result_kind"]=="event_candidate"
 assert client.get("/competition-catalog/tavily/events/event-1").status_code==422
 headers=mutation_headers(client,**{H:str(athlete.id)});body={"provider":"tavily","external_id":"event-1","priority":"B"};assert client.post("/competition-catalog/import",json=body,headers=headers).status_code==422
 app.dependency_overrides.pop(registry,None)
