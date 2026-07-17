from dataclasses import asdict
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field
from starlette.concurrency import run_in_threadpool
from app.api.dependencies.auth import AuthenticatedUser,get_current_user
from app.api.dependencies.providers import get_strava_evidence_manager
from app.application.queries.activity_evidence import ActivityEvidenceQuery
from app.core.settings import Settings,get_settings
from app.db.session import get_db_session
from app.integrations.strava.activity_evidence import EvidenceConnectionRequiredError,EvidenceJobNotFoundError,EvidenceSelectionError,StravaActivityEvidenceManager
from sqlalchemy.orm import Session
HEADERS={"Cache-Control":"no-store","Pragma":"no-cache"};router=APIRouter(tags=["activities","integrations"])
class EvidenceRequest(BaseModel):
 activity_ids:list[UUID]|None=Field(None,max_length=10)
 include_laps:bool=True;include_streams:bool=True;include_location:bool=False
@router.post("/integrations/strava/evidence",status_code=202)
async def start_evidence(body:EvidenceRequest,current_user:AuthenticatedUser=Depends(get_current_user),manager:StravaActivityEvidenceManager=Depends(get_strava_evidence_manager)):
 try:job=await run_in_threadpool(manager.create_job,current_user.id,activity_ids=body.activity_ids,include_laps=body.include_laps,include_streams=body.include_streams,include_location=body.include_location)
 except EvidenceConnectionRequiredError:raise HTTPException(409,detail={"code":"strava_connection_required"},headers=HEADERS) from None
 except EvidenceSelectionError:raise HTTPException(422,detail={"code":"invalid_evidence_selection"},headers=HEADERS) from None
 except Exception:raise HTTPException(500,detail={"code":"strava_evidence_start_failed"},headers=HEADERS) from None
 manager.schedule(job.job_id);return JSONResponse({"job_id":str(job.job_id),"status":job.status},202,headers=HEADERS)
@router.get("/integrations/strava/evidence/{job_id}")
def evidence_status(job_id:UUID,current_user:AuthenticatedUser=Depends(get_current_user),manager:StravaActivityEvidenceManager=Depends(get_strava_evidence_manager)):
 try:job=manager.job_for_user(current_user.id,job_id)
 except EvidenceJobNotFoundError:raise HTTPException(404,detail={"code":"strava_evidence_not_found"},headers=HEADERS) from None
 return JSONResponse(jsonable_encoder(asdict(job)),headers=HEADERS)
@router.delete("/integrations/strava/evidence/location")
def cleanup_location(current_user:AuthenticatedUser=Depends(get_current_user),manager:StravaActivityEvidenceManager=Depends(get_strava_evidence_manager)):
 return JSONResponse({"deleted_count":manager.cleanup_location_for_user(current_user.id)},headers=HEADERS)
@router.get("/activities/{activity_id}/evidence")
def activity_evidence(activity_id:UUID,current_user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session),settings:Settings=Depends(get_settings)):
 value=ActivityEvidenceQuery(session,location_enabled=settings.activity_location_stream_retention_enabled,max_samples=settings.activity_stream_max_samples).for_user(current_user.id,activity_id)
 if value is None:raise HTTPException(404,detail={"code":"activity_evidence_not_found"},headers=HEADERS)
 return JSONResponse(jsonable_encoder(value),headers=HEADERS)
