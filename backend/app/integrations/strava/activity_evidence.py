from __future__ import annotations
import asyncio,hashlib,logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime,timedelta
from uuid import UUID,uuid4
from sqlalchemy import delete,or_,select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.base import utc_now
from app.db.models import ActivityEvidenceState,ActivityLap,ActivityRouteEvidence,ActivityStream,AthleteProfile,CompletedActivity,IntegrationAccount,SyncJob
from app.integrations.strava.token_service import StravaTokenService
from app.providers.base import AuthenticationError,InvalidPayloadError,ProviderError,TemporaryProviderError
from app.providers.strava.activity_client import StravaActivityClient,StravaActivityRateLimitError,StravaActivityUnavailableError
from app.providers.strava.evidence_mapper import StravaEvidenceMapper,route_polyline
SessionFactory=Callable[[],Session];JOB_TYPE="strava_activity_evidence";ACTIVE={"queued","running","retry_scheduled"};MAX_BATCH=10;BASE_STREAMS=("time","distance","heartrate","watts","cadence","altitude","velocity_smooth");LOGGER=logging.getLogger("uvicorn.error")
DEFAULT={"activity_ids":[],"selected_count":0,"laps_imported":0,"streams_imported":0,"activities_completed":0,"skipped_count":0,"failed_count":0,"last_activity_id":None,"include_laps":True,"include_streams":True,"include_location":False}
class EvidenceConnectionRequiredError(Exception):pass
class EvidenceSelectionError(Exception):pass
class EvidenceJobNotFoundError(Exception):pass
@dataclass(frozen=True,slots=True)
class EvidenceJobView:
 job_id:UUID;status:str;selected_count:int;laps_imported:int;streams_imported:int;activities_completed:int;skipped_count:int;failed_count:int;last_activity_id:str|None;started_at:datetime|None;updated_at:datetime;completed_at:datetime|None;next_resume_at:datetime|None;error_category:str|None;location_retention_enabled:bool
