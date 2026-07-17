from __future__ import annotations
import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.db.base import utc_now
from app.db.models import AthleteProfile, CompletedActivity, IntegrationAccount, SyncJob
from app.integrations.strava.token_service import StravaTokenService
from app.providers.base import AuthenticationError, InvalidPayloadError, ProviderError, TemporaryProviderError
from app.providers.strava.activity_client import StravaActivityClient, StravaActivityRateLimitError, StravaActivityUnavailableError
from app.providers.strava.activity_mapper import StravaActivityMapper, StravaActivityOwnershipError

SessionFactory=Callable[[],Session]
JOB_TYPE="strava_activity_detail"
DEFAULT_LIMIT=10
MAX_LIMIT=50
ACTIVE={"queued","running","retry_scheduled"}
LOGGER = logging.getLogger("uvicorn.error")
DEFAULT_STATS={"activity_ids":[],"selected_count":0,"enriched_count":0,"updated_count":0,"skipped_count":0,"failed_count":0,"last_activity_id":None}
class EnrichmentConnectionRequiredError(Exception):pass
class EnrichmentJobNotFoundError(Exception):pass
class EnrichmentSelectionError(Exception):pass
@dataclass(frozen=True,slots=True)
class StravaEnrichmentJobView:
 job_id:UUID;status:str;selected_count:int;enriched_count:int;updated_count:int;skipped_count:int;failed_count:int;last_activity_id:str|None;started_at:datetime|None;updated_at:datetime;completed_at:datetime|None;next_resume_at:datetime|None;error_category:str|None

