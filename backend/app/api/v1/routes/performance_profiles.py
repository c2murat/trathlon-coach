from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.api.dependencies.auth import AuthenticatedUser,get_current_user
from app.application.performance_profiles import PerformanceProfileError,PerformanceProfileRepository
from app.db.models import AthleteProfile
from app.db.session import get_db_session
from app.domains.performance_profile.zones import *
router=APIRouter(prefix="/athlete/performance-profile",tags=["performance-profile"])
class ProfileIn(BaseModel):
 effective_from:datetime;data_origin:str;source_note:str|None=None;resting_heart_rate_bpm:int|None=None;maximum_heart_rate_bpm:int|None=None;weight_kg:float|None=None;cycling_ftp_watts:float|None=None;cycling_threshold_heart_rate_bpm:int|None=None;running_threshold_heart_rate_bpm:int|None=None;running_threshold_pace_seconds_per_km:float|None=None;swimming_css_seconds_per_100m:float|None=None;preferred_pool_length_metres:int|None=None
class ZoneOut(BaseModel):number:int;name:str;lower:float;upper:float|None;unit:str;direction:str;reference:float;algorithm_version:str
class ProfileOut(ProfileIn):id:str;algorithm_version:str;created_at:datetime;zones:dict[str,list[ZoneOut]]
class CurrentOut(BaseModel):profile:ProfileOut|None;derived:dict[str,float]
def zones(row):
 out={};
 refs=[("heart_rate",Sport.RUNNING,MetricType.HEART_RATE,row.maximum_heart_rate_bpm,Unit.BPM,heart_rate_zones),("cycling_power",Sport.CYCLING,MetricType.POWER,row.cycling_ftp_watts,Unit.WATT,cycling_power_zones),("running_pace",Sport.RUNNING,MetricType.PACE,row.running_threshold_pace_seconds_per_km,Unit.SECOND_PER_KM,running_pace_zones),("swimming",Sport.SWIMMING,MetricType.SWIM_PACE,row.swimming_css_seconds_per_100m,Unit.SECOND_PER_100M,swimming_zones)]
 for key,sport,metric,value,unit,fn in refs:
  if value is not None:
   z=fn(PerformanceReference(sport,metric,float(value),unit));out[key]=[ZoneOut(number=x.number,name=x.name,lower=x.lower,upper=x.upper,unit=x.unit.value,direction=z.direction.value,reference=x.reference_value,algorithm_version=x.algorithm_version) for x in z.zones]
 return out
def serialize(row):
 fields={k:getattr(row,k) for k in ProfileIn.model_fields if k!="effective_from"}; fields["effective_from"]=row.effective_from;return ProfileOut(**fields,id=str(row.id),algorithm_version=row.algorithm_version,created_at=row.created_at,zones=zones(row))
def athlete(session,user):return session.scalar(__import__('sqlalchemy').select(AthleteProfile).where(AthleteProfile.user_id==user.id))
@router.get("",response_model=CurrentOut)
def current(user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 a=athlete(session,user); row=PerformanceProfileRepository(session).latest(a.id) if a else None; return CurrentOut(profile=serialize(row) if row else None,derived={})
@router.get("/history",response_model=list[ProfileOut])
def history(user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 a=athlete(session,user); return [serialize(x) for x in PerformanceProfileRepository(session).history(a.id)] if a else []
@router.post("/versions",response_model=ProfileOut,status_code=201)
def create(data:ProfileIn,user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 a=athlete(session,user)
 if not a:raise HTTPException(404,"athlete_not_found")
 try: row=PerformanceProfileRepository(session).add_version(a.id,**data.model_dump(),algorithm_version=ALGORITHM_VERSION);session.commit();session.refresh(row);return serialize(row)
 except PerformanceProfileError as e:session.rollback();raise HTTPException(422,str(e))
 except Exception:session.rollback();raise