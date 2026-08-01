from dataclasses import dataclass
from datetime import date,datetime
from decimal import Decimal
from enum import Enum
from math import isfinite
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
class AggregateCoverage(str,Enum): COMPLETE="complete"; PARTIAL="partial"; UNAVAILABLE="unavailable"
class AggregateQuality(str,Enum): HIGH="high"; MEDIUM="medium"; LOW="low"; UNAVAILABLE="unavailable"
class TrainingLoadAggregationError(ValueError): pass
class InvalidAggregationInputError(TrainingLoadAggregationError): pass
class MixedAlgorithmVersionError(TrainingLoadAggregationError): pass
class DuplicateActivityEntryError(TrainingLoadAggregationError): pass
class InvalidTimezoneError(TrainingLoadAggregationError): pass
@dataclass(frozen=True,slots=True)
class ActivityLoadEntry:
 activity_id:object;activity_start_at:datetime;load_value:Decimal|float|None;algorithm_version:str;coverage:str|None=None;quality:str|None=None;duration_seconds:float|None=None;method:str|None=None;sport:str|None=None;reason:str|None=None
 def __post_init__(self):
  if self.activity_id is None or str(self.activity_id)=="":raise InvalidAggregationInputError("activity_id inválido")
  if self.activity_start_at.tzinfo is None or self.activity_start_at.utcoffset() is None:raise InvalidAggregationInputError("datetime debe incluir zona horaria")
  if not isinstance(self.algorithm_version,str) or not self.algorithm_version.strip():raise InvalidAggregationInputError("algorithm_version obligatorio")
  for n in ("load_value","duration_seconds"):
   v=getattr(self,n)
   if v is not None and (isinstance(v,bool) or not isfinite(float(v)) or v<0):raise InvalidAggregationInputError(f"{n} inválido")
@dataclass(frozen=True,slots=True)
class DailyTrainingLoadAggregate:
 local_date:date;timezone:str;source_load_algorithm_version:str;aggregation_algorithm_version:str;total_load:Decimal;activity_count:int;loaded_activity_count:int;null_load_activity_count:int;total_duration_seconds:Decimal;coverage:AggregateCoverage;quality:AggregateQuality;activity_ids:tuple=();warnings:tuple=()
 def __post_init__(self):
  if self.total_load<0 or min(self.activity_count,self.loaded_activity_count,self.null_load_activity_count)<0 or self.loaded_activity_count+self.null_load_activity_count!=self.activity_count:raise InvalidAggregationInputError("conteos diarios inválidos")
@dataclass(frozen=True,slots=True)
class WeeklyTrainingLoadAggregate:
 iso_year:int;iso_week:int;week_start_date:date;week_end_date:date;timezone:str;source_load_algorithm_version:str;aggregation_algorithm_version:str;total_load:Decimal;activity_count:int;loaded_activity_count:int;null_load_activity_count:int;total_duration_seconds:Decimal;coverage:AggregateCoverage;quality:AggregateQuality;daily_aggregates:tuple=();activity_ids:tuple=();warnings:tuple=()
 def __post_init__(self):
  if self.week_start_date.weekday()!=0 or self.week_end_date-self.week_start_date != __import__('datetime').timedelta(days=6) or self.week_start_date.isocalendar()[:2]!=(self.iso_year,self.iso_week):raise InvalidAggregationInputError("semana ISO inválida")
  if self.total_load<0 or self.loaded_activity_count+self.null_load_activity_count!=self.activity_count:raise InvalidAggregationInputError("conteos semanales inválidos")
