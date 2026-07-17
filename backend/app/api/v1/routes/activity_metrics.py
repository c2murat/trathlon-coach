from datetime import datetime,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel
from sqlalchemy import delete,select
from sqlalchemy.orm import Session,selectinload
from app.api.dependencies.auth import AuthenticatedUser,get_current_user
from app.db.session import get_db_session
from app.db.models import ActivityMetric,AthleteProfile,CompletedActivity
from app.application.metrics import ALGORITHM_VERSION,calculate
router=APIRouter(prefix="/activities",tags=["activity-metrics"])
class MetricOut(BaseModel):
 key:str;label:str;status:str;value:float|None;unit:str|None;source:str|None;sample_count:int|None;coverage_ratio:float|None;quality_notes:list[str];unavailable_reason:str|None
class MetricsOut(BaseModel):
 activity_id:UUID;algorithm_version:str;calculated_at:datetime|None;metrics:list[MetricOut];coverage_summary:dict[str,int];warnings:list[str]
def own(session,user,activity_id):return session.scalar(select(CompletedActivity).join(AthleteProfile).options(selectinload(CompletedActivity.streams),selectinload(CompletedActivity.laps)).where(CompletedActivity.id==activity_id,AthleteProfile.user_id==user.id,CompletedActivity.deleted_at.is_(None)))
def label(k):return {"moving_time":"Tiempo en movimiento","elapsed_time":"Tiempo total","distance":"Distancia","elevation_gain":"Desnivel","average_speed":"Velocidad media","max_speed":"Velocidad máxima","average_heart_rate":"Frecuencia cardiaca media","max_heart_rate":"Frecuencia cardiaca máxima","average_power":"Potencia media","max_power":"Potencia máxima","average_cadence":"Cadencia media","lap_count":"Vueltas","stream_sample_count":"Muestras de streams"}.get(k,k)
def response(activity,rows):
 metrics=[MetricOut(key=x.metric_key,label=label(x.metric_key),status=x.status,value=x.value,unit=x.unit,source=x.source,sample_count=x.sample_count,coverage_ratio=x.coverage_ratio,quality_notes=x.quality_notes or [],unavailable_reason=x.unavailable_reason) for x in rows]; counts={s:sum(x.status==s for x in metrics) for s in ("available","partial","unavailable","not_applicable")}; return MetricsOut(activity_id=activity.id,algorithm_version=ALGORITHM_VERSION,calculated_at=max((x.calculated_at for x in rows),default=None),metrics=metrics,coverage_summary=counts,warnings=[])
@router.get("/{activity_id}/metrics",response_model=MetricsOut)
def get_metrics(activity_id:UUID,current_user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 a=own(session,current_user,activity_id)
 if not a:raise HTTPException(404,detail={"code":"activity_not_found"})
 rows=session.scalars(select(ActivityMetric).where(ActivityMetric.completed_activity_id==a.id,ActivityMetric.algorithm_version==ALGORITHM_VERSION)).all();return response(a,rows)
@router.post("/{activity_id}/metrics/recalculate",response_model=MetricsOut)
def recalculate(activity_id:UUID,current_user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 a=own(session,current_user,activity_id)
 if not a:raise HTTPException(404,detail={"code":"activity_not_found"})
 session.execute(delete(ActivityMetric).where(ActivityMetric.completed_activity_id==a.id,ActivityMetric.algorithm_version==ALGORITHM_VERSION)); now=datetime.now(timezone.utc); rows=[ActivityMetric(completed_activity_id=a.id,metric_key=x.key,algorithm_version=ALGORITHM_VERSION,status=x.status,value=x.value,unit=x.unit,source=x.source,sample_count=x.sample_count,coverage_ratio=x.coverage_ratio,quality_notes=x.quality_notes,unavailable_reason=x.unavailable_reason,calculated_at=now) for x in calculate(a,a.streams)];session.add_all(rows);session.commit();return response(a,rows)