class StravaActivityEnrichmentManager:
 def __init__(self,*,session_factory:SessionFactory,activity_client:StravaActivityClient,token_service:StravaTokenService,retry_seconds:int=60,clock=utc_now,mapper:StravaActivityMapper|None=None):
  self._sessions=session_factory;self._client=activity_client;self._tokens=token_service;self._retry=retry_seconds;self._clock=clock;self._mapper=mapper or StravaActivityMapper();self._tasks:set[asyncio.Task[None]]=set()
 def create_job(self,user_id:UUID,*,activity_ids:list[UUID]|None=None,limit:int|None=None)->StravaEnrichmentJobView:
  batch=DEFAULT_LIMIT if limit is None else limit
  if batch<1 or batch>MAX_LIMIT:raise EnrichmentSelectionError
  with self._sessions() as s:
   account=self._account(s,user_id)
   if not account:raise EnrichmentConnectionRequiredError
   active=s.scalar(select(SyncJob).where(SyncJob.integration_account_id==account.id,SyncJob.job_type==JOB_TYPE,SyncJob.status.in_(ACTIVE)).order_by(SyncJob.created_at.desc()))
   if active:return self._view(active)
   q=select(CompletedActivity).where(CompletedActivity.athlete_id==account.athlete_id,CompletedActivity.source_integration_account_id==account.id,CompletedActivity.deleted_at.is_(None),CompletedActivity.provider_deleted_at.is_(None),CompletedActivity.external_activity_id.is_not(None))
   if activity_ids:
    unique=list(dict.fromkeys(activity_ids));q=q.where(CompletedActivity.id.in_(unique));rows=list(s.scalars(q).all())
    if len(rows)!=len(unique):raise EnrichmentSelectionError
    order={x:i for i,x in enumerate(unique)};rows.sort(key=lambda x:order[x.id]);rows=rows[:batch]
   else:
    q=q.where(or_(CompletedActivity.enriched_at.is_(None),CompletedActivity.enrichment_status=="failed",CompletedActivity.provider_updated_at>CompletedActivity.enriched_at)).order_by(CompletedActivity.start_at.desc()).limit(batch);rows=list(s.scalars(q).all())
   stats={**DEFAULT_STATS,"activity_ids":[str(a.id) for a in rows],"selected_count":len(rows)}
   job=SyncJob(athlete_id=account.athlete_id,integration_account_id=account.id,requested_by_user_id=user_id,job_type=JOB_TYPE,status="queued",idempotency_key=str(uuid4()),stats=stats)
   s.add(job);s.commit();s.refresh(job);return self._view(job)
 def schedule(self,job_id:UUID)->None:
  task=asyncio.create_task(self.run(job_id));self._tasks.add(task);task.add_done_callback(self._tasks.discard)
 async def run(self,job_id:UUID)->None:
  start=await asyncio.to_thread(self._start,job_id)
  if not start:return
  account_id,ids=start
  try:token=await self._tokens.access_token(account_id)
  except AuthenticationError:await asyncio.to_thread(self._fail,job_id,"authentication_reconnect_required",True);return
  for activity_id in ids:
   external_id=None;stage="lifecycle"
   try:
    external_id,owner=await asyncio.to_thread(self._activity_identity,job_id,activity_id)
    stage="client";detail=await self._client.fetch_activity_detail(access_token=token,external_activity_id=external_id)
    stage="mapping";mapped=self._mapper.map_detail(detail.payload,expected_external_activity_id=external_id,external_account_id=owner)
    stage="persistence";await asyncio.to_thread(self._persist,job_id,activity_id,mapped.provider_fields())
    if self._rate_exhausted(detail.rate_limit):await asyncio.to_thread(self._pause,job_id,"rate_limited",900);return
   except StravaActivityRateLimitError as e:self._diagnostic(job_id,activity_id,external_id,stage,e,"rate_limited",429);await asyncio.to_thread(self._pause,job_id,"rate_limited",e.retry_after_seconds or 900);return
   except TemporaryProviderError as e:self._diagnostic(job_id,activity_id,external_id,stage,e,"provider_temporary");await asyncio.to_thread(self._pause,job_id,"provider_temporary",self._retry);return
   except AuthenticationError as e:self._diagnostic(job_id,activity_id,external_id,stage,e,"authentication_reconnect_required",401);await asyncio.to_thread(self._fail,job_id,"authentication_reconnect_required",True);return
   except StravaActivityUnavailableError as e:self._diagnostic(job_id,activity_id,external_id,stage,e,"provider_unavailable",getattr(e,"status_code",None));await asyncio.to_thread(self._unavailable,job_id,activity_id);continue
   except (InvalidPayloadError,StravaActivityOwnershipError) as e:self._diagnostic(job_id,activity_id,external_id,stage,e,"provider_payload");await asyncio.to_thread(self._activity_failed,job_id,activity_id,"provider_payload");continue
   except SQLAlchemyError as e:self._diagnostic(job_id,activity_id,external_id,stage,e,"database_error");await asyncio.to_thread(self._activity_failed,job_id,activity_id,"database_error");continue
   except ProviderError as e:self._diagnostic(job_id,activity_id,external_id,stage,e,"provider_error",getattr(e,"status_code",None));await asyncio.to_thread(self._activity_failed,job_id,activity_id,"provider_error");continue
  await asyncio.to_thread(self._finish,job_id)
 def job_for_user(self,user_id:UUID,job_id:UUID)->StravaEnrichmentJobView:
  with self._sessions() as s:
   job=s.scalar(select(SyncJob).join(AthleteProfile,SyncJob.athlete_id==AthleteProfile.id).where(SyncJob.id==job_id,SyncJob.job_type==JOB_TYPE,AthleteProfile.user_id==user_id))
   if not job:raise EnrichmentJobNotFoundError
   return self._view(job)
 def _start(self,job_id):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id)
   if not j or j.status not in {"queued","retry_scheduled"} or (j.next_retry_at and j.next_retry_at>self._clock()):return None
   st=self._stats(j);done=int(st["enriched_count"])+int(st["failed_count"]);ids=[UUID(x) for x in st["activity_ids"]][done:];j.status="running";j.started_at=j.started_at or self._clock();j.next_retry_at=None;j.attempt_count+=1;s.commit();return j.integration_account_id,ids
 def _activity_identity(self,job_id,activity_id):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id);a=s.get(CompletedActivity,activity_id);account=s.get(IntegrationAccount,j.integration_account_id) if j else None
   if not j or not a or not account or a.athlete_id!=j.athlete_id or a.source_integration_account_id!=account.id or not a.external_activity_id:raise InvalidPayloadError("Activity selection invalid")
   return a.external_activity_id,account.external_account_id
 def _persist(self,job_id,activity_id,fields):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id);a=s.get(CompletedActivity,activity_id)
   if not j or not a:raise SQLAlchemyError("Missing enrichment record")
   changed=any(getattr(a,k)!=v for k,v in fields.items())
   for k,v in fields.items():setattr(a,k,v)
   a.enriched_at=self._clock();a.enrichment_status="succeeded";a.enrichment_error_category=None
   st=self._stats(j);st["enriched_count"]=int(st["enriched_count"])+1;st["updated_count" if changed else "skipped_count"]=int(st["updated_count" if changed else "skipped_count"])+1;st["last_activity_id"]=str(a.id);j.stats=st;s.commit()
 def _activity_failed(self,job_id,activity_id,category):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id);a=s.get(CompletedActivity,activity_id)
   if not j:return
   if a:a.enrichment_status="failed";a.enrichment_error_category=category
   j.error_code=j.error_code or category
   st=self._stats(j);st["failed_count"]=int(st["failed_count"])+1;st["last_activity_id"]=str(activity_id);j.stats=st;s.commit()
 def _unavailable(self,job_id,activity_id):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id);a=s.get(CompletedActivity,activity_id)
   if not j:return
   if a:a.provider_deleted_at=self._clock();a.enrichment_status="unavailable";a.enrichment_error_category="provider_unavailable"
   j.error_code=j.error_code or "provider_unavailable"
   st=self._stats(j);st["failed_count"]=int(st["failed_count"])+1;st["last_activity_id"]=str(activity_id);j.stats=st;s.commit()
 def _pause(self,job_id,category,seconds):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id)
   if j:j.status="retry_scheduled";j.error_code=category;j.next_retry_at=self._clock()+timedelta(seconds=seconds);s.commit()
 def _fail(self,job_id,category,reconnect=False):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id)
   if not j:return
   j.status="failed";j.finished_at=self._clock();j.error_code=category
   if reconnect:
    account=s.get(IntegrationAccount,j.integration_account_id)
    if account:account.status="refresh_required"
   s.commit()
 def _finish(self,job_id):
  with self._sessions() as s:
   j=s.get(SyncJob,job_id)
   if not j:return
   st=self._stats(j);failed=int(st["failed_count"]);j.status="partially_succeeded" if failed else "succeeded";j.finished_at=self._clock();j.error_code=(j.error_code or "activity_failed") if failed else None;s.commit()
 @staticmethod
 def _diagnostic(job_id,activity_id,external_id,stage,exc,category,status_code=None):
  LOGGER.warning("strava_enrichment_failure job_id=%s activity_id=%s external_activity_id=%s stage=%s exception_class=%s provider_status_code=%s error_category=%s",job_id,activity_id,external_id,stage,type(exc).__name__,status_code,category)
 @staticmethod
 def _account(s,user_id):return s.scalar(select(IntegrationAccount).join(AthleteProfile).where(AthleteProfile.user_id==user_id,IntegrationAccount.provider=="strava",IntegrationAccount.status=="active",IntegrationAccount.deleted_at.is_(None)))
 @staticmethod
 def _stats(j):return {**DEFAULT_STATS,**(j.stats or {})}
 @staticmethod
 def _rate_exhausted(x):return any(limit and usage and (usage[0]>=limit[0] or usage[1]>=limit[1]) for limit,usage in ((x.general_limit,x.general_usage),(x.read_limit,x.read_usage)))
 @classmethod
 def _view(cls,j):
  s=cls._stats(j);return StravaEnrichmentJobView(j.id,j.status,int(s["selected_count"]),int(s["enriched_count"]),int(s["updated_count"]),int(s["skipped_count"]),int(s["failed_count"]),s["last_activity_id"],j.started_at,j.updated_at,j.finished_at,j.next_retry_at,j.error_code)

