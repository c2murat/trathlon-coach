from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Any
ALGORITHM_VERSION="0.6c.1"
@dataclass(frozen=True)
class MetricResult:
 key:str;status:str;value:float|None;unit:str|None;source:str|None;sample_count:int|None;coverage_ratio:float|None;quality_notes:list[str];unavailable_reason:str|None

def nums(values:Any)->list[float]:
 if not isinstance(values,list): return []
 return [float(x) for x in values if isinstance(x,(int,float)) and not isinstance(x,bool) and isfinite(float(x))]
def result(key, value, unit, source, count=None, ratio=None, reason=None, status=None, notes=None):
 return MetricResult(key,status or ("available" if value is not None else "unavailable"),value,unit,source,count,ratio,notes or [],reason)
def calculate(activity, streams:list[Any])->list[MetricResult]:
 by={s.stream_type:s for s in streams}; out=[]
 def observed(key,attr,unit,stream_type):
  stream=by.get(stream_type); vals=nums(getattr(stream,"values",None)) if stream else []
  if vals:return result(key,max(vals),unit,f"stream_{stream_type}",len(vals),1.0)
  value=getattr(activity,attr,None)
  return result(key,value,unit,"activity_summary" if value is not None else None,reason=None if value is not None else "missing_stream")
 out.append(result("moving_time",activity.moving_time_s,"s","activity_summary",reason=None if activity.moving_time_s is not None else "no_evidence"))
 out.append(result("elapsed_time",activity.elapsed_time_s,"s","activity_summary"))
 out.append(result("distance",activity.distance_m,"m","activity_summary",reason=None if activity.distance_m is not None else "no_evidence"))
 out.append(result("elevation_gain",activity.elevation_gain_m,"m","activity_summary",reason=None if activity.elevation_gain_m is not None else "no_evidence"))
 out.append(result("average_speed",activity.average_speed_mps*3.6 if activity.average_speed_mps is not None else None,"km/h","activity_summary",reason=None if activity.average_speed_mps is not None else "no_evidence"))
 out.append(observed("max_speed","max_speed_mps","m/s","velocity_smooth"))
 out.append(result("average_heart_rate",activity.average_heart_rate_bpm,"bpm","activity_summary",reason=None if activity.average_heart_rate_bpm is not None else "missing_stream"))
 out.append(observed("max_heart_rate","max_heart_rate_bpm","bpm","heartrate"))
 out.append(result("average_power",activity.average_power_w,"W","activity_summary",reason=None if activity.average_power_w is not None else "missing_stream"))
 out.append(observed("max_power","max_power_w","W","watts"))
 out.append(result("average_cadence",activity.average_cadence_rpm,"rpm","activity_summary",reason=None if activity.average_cadence_rpm is not None else "missing_stream"))
 out.append(result("lap_count",len(activity.laps),"laps","laps"))
 out.append(result("stream_sample_count",sum(getattr(s,"sample_count",0) or 0 for s in streams),"samples","streams"))
 return out