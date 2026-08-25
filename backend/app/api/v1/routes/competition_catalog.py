from datetime import date
from typing import Annotated,Literal
from fastapi import APIRouter,Depends,HTTPException,Query,status
from pydantic import BaseModel,Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.dependencies.auth import AuthenticatedUser,get_current_user
from app.api.dependencies.athlete_permissions import AthleteCapability,require_athlete_capability
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.routes.competition_goals import response
from app.api.v1.schemas.competition_goals import CompetitionGoalResponse
from app.application.competition_catalog import CompetitionCatalogRegistry,build_catalog_registry
from app.application.competition_goals import CompetitionGoalApplication,CompetitionGoalError
from app.core.settings import Settings,get_settings
from app.db.session import get_db_session
from app.domains.competition_catalog.models import CatalogError,CatalogEvent,CatalogProviderInfo,CatalogSearch,WebCompetitionSearchResponse
router=APIRouter(prefix="/competition-catalog",tags=["competition-catalog"]);manage=require_athlete_capability(AthleteCapability.MANAGE_COMPETITION_GOALS)
def registry(settings:Settings=Depends(get_settings)):return build_catalog_registry(settings)
def failure(exc):
 codes={"provider_not_configured":503,"provider_temporarily_unavailable":503,"provider_timeout":504,"provider_invalid_response":502,"competition_not_found":404,"provider_unknown":404,"provider_request_rejected":502,"provider_rate_limited":429,"provider_authentication_failed":503,"provider_evidence_insufficient":422,"provider_extract_failed":502};raise HTTPException(status_code=codes.get(exc.code,422),detail={"code":exc.code}) from None
class ImportRequest(BaseModel):provider:str=Field(min_length=1,max_length=64);external_id:str=Field(min_length=1,max_length=200);priority:str=Field(pattern="^[ABC]$");target_finish_time_seconds:int|None=Field(default=None,gt=0);notes:str|None=Field(default=None,max_length=4000)
@router.get("/providers",response_model=list[CatalogProviderInfo])
def providers(_:AuthenticatedUser=Depends(get_current_user),catalog:CompetitionCatalogRegistry=Depends(registry)):return catalog.infos()
@router.get("/search",response_model=list[CatalogEvent])
def search(_:AuthenticatedUser=Depends(get_current_user),catalog:CompetitionCatalogRegistry=Depends(registry),text:str|None=Query(default=None,max_length=200),category:Literal["triathlon","running","cycling","swimming","duathlon","aquathlon"]|None=None,start_date:date|None=None,end_date:date|None=None,location:str|None=Query(default=None,max_length=120),provider:str|None=None):
 try:
  if start_date and end_date and start_date>end_date:raise HTTPException(status_code=422,detail={"code":"catalog_filters_invalid"})
  return catalog.search(CatalogSearch(text=text,category=category,start_date=start_date,end_date=end_date,location=location),provider)
 except CatalogError as exc:failure(exc)
@router.get("/web-search",response_model=WebCompetitionSearchResponse)
def web_search(_:AuthenticatedUser=Depends(get_current_user),catalog:CompetitionCatalogRegistry=Depends(registry),provider:str=Query(min_length=1,max_length=64),phase:Literal["initial","more"]="initial",text:str|None=Query(default=None,max_length=200),category:Literal["triathlon","running","cycling","swimming","duathlon","aquathlon"]|None=None,start_date:date|None=None,end_date:date|None=None,location:str|None=Query(default=None,max_length=120)):
 try:
  if start_date and end_date and start_date>end_date:raise HTTPException(status_code=422,detail={"code":"catalog_filters_invalid"})
  results,has_more=catalog.web_search(CatalogSearch(text=text,category=category,start_date=start_date,end_date=end_date,location=location),provider,phase)
  return {"results":results,"has_more":has_more,"phase":phase}
 except CatalogError as exc:failure(exc)
@router.get("/{provider}/events/{external_id}",response_model=CatalogEvent)
def detail(provider:str,external_id:str,_:AuthenticatedUser=Depends(get_current_user),catalog:CompetitionCatalogRegistry=Depends(registry)):
 try:
  selected=catalog.provider(provider)
  if not getattr(selected,"supports_structured_detail",True):raise CatalogError("provider_search_mode_invalid")
  return selected.detail(external_id)
 except CatalogError as exc:failure(exc)
@router.post("/import",response_model=CompetitionGoalResponse,status_code=201)
def import_goal(payload:ImportRequest,current:CurrentAthleteContext=Depends(manage),session:Session=Depends(get_db_session),catalog:CompetitionCatalogRegistry=Depends(registry)):
 service=CompetitionGoalApplication(session)
 try:
  existing=service.imported(current.athlete_id,payload.provider,payload.external_id)
  if existing:raise HTTPException(status_code=409,detail={"code":"competition_already_imported","goal_id":str(existing.id)})
  selected=catalog.provider(payload.provider)
  if not getattr(selected,"supports_structured_import",True):raise CatalogError("provider_search_mode_invalid")
  event=selected.detail(payload.external_id);snapshot=event.model_dump(mode="json");goal=service.create(current.athlete_id,current.user_id,current.athlete_profile.timezone,{"name":event.name,"event_date":event.start_date,"event_category":event.category or "triathlon","event_format":event.event_format or "custom","priority":payload.priority,"segments":[x.model_dump(exclude={"position"}) for x in event.segments],"target_finish_time_seconds":payload.target_finish_time_seconds,"notes":payload.notes,"city":event.city,"region":event.region,"country":event.country},{"source_provider":event.provider,"source_external_id":event.external_id,"source_url":event.source_url,"source_retrieved_at":event.retrieved_at,"source_snapshot":snapshot});session.commit();return response(goal)
 except HTTPException:session.rollback();raise
 except CatalogError as exc:session.rollback();failure(exc)
 except (CompetitionGoalError,ValueError):session.rollback();raise HTTPException(status_code=422,detail={"code":"competition_import_invalid"}) from None
 except IntegrityError:session.rollback();raise HTTPException(status_code=409,detail={"code":"competition_already_imported"}) from None
