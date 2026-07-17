from dataclasses import asdict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.dependencies.providers import get_strava_enrichment_manager
from app.integrations.strava.activity_enrichment import EnrichmentConnectionRequiredError, EnrichmentJobNotFoundError, EnrichmentSelectionError, StravaActivityEnrichmentManager
router=APIRouter(prefix="/integrations/strava/enrichments",tags=["integrations"])
HEADERS={"Cache-Control":"no-store","Pragma":"no-cache"}
class EnrichmentRequest(BaseModel):
 activity_ids:list[UUID]|None=None
 limit:int|None=Field(None,ge=1,le=50)
@router.post("",status_code=status.HTTP_202_ACCEPTED)
async def start_enrichment(body:EnrichmentRequest|None=None,current_user:AuthenticatedUser=Depends(get_current_user),manager:StravaActivityEnrichmentManager=Depends(get_strava_enrichment_manager)):
 try:job=await run_in_threadpool(manager.create_job,current_user.id,activity_ids=body.activity_ids if body else None,limit=body.limit if body else None)
 except EnrichmentConnectionRequiredError:raise HTTPException(409,detail={"code":"strava_connection_required"},headers=HEADERS) from None
 except EnrichmentSelectionError:raise HTTPException(422,detail={"code":"invalid_enrichment_selection"},headers=HEADERS) from None
 except Exception:raise HTTPException(500,detail={"code":"strava_enrichment_start_failed"},headers=HEADERS) from None
 manager.schedule(job.job_id)
 return JSONResponse({"job_id":str(job.job_id),"status":job.status},status_code=202,headers=HEADERS)
@router.get("/{job_id}")
async def enrichment_status(job_id:UUID,current_user:AuthenticatedUser=Depends(get_current_user),manager:StravaActivityEnrichmentManager=Depends(get_strava_enrichment_manager)):
 try:job=await run_in_threadpool(manager.job_for_user,current_user.id,job_id)
 except EnrichmentJobNotFoundError:raise HTTPException(404,detail={"code":"strava_enrichment_not_found"},headers=HEADERS) from None
 except Exception:raise HTTPException(500,detail={"code":"strava_enrichment_status_unavailable"},headers=HEADERS) from None
 return JSONResponse(jsonable_encoder(asdict(job)),headers=HEADERS)
