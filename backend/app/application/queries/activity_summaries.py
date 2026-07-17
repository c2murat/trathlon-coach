from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.base import utc_now
from app.db.models import AthleteProfile, CompletedActivity

@dataclass(frozen=True,slots=True)
class ActivitySummaryView:
 id:UUID; external_activity_id:str|None; name:str; sport_type:str; start_time:datetime; athlete_timezone:str; distance_metres:float|None; moving_time_seconds:int|None; elapsed_time_seconds:int; elevation_metres:float|None; average_heart_rate:float|None; average_watts:float|None; trainer:bool|None; manual:bool|None; visibility:str|None
@dataclass(frozen=True,slots=True)
class ActivitySummaryPage:
 total:int;limit:int;offset:int;items:tuple[ActivitySummaryView,...]
@dataclass(frozen=True,slots=True)
class ActivityFilterOptions:
 sport_types:tuple[str,...];visibility_values:tuple[str,...];minimum_activity_date:date|None;maximum_activity_date:date|None

class ActivitySummaryQuery:
 def __init__(self,session:Session):self._session=session
 @staticmethod
 def _base(user_id:UUID):return (CompletedActivity.athlete_id==AthleteProfile.id,AthleteProfile.user_id==user_id,AthleteProfile.deleted_at.is_(None),CompletedActivity.deleted_at.is_(None),CompletedActivity.provider_deleted_at.is_(None),CompletedActivity.start_at<=utc_now())
 def for_user(self,user_id:UUID,*,limit:int,offset:int,sport:str|None=None,date_from:date|None=None,date_to:date|None=None,min_distance_metres:float|None=None,max_distance_metres:float|None=None,trainer:bool|None=None,manual:bool|None=None,visibility:str|None=None,search:str|None=None)->ActivitySummaryPage:
  filters=list(self._base(user_id))
  if sport:filters.append(CompletedActivity.sport==sport)
  if date_from:filters.append(CompletedActivity.start_at>=datetime.combine(date_from,time.min,tzinfo=timezone.utc))
  if date_to:filters.append(CompletedActivity.start_at<datetime.combine(date_to,time.max,tzinfo=timezone.utc))
  if min_distance_metres is not None:filters.append(CompletedActivity.distance_m>=min_distance_metres)
  if max_distance_metres is not None:filters.append(CompletedActivity.distance_m<=max_distance_metres)
  if trainer is not None:filters.append(CompletedActivity.indoor==trainer)
  if manual is not None:filters.append(CompletedActivity.manual==manual)
  if visibility:filters.append(CompletedActivity.visibility==visibility)
  if search:filters.append(func.lower(CompletedActivity.name).contains(search.strip().lower()))
  total=self._session.scalar(select(func.count(CompletedActivity.id)).select_from(CompletedActivity).join(AthleteProfile).where(*filters))
  rows=self._session.scalars(select(CompletedActivity).join(AthleteProfile).where(*filters).order_by(CompletedActivity.start_at.desc(),CompletedActivity.id.desc()).limit(limit).offset(offset)).all()
  return ActivitySummaryPage(int(total or 0),limit,offset,tuple(self._view(x) for x in rows))
 def detail(self,user_id:UUID,activity_id:UUID)->CompletedActivity|None:return self._session.scalar(select(CompletedActivity).join(AthleteProfile).where(*self._base(user_id),CompletedActivity.id==activity_id))
 def filter_options(self,user_id:UUID)->ActivityFilterOptions:
  base=self._base(user_id);rows=self._session.execute(select(CompletedActivity.sport,CompletedActivity.visibility,CompletedActivity.start_at).join(AthleteProfile).where(*base)).all()
  sports=tuple(sorted({x.sport for x in rows}));vis=tuple(sorted({x.visibility for x in rows if x.visibility}));dates=[x.start_at.date() for x in rows]
  return ActivityFilterOptions(sports,vis,min(dates,default=None),max(dates,default=None))
 @staticmethod
 def _view(a:CompletedActivity)->ActivitySummaryView:return ActivitySummaryView(a.id,a.external_activity_id,a.name,a.sport,a.start_at,a.timezone,a.distance_m,a.moving_time_s,a.elapsed_time_s,a.elevation_gain_m,a.average_heart_rate_bpm,a.average_power_w,a.indoor,a.manual,a.visibility)
