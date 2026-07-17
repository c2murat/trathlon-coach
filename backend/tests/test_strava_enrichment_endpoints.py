from datetime import datetime,timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from app.api.dependencies.providers import get_strava_enrichment_manager
from app.integrations.strava.activity_enrichment import EnrichmentJobNotFoundError,StravaEnrichmentJobView
from app.main import create_app
class Manager:
 def __init__(self):self.job_id=uuid4();self.scheduled=[];self.selection=None
 def create_job(self,user_id,*,activity_ids=None,limit=None):
  self.selection=(user_id,activity_ids,limit);now=datetime.now(timezone.utc);return StravaEnrichmentJobView(self.job_id,"queued",len(activity_ids or []),0,0,0,0,None,None,now,None,None,None)
 def schedule(self,job_id):self.scheduled.append(job_id)
 def job_for_user(self,user_id,job_id):
  if job_id!=self.job_id:raise EnrichmentJobNotFoundError
  now=datetime.now(timezone.utc);return StravaEnrichmentJobView(job_id,"succeeded",1,1,1,0,0,str(uuid4()),now,now,now,None,None)
def test_enrichment_endpoints_return_202_and_allowlisted_owned_progress():
 app=create_app();manager=Manager();app.dependency_overrides[get_strava_enrichment_manager]=lambda:manager
 with TestClient(app) as client:
  activity_id=uuid4();started=client.post("/integrations/strava/enrichments",json={"activity_ids":[str(activity_id)],"limit":1});assert started.status_code==202 and started.json()=={"job_id":str(manager.job_id),"status":"queued"};assert manager.scheduled==[manager.job_id]
  response=client.get(f"/integrations/strava/enrichments/{manager.job_id}");assert response.status_code==200;assert set(response.json())=={"job_id","status","selected_count","enriched_count","updated_count","skipped_count","failed_count","last_activity_id","started_at","updated_at","completed_at","next_resume_at","error_category"};assert "no-store" in response.headers["cache-control"]
def test_enrichment_status_hides_unowned_or_unknown_jobs():
 app=create_app();manager=Manager();app.dependency_overrides[get_strava_enrichment_manager]=lambda:manager
 with TestClient(app) as client:assert client.get(f"/integrations/strava/enrichments/{uuid4()}").status_code==404
