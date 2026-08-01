from datetime import date, datetime, time, timedelta, timezone
from dataclasses import dataclass
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import delete, select
from app.db.models.activity import CompletedActivity
from app.db.models.training_load import ActivityTrainingLoad
from app.db.models.training_load_aggregate import AthleteDailyTrainingLoad, AthleteWeeklyTrainingLoad
from app.domains.training_load_aggregation import ActivityLoadEntry, aggregate_daily_training_load, aggregate_weekly_training_load
from app.domains.training_load_aggregation.models import InvalidAggregationInputError
AGGREGATION_ALGORITHM_VERSION='0.7c.1'
@dataclass(frozen=True)
class TrainingLoadAggregationRecalculationResult:
 daily: tuple; weekly: tuple
class TrainingLoadAggregationApplicationError(ValueError): pass
class InvalidAggregationRangeError(TrainingLoadAggregationApplicationError): pass
class TrainingLoadAggregationApplication:
 def __init__(self,session,clock=None): self.session=session; self.clock=clock or (lambda:datetime.now(timezone.utc))
 def _bounds(self,start,end,tz,weekly=False):
  if start>end: raise InvalidAggregationRangeError('start_date must be <= end_date')
  if weekly: start=start-timedelta(days=start.weekday()); end=end+timedelta(days=6-end.weekday())
  z=ZoneInfo(tz); a=datetime.combine(start,time.min,tzinfo=z); b=datetime.combine(end+timedelta(days=1),time.min,tzinfo=z); return start,end,a.astimezone(timezone.utc),b.astimezone(timezone.utc)
 def _entries(self,athlete,start,end,tz,version):
  _,_,a,b=self._bounds(start,end,tz)
  rows=self.session.execute(select(ActivityTrainingLoad,CompletedActivity).join(CompletedActivity,CompletedActivity.id==ActivityTrainingLoad.completed_activity_id).where(CompletedActivity.athlete_id==athlete,ActivityTrainingLoad.algorithm_version==version,CompletedActivity.start_at>=a,CompletedActivity.start_at<b).order_by(CompletedActivity.start_at,CompletedActivity.id)).all()
  return tuple(ActivityLoadEntry(activity_id=str(load.completed_activity_id),activity_start_at=activity.start_at,load_value=load.load_value,algorithm_version=load.algorithm_version,coverage=load.coverage,quality=load.quality,duration_seconds=load.duration_seconds) for load,activity in rows)
 def _sync_daily(self,athlete,results,tz,version,start,end):
  keys={(x.local_date,x.timezone,x.source_load_algorithm_version,x.aggregation_algorithm_version) for x in results}; rows=self.session.scalars(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id==athlete,AthleteDailyTrainingLoad.timezone_name==tz,AthleteDailyTrainingLoad.source_load_algorithm_version==version,AthleteDailyTrainingLoad.aggregation_algorithm_version==AGGREGATION_ALGORITHM_VERSION,AthleteDailyTrainingLoad.local_date>=start,AthleteDailyTrainingLoad.local_date<=end)).all()
  for row in rows:
   if (row.local_date,row.timezone_name,row.source_load_algorithm_version,row.aggregation_algorithm_version) not in keys:self.session.delete(row)
  now=self.clock()
  for x in results:
   row=self.session.scalar(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id==athlete,AthleteDailyTrainingLoad.local_date==x.local_date,AthleteDailyTrainingLoad.timezone_name==tz,AthleteDailyTrainingLoad.source_load_algorithm_version==version,AthleteDailyTrainingLoad.aggregation_algorithm_version==AGGREGATION_ALGORITHM_VERSION))
   vals=dict(total_load=x.total_load,activity_count=x.activity_count,loaded_activity_count=x.loaded_activity_count,null_load_activity_count=x.null_load_activity_count,total_duration_seconds=x.total_duration_seconds,coverage=x.coverage.value,quality=x.quality.value,warnings=list(x.warnings),activity_ids=list(x.activity_ids),calculated_at=now)
   if row:
    for k,v in vals.items():setattr(row,k,v)
   else:self.session.add(AthleteDailyTrainingLoad(athlete_profile_id=athlete,local_date=x.local_date,timezone_name=tz,source_load_algorithm_version=version,aggregation_algorithm_version=AGGREGATION_ALGORITHM_VERSION,**vals))
 def recalculate_daily(self,athlete_profile_id,*,start_date,end_date,timezone_name,source_load_algorithm_version='0.7b.1'):
  start,end,_,_=self._bounds(start_date,end_date,timezone_name); result=aggregate_daily_training_load(self._entries(athlete_profile_id,start,end,timezone_name,source_load_algorithm_version),timezone_name=timezone_name,source_algorithm_version=source_load_algorithm_version); self._sync_daily(athlete_profile_id,result,timezone_name,source_load_algorithm_version,start,end); self.session.flush(); return result
 def recalculate_weekly(self,athlete_profile_id,*,start_date,end_date,timezone_name,source_load_algorithm_version='0.7b.1'):
  start,end,_,_=self._bounds(start_date,end_date,timezone_name,True); result=aggregate_weekly_training_load(self._entries(athlete_profile_id,start,end,timezone_name,source_load_algorithm_version),timezone_name=timezone_name,source_algorithm_version=source_load_algorithm_version); self._sync_weekly(athlete_profile_id,result,timezone_name,source_load_algorithm_version,start,end); self.session.flush(); return result
 def _sync_weekly(self,athlete,results,tz,version,start,end):
  keys={(x.iso_year,x.iso_week,tz,version,AGGREGATION_ALGORITHM_VERSION) for x in results}; rows=self.session.scalars(select(AthleteWeeklyTrainingLoad).where(AthleteWeeklyTrainingLoad.athlete_profile_id==athlete,AthleteWeeklyTrainingLoad.timezone_name==tz,AthleteWeeklyTrainingLoad.source_load_algorithm_version==version,AthleteWeeklyTrainingLoad.aggregation_algorithm_version==AGGREGATION_ALGORITHM_VERSION,AthleteWeeklyTrainingLoad.week_start_date>=start,AthleteWeeklyTrainingLoad.week_start_date<=end)).all()
  for row in rows:
   if (row.iso_year,row.iso_week,row.timezone_name,row.source_load_algorithm_version,row.aggregation_algorithm_version) not in keys:self.session.delete(row)
  now=self.clock()
  for x in results:
   row=self.session.scalar(select(AthleteWeeklyTrainingLoad).where(AthleteWeeklyTrainingLoad.athlete_profile_id==athlete,AthleteWeeklyTrainingLoad.iso_year==x.iso_year,AthleteWeeklyTrainingLoad.iso_week==x.iso_week,AthleteWeeklyTrainingLoad.timezone_name==tz,AthleteWeeklyTrainingLoad.source_load_algorithm_version==version,AthleteWeeklyTrainingLoad.aggregation_algorithm_version==AGGREGATION_ALGORITHM_VERSION))
   vals=dict(week_end_date=x.week_end_date,total_load=x.total_load,activity_count=x.activity_count,loaded_activity_count=x.loaded_activity_count,null_load_activity_count=x.null_load_activity_count,total_duration_seconds=x.total_duration_seconds,coverage=x.coverage.value,quality=x.quality.value,warnings=list(x.warnings),activity_ids=list(x.activity_ids),calculated_at=now)
   if row:
    for k,v in vals.items():setattr(row,k,v)
   else:self.session.add(AthleteWeeklyTrainingLoad(athlete_profile_id=athlete,iso_year=x.iso_year,iso_week=x.iso_week,week_start_date=x.week_start_date,timezone_name=tz,source_load_algorithm_version=version,aggregation_algorithm_version=AGGREGATION_ALGORITHM_VERSION,**vals))
 def recalculate_all(self,athlete_profile_id,**kwargs):
  d=self.recalculate_daily(athlete_profile_id,**kwargs); w=self.recalculate_weekly(athlete_profile_id,**kwargs); return TrainingLoadAggregationRecalculationResult(d,w)
 def get_daily_aggregates(self,athlete_profile_id,*,start_date,end_date,timezone_name,source_load_algorithm_version='0.7b.1'):
  return tuple(self.session.scalars(select(AthleteDailyTrainingLoad).where(AthleteDailyTrainingLoad.athlete_profile_id==athlete_profile_id,AthleteDailyTrainingLoad.local_date.between(start_date,end_date),AthleteDailyTrainingLoad.timezone_name==timezone_name,AthleteDailyTrainingLoad.source_load_algorithm_version==source_load_algorithm_version,AthleteDailyTrainingLoad.aggregation_algorithm_version==AGGREGATION_ALGORITHM_VERSION).order_by(AthleteDailyTrainingLoad.local_date)).all())
 def get_weekly_aggregates(self,athlete_profile_id,*,start_date,end_date,timezone_name,source_load_algorithm_version='0.7b.1'):
  return tuple(self.session.scalars(select(AthleteWeeklyTrainingLoad).where(AthleteWeeklyTrainingLoad.athlete_profile_id==athlete_profile_id,AthleteWeeklyTrainingLoad.week_start_date.between(start_date,end_date),AthleteWeeklyTrainingLoad.timezone_name==timezone_name,AthleteWeeklyTrainingLoad.source_load_algorithm_version==source_load_algorithm_version,AthleteWeeklyTrainingLoad.aggregation_algorithm_version==AGGREGATION_ALGORITHM_VERSION).order_by(AthleteWeeklyTrainingLoad.week_start_date)).all())
