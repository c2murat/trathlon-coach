from __future__ import annotations
from datetime import date,datetime
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,model_validator
from sqlalchemy.orm import Session
from app.api.dependencies.auth import AuthenticatedUser,get_current_user
from app.application.queries.activity_summaries import ActivitySummaryQuery
from app.db.session import get_db_session
router=APIRouter(prefix="/activities",tags=["activities"])
class ActivitySummaryResponse(BaseModel):
 id:UUID;external_activity_id:str|None;name:str;sport_type:str;start_time:datetime;athlete_timezone:str;distance_metres:float|None;moving_time_seconds:int|None;elapsed_time_seconds:int;elevation_metres:float|None;average_heart_rate:float|None;average_watts:float|None;trainer:bool|None;manual:bool|None;visibility:str|None
class ActivityPageResponse(BaseModel):total:int;limit:int;offset:int;items:list[ActivitySummaryResponse]
class FilterOptionsResponse(BaseModel):sport_types:list[str];visibility_values:list[str];minimum_activity_date:date|None;maximum_activity_date:date|None
class ActivityDetailResponse(ActivitySummaryResponse):
 max_heart_rate:float|None;average_speed_metres_per_second:float|None;max_speed_metres_per_second:float|None;average_cadence:float|None;weighted_average_watts:float|None;commute:bool|None;created_at:datetime;updated_at:datetime;provider_description:str|None;calories:float|None;device_name:str|None;gear_id:str|None;suffer_score:int|None;perceived_exertion:float|None;total_work_joules:float|None;kilojoules:float|None;average_temperature_celsius:float|None;max_watts:float|None;workout_type:int|None;achievement_count:int|None;kudos_count:int|None;athlete_count:int|None;photo_count:int|None;has_heartrate:bool|None;has_power_meter:bool|None;hide_from_home:bool|None;private:bool|None;flagged:bool|None;enriched_at:datetime|None;enrichment_status:str|None;enrichment_error_category:str|None
class BrowseFilters(BaseModel):
 date_from:date|None=None;date_to:date|None=None;min_distance_metres:float|None=None;max_distance_metres:float|None=None
 @model_validator(mode="after")
 def ranges(self):
  if self.date_from and self.date_to and self.date_from>self.date_to:raise ValueError("date_from must not exceed date_to")
  if self.min_distance_metres is not None and self.max_distance_metres is not None and self.min_distance_metres>self.max_distance_metres:raise ValueError("minimum distance must not exceed maximum")
  return self
@router.get("",response_model=ActivityPageResponse)
def list_activities(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),sport:Literal["swimming","cycling","running","strength","multisport","other"]|None=None,date_from:date|None=None,date_to:date|None=None,min_distance_metres:float|None=Query(None,ge=0),max_distance_metres:float|None=Query(None,ge=0),trainer:bool|None=None,manual:bool|None=None,visibility:Literal["everyone","followers_only","only_me","unknown"]|None=None,search:str|None=Query(None,min_length=1,max_length=300),current_user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 if date_from and date_to and date_from>date_to:raise HTTPException(422,detail={"code":"invalid_date_range"})
 if min_distance_metres is not None and max_distance_metres is not None and min_distance_metres>max_distance_metres:raise HTTPException(422,detail={"code":"invalid_distance_range"})
 page=ActivitySummaryQuery(session).for_user(current_user.id,limit=limit,offset=offset,sport=sport,date_from=date_from,date_to=date_to,min_distance_metres=min_distance_metres,max_distance_metres=max_distance_metres,trainer=trainer,manual=manual,visibility=visibility,search=search)
 return ActivityPageResponse(total=page.total,limit=page.limit,offset=page.offset,items=[ActivitySummaryResponse.model_validate(x,from_attributes=True) for x in page.items])
@router.get("/filter-options",response_model=FilterOptionsResponse)
def filter_options(current_user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 x=ActivitySummaryQuery(session).filter_options(current_user.id);return FilterOptionsResponse(sport_types=list(x.sport_types),visibility_values=list(x.visibility_values),minimum_activity_date=x.minimum_activity_date,maximum_activity_date=x.maximum_activity_date)
@router.get("/{activity_id}",response_model=ActivityDetailResponse)
def activity_detail(activity_id:UUID,current_user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 a=ActivitySummaryQuery(session).detail(current_user.id,activity_id)
 if not a:raise HTTPException(404,detail={"code":"activity_not_found"})
 return ActivityDetailResponse(id=a.id,external_activity_id=a.external_activity_id,name=a.name,sport_type=a.sport,start_time=a.start_at,athlete_timezone=a.timezone,distance_metres=a.distance_m,moving_time_seconds=a.moving_time_s,elapsed_time_seconds=a.elapsed_time_s,elevation_metres=a.elevation_gain_m,average_heart_rate=a.average_heart_rate_bpm,max_heart_rate=a.max_heart_rate_bpm,average_speed_metres_per_second=a.average_speed_mps,max_speed_metres_per_second=a.max_speed_mps,average_cadence=a.average_cadence_rpm,average_watts=a.average_power_w,weighted_average_watts=a.weighted_average_power_w,trainer=a.indoor,commute=a.commute,manual=a.manual,visibility=a.visibility,created_at=a.created_at,updated_at=a.updated_at,provider_description=a.provider_description,calories=a.calories_kcal,device_name=a.device_name,gear_id=a.gear_id,suffer_score=a.suffer_score,perceived_exertion=a.provider_perceived_exertion,total_work_joules=a.total_work_j,kilojoules=a.kilojoules,average_temperature_celsius=a.average_temperature_c,max_watts=a.max_power_w,workout_type=a.workout_type,achievement_count=a.achievement_count,kudos_count=a.kudos_count,athlete_count=a.athlete_count,photo_count=a.photo_count,has_heartrate=a.has_heartrate,has_power_meter=a.has_power_meter,hide_from_home=a.hide_from_home,private=a.private,flagged=a.flagged,enriched_at=a.enriched_at,enrichment_status=a.enrichment_status,enrichment_error_category=a.enrichment_error_category)


