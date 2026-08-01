from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any
class Sport(str,Enum): SWIMMING="swimming"; CYCLING="cycling"; RUNNING="running"; OTHER="other"
class TrainingLoadMethod(str,Enum): CYCLING_POWER="cycling_power"; HEART_RATE="heart_rate"; RUNNING_PACE="running_pace"; SWIMMING_CSS="swimming_css"; DURATION_ONLY="duration_only"
class TrainingLoadUnit(str,Enum): LOAD_POINTS="load_points"
class TrainingLoadCoverage(str,Enum): COMPLETE="complete"; PARTIAL="partial"; UNAVAILABLE="unavailable"; NOT_APPLICABLE="not_applicable"
class TrainingLoadQuality(str,Enum): HIGH="high"; MEDIUM="medium"; LOW="low"; NONE="none"
class TrainingLoadReason(str,Enum): CALCULATED="calculated"; MISSING_DURATION="missing_duration"; MISSING_REFERENCE="missing_reference"; MISSING_STREAM="missing_stream"; INVALID_VALUE="invalid_value"; UNSUPPORTED_SPORT="unsupported_sport"; INSUFFICIENT_DATA="insufficient_data"

def _check(v,name,positive=False):
 if v is None:return
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or (positive and v<=0) or (not positive and v<0):raise ValueError(f"{name} inválido")
@dataclass(frozen=True,slots=True)
class TrainingLoadInput:
 sport:Sport; moving_time_seconds:float|None=None; elapsed_time_seconds:float|None=None; distance_meters:float|None=None; average_heart_rate_bpm:float|None=None; max_heart_rate_bpm:float|None=None; average_power_watts:float|None=None; normalized_power_watts:float|None=None; average_speed_mps:float|None=None; average_pace_seconds_per_km:float|None=None; swim_pace_seconds_per_100m:float|None=None; activity_start_time:datetime|None=None; ftp_watts:float|None=None; threshold_heart_rate_bpm:float|None=None; reference_max_heart_rate_bpm:float|None=None; resting_heart_rate_bpm:float|None=None; running_threshold_pace_seconds_per_km:float|None=None; swim_css_seconds_per_100m:float|None=None
 def __post_init__(self):
  for n in ("moving_time_seconds","elapsed_time_seconds","distance_meters","average_heart_rate_bpm","max_heart_rate_bpm","average_power_watts","normalized_power_watts","average_speed_mps","average_pace_seconds_per_km","swim_pace_seconds_per_100m","ftp_watts","threshold_heart_rate_bpm","reference_max_heart_rate_bpm","resting_heart_rate_bpm","running_threshold_pace_seconds_per_km","swim_css_seconds_per_100m"): _check(getattr(self,n),n,True)
@dataclass(frozen=True,slots=True)
class TrainingLoadResult:
 sport:Sport; load:float|None; unit:TrainingLoadUnit; method:TrainingLoadMethod; coverage:TrainingLoadCoverage; quality:TrainingLoadQuality|None; reason:TrainingLoadReason; algorithm_version:str; duration_seconds:float|None; reference_value:float|None=None; reference_unit:str|None=None; source_metrics:tuple[str,...]=(); warnings:tuple[str,...]=()
 def __post_init__(self):
  if self.load is not None and (not isfinite(self.load) or self.load<0):raise ValueError("Carga inválida")