class StravaActivityEvidenceManager:
 def __init__(self,*,session_factory:SessionFactory,client:StravaActivityClient,token_service:StravaTokenService,stream_retention_enabled:bool=True,location_retention_enabled:bool=False,max_samples:int=1000,retention_days:int=0,retry_seconds:int=60,clock=utc_now,mapper=None):self._s=session_factory;self._client=client;self._tokens=token_service;self._streams=stream_retention_enabled;self._location=location_retention_enabled;self._max=max_samples;self._retention_days=retention_days;self._retry=retry_seconds;self._clock=clock;self._mapper=mapper or StravaEvidenceMapper();self._tasks=set()
 def create_job(self,user_id:UUID,*,activity_ids:list[UUID]|None,include_laps:bool,include_streams:bool,include_location:bool)->EvidenceJobView:
  if not include_laps and not include_streams:raise EvidenceSelectionError
  if include_location and (not include_streams or not self._location):raise EvidenceSelectionError
  with self._s() as s:
   account=self._account(s,user_id)
   if not account:raise EvidenceConnectionRequiredError
   self._cleanup_location(s,account.athlete_id)
   self._cleanup_expired(s,account.athlete_id)
   active=s.scalar(select(SyncJob).where(SyncJob.integration_account_id==account.id,SyncJob.job_type==JOB_TYPE,SyncJob.status.in_(ACTIVE)).order_by(SyncJob.created_at.desc()))
   if active:return self._view(active)
   q=select(CompletedActivity).where(CompletedActivity.athlete_id==account.athlete_id,CompletedActivity.source_integration_account_id==account.id,CompletedActivity.enrichment_status=="succeeded",CompletedActivity.deleted_at.is_(None),CompletedActivity.provider_deleted_at.is_(None))
   if activity_ids:
    ids=list(dict.fromkeys(activity_ids))
    if len(ids)>MAX_BATCH:raise EvidenceSelectionError
    rows=list(s.scalars(q.where(CompletedActivity.id.in_(ids))).all())
    if len(rows)!=len(ids):raise EvidenceSelectionError
    order={v:i for i,v in enumerate(ids)};rows.sort(key=lambda x:order[x.id])
   else:
    q=q.outerjoin(ActivityEvidenceState).where(or_(ActivityEvidenceState.id.is_(None),ActivityEvidenceState.status=="failed",CompletedActivity.provider_updated_at>ActivityEvidenceState.source_updated_at)).order_by(CompletedActivity.start_at.desc()).limit(1);rows=list(s.scalars(q).all())
   stats={**DEFAULT,"activity_ids":[str(x.id) for x in rows],"selected_count":len(rows),"include_laps":include_laps,"include_streams":include_streams,"include_location":include_location}
   empty=not rows;job=SyncJob(athlete_id=account.athlete_id,integration_account_id=account.id,requested_by_user_id=user_id,job_type=JOB_TYPE,status="succeeded" if empty else "queued",idempotency_key=str(uuid4()),stats=stats,finished_at=self._clock() if empty else None);s.add(job);s.commit();s.refresh(job);return self._view(job)
 def schedule(self,job_id):task=asyncio.create_task(self.run(job_id));self._tasks.add(task);task.add_done_callback(self._tasks.discard)
 async def run(self,job_id):
  start=await asyncio.to_thread(self._start,job_id)
  if not start:return
  account_id,ids,options=start
  try:token=await self._tokens.access_token(account_id)
  except AuthenticationError:await asyncio.to_thread(self._fail,job_id,"authentication_reconnect_required",True);return
  for aid in ids:
   external=None
   try:
    external=await asyncio.to_thread(self._identity,job_id,aid)
    laps=await self._client.fetch_activity_laps(access_token=token,external_activity_id=external) if options[0] else None
    types=BASE_STREAMS+(("latlng",) if options[2] else ())
    streams=await self._client.fetch_activity_streams(access_token=token,external_activity_id=external,stream_types=types) if options[1] and self._streams else None
    detail=await self._client.fetch_activity_detail(access_token=token,external_activity_id=external) if options[2] else None
    mapped_laps=self._mapper.map_laps(laps.laps) if laps else ()
    mapped_streams=self._mapper.map_streams(streams.streams,types,self._max,self._location) if streams else None
    polyline=route_polyline(detail.payload) if detail else None
    await asyncio.to_thread(self._persist,job_id,aid,mapped_laps,mapped_streams,polyline,options)
   except StravaActivityRateLimitError as e:await asyncio.to_thread(self._pause,job_id,"rate_limited",e.retry_after_seconds or 900);return
   except TemporaryProviderError:await asyncio.to_thread(self._pause,job_id,"provider_temporary",self._retry);return
   except AuthenticationError:await asyncio.to_thread(self._fail,job_id,"authentication_reconnect_required",True);return
   except StravaActivityUnavailableError:await asyncio.to_thread(self._unavailable,job_id,aid);continue
   except InvalidPayloadError:await asyncio.to_thread(self._activity_failed,job_id,aid,"provider_payload");continue
   except SQLAlchemyError:await asyncio.to_thread(self._activity_failed,job_id,aid,"database_error");continue
   except ProviderError:await asyncio.to_thread(self._activity_failed,job_id,aid,"provider_error");continue
  await asyncio.to_thread(self._finish,job_id)
 def job_for_user(self,user_id,job_id):
  with self._s() as s:
   j=s.scalar(select(SyncJob).join(AthleteProfile).where(SyncJob.id==job_id,SyncJob.job_type==JOB_TYPE,AthleteProfile.user_id==user_id))
   if not j:raise EvidenceJobNotFoundError
   return self._view(j)
 def cleanup_location_for_user(self,user_id):
  with self._s() as s:
   athlete=s.scalar(select(AthleteProfile).where(AthleteProfile.user_id==user_id));count=0 if not athlete else self._cleanup_location(s,athlete.id);s.commit();return count
 def _cleanup_location(self,s,athlete_id):
  if self._location:return 0
  ids=select(CompletedActivity.id).where(CompletedActivity.athlete_id==athlete_id);a=s.execute(delete(ActivityStream).where(ActivityStream.completed_activity_id.in_(ids),ActivityStream.stream_type=="latlng")).rowcount or 0;b=s.execute(delete(ActivityRouteEvidence).where(ActivityRouteEvidence.completed_activity_id.in_(ids))).rowcount or 0;s.execute(ActivityEvidenceState.__table__.update().where(ActivityEvidenceState.completed_activity_id.in_(ids)).values(location_retained=False));return a+b
 def _cleanup_expired(self,s,athlete_id):
  if self._retention_days<=0:return 0
  cutoff=self._clock()-timedelta(days=self._retention_days);ids=select(CompletedActivity.id).where(CompletedActivity.athlete_id==athlete_id);a=s.execute(delete(ActivityStream).where(ActivityStream.completed_activity_id.in_(ids),ActivityStream.fetched_at<cutoff)).rowcount or 0;b=s.execute(delete(ActivityRouteEvidence).where(ActivityRouteEvidence.completed_activity_id.in_(ids),ActivityRouteEvidence.fetched_at<cutoff)).rowcount or 0;return a+b
 def _start(self,jid):
  with self._s() as s:
   j=s.get(SyncJob,jid)
   if not j or j.status not in {"queued","retry_scheduled"} or j.next_retry_at and j.next_retry_at>self._clock():return None
   st=self._stats(j);all_ids=[UUID(x) for x in st["activity_ids"]];last=UUID(st["last_activity_id"]) if st.get("last_activity_id") else None;done=(all_ids.index(last)+1) if last in all_ids else 0;ids=all_ids[done:];j.status="running";j.started_at=j.started_at or self._clock();j.next_retry_at=None;j.attempt_count+=1;s.commit();return j.integration_account_id,ids,(bool(st["include_laps"]),bool(st["include_streams"]),bool(st["include_location"]))
 def _identity(self,jid,aid):
  with self._s() as s:
   j=s.get(SyncJob,jid);a=s.get(CompletedActivity,aid)
   if not j or not a or a.athlete_id!=j.athlete_id or not a.external_activity_id:raise InvalidPayloadError("Invalid evidence selection")
   return a.external_activity_id
 def _persist(self,jid,aid,laps,streams,polyline,options):
  with self._s() as s:
   j=s.get(SyncJob,jid);a=s.get(CompletedActivity,aid)
   if not j or not a:raise SQLAlchemyError("Missing evidence record")
   now=self._clock();st=self._stats(j)
   if options[0]:
    s.execute(delete(ActivityLap).where(ActivityLap.completed_activity_id==aid))
    for lap in laps:s.add(ActivityLap(completed_activity_id=aid,**lap.fields()))
    st["laps_imported"]=int(st["laps_imported"])+len(laps)
   invalid=()
   if options[1] and streams:
    invalid=streams.invalid_streams
    for item in streams.streams:
     row=s.scalar(select(ActivityStream).where(ActivityStream.completed_activity_id==aid,ActivityStream.stream_type==item.stream_type));fields={name:getattr(item,name) for name in item.__dataclass_fields__};fields.update(fetched_at=now,source_updated_at=a.provider_updated_at)
     if row is None:s.add(ActivityStream(completed_activity_id=aid,**fields))
     else:
      for k,v in fields.items():setattr(row,k,v)
    st["streams_imported"]=int(st["streams_imported"])+len(streams.streams)
   if options[2]:
    lat=next((x for x in (streams.streams if streams else ()) if x.stream_type=="latlng"),None);route=s.scalar(select(ActivityRouteEvidence).where(ActivityRouteEvidence.completed_activity_id==aid));fields=dict(available=bool(polyline or lat),summary_polyline=polyline,sample_count=lat.sample_count if lat else 0,fetched_at=now,source_updated_at=a.provider_updated_at,retention_class="location",checksum=hashlib.sha256(polyline.encode()).hexdigest() if polyline else None,version=1)
    if route is None:s.add(ActivityRouteEvidence(completed_activity_id=aid,**fields))
    else:
     for k,v in fields.items():setattr(route,k,v)
   state=s.scalar(select(ActivityEvidenceState).where(ActivityEvidenceState.completed_activity_id==aid)) or ActivityEvidenceState(completed_activity_id=aid);s.add(state);state.laps_fetched_at=now if options[0] else state.laps_fetched_at;state.streams_fetched_at=now if options[1] and streams is not None else state.streams_fetched_at;state.source_updated_at=a.provider_updated_at;state.status="partial" if invalid else "succeeded";state.error_category="invalid_stream" if invalid else None;state.location_retained=bool(options[2] and self._location)
   st["activities_completed"]=int(st["activities_completed"])+1;st["last_activity_id"]=str(aid)
   if invalid:st["failed_count"]=int(st["failed_count"])+1;j.error_code=j.error_code or "invalid_stream"
   j.stats=st;s.commit()
 def _activity_failed(self,jid,aid,cat):
  with self._s() as s:
   j=s.get(SyncJob,jid)
   if not j:return
   state=s.scalar(select(ActivityEvidenceState).where(ActivityEvidenceState.completed_activity_id==aid)) or ActivityEvidenceState(completed_activity_id=aid);s.add(state);state.status="failed";state.error_category=cat;st=self._stats(j);st["failed_count"]=int(st["failed_count"])+1;st["last_activity_id"]=str(aid);j.stats=st;j.error_code=j.error_code or cat;s.commit()
 def _unavailable(self,jid,aid):
  with self._s() as s:
   a=s.get(CompletedActivity,aid)
   if a:a.provider_deleted_at=self._clock();s.commit()
  self._activity_failed(jid,aid,"provider_unavailable")
 def _pause(self,jid,cat,seconds):
  with self._s() as s:j=s.get(SyncJob,jid);j.status="retry_scheduled";j.error_code=cat;j.next_retry_at=self._clock()+timedelta(seconds=seconds);s.commit()
 def _fail(self,jid,cat,reconnect=False):
  with self._s() as s:
   j=s.get(SyncJob,jid);j.status="failed";j.error_code=cat;j.finished_at=self._clock()
   if reconnect:s.get(IntegrationAccount,j.integration_account_id).status="refresh_required"
   s.commit()
 def _finish(self,jid):
  with self._s() as s:j=s.get(SyncJob,jid);st=self._stats(j);j.status="partially_succeeded" if int(st["failed_count"]) else "succeeded";j.finished_at=self._clock();j.error_code=j.error_code if int(st["failed_count"]) else None;s.commit()
 @staticmethod
 def _account(s,user):return s.scalar(select(IntegrationAccount).join(AthleteProfile).where(AthleteProfile.user_id==user,IntegrationAccount.provider=="strava",IntegrationAccount.status=="active",IntegrationAccount.deleted_at.is_(None)))
 @staticmethod
 def _stats(j):return {**DEFAULT,**(j.stats or {})}
 def _view(self,j):
  s=self._stats(j);return EvidenceJobView(j.id,j.status,int(s["selected_count"]),int(s["laps_imported"]),int(s["streams_imported"]),int(s["activities_completed"]),int(s["skipped_count"]),int(s["failed_count"]),s["last_activity_id"],j.started_at,j.updated_at,j.finished_at,j.next_retry_at,j.error_code,self._location)




