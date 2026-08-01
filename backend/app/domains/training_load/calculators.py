from .models import *
from .methods import select_method
ALGORITHM_VERSION="0.7b.1"
def _result(i,m,load,quality,ref=None,unit=None,src=(),warning=()): return TrainingLoadResult(i.sport,round(load,2) if load is not None else None,TrainingLoadUnit.LOAD_POINTS,m,TrainingLoadCoverage.COMPLETE if quality!=TrainingLoadQuality.LOW else TrainingLoadCoverage.PARTIAL,quality,TrainingLoadReason.CALCULATED,ALGORITHM_VERSION,i.moving_time_seconds,ref,unit,tuple(src),tuple(warning))
def calculate(i:TrainingLoadInput)->TrainingLoadResult:
 d=i.moving_time_seconds
 if d is None or d<=0:return TrainingLoadResult(i.sport,None,TrainingLoadUnit.LOAD_POINTS,TrainingLoadMethod.DURATION_ONLY,TrainingLoadCoverage.UNAVAILABLE,None,TrainingLoadReason.MISSING_DURATION,ALGORITHM_VERSION,d)
 m=select_method(i); h=d/3600
 if m is TrainingLoadMethod.CYCLING_POWER:
  p=i.normalized_power_watts or i.average_power_watts; load=h*(p/i.ftp_watts)**2*100; return _result(i,m,load,TrainingLoadQuality.HIGH if i.normalized_power_watts else TrainingLoadQuality.MEDIUM,i.ftp_watts,"W",("moving_time_seconds","normalized_power_watts" if i.normalized_power_watts else "average_power_watts","ftp_watts"))
 if m is TrainingLoadMethod.RUNNING_PACE:
  x=i.running_threshold_pace_seconds_per_km/i.average_pace_seconds_per_km; return _result(i,m,h*x*x*100,TrainingLoadQuality.MEDIUM,i.running_threshold_pace_seconds_per_km,"s/km",("moving_time_seconds","average_pace_seconds_per_km","running_threshold_pace_seconds_per_km"))
 if m is TrainingLoadMethod.SWIMMING_CSS:
  x=i.swim_css_seconds_per_100m/i.swim_pace_seconds_per_100m; return _result(i,m,h*x*x*100,TrainingLoadQuality.MEDIUM,i.swim_css_seconds_per_100m,"s/100m",("moving_time_seconds","swim_pace_seconds_per_100m","swim_css_seconds_per_100m"))
 if m is TrainingLoadMethod.HEART_RATE:
  if i.resting_heart_rate_bpm is not None and i.reference_max_heart_rate_bpm is not None:
   span=i.reference_max_heart_rate_bpm-i.resting_heart_rate_bpm
   if span<=0: return TrainingLoadResult(i.sport,None,TrainingLoadUnit.LOAD_POINTS,m,TrainingLoadCoverage.UNAVAILABLE,None,TrainingLoadReason.INVALID_VALUE,ALGORITHM_VERSION,d)
   x=max(0,min(1,(i.average_heart_rate_bpm-i.resting_heart_rate_bpm)/span)); q=TrainingLoadQuality.MEDIUM; src=("average_heart_rate_bpm","resting_heart_rate_bpm","reference_max_heart_rate_bpm")
  elif i.threshold_heart_rate_bpm: x=i.average_heart_rate_bpm/i.threshold_heart_rate_bpm;q=TrainingLoadQuality.LOW;src=("average_heart_rate_bpm","threshold_heart_rate_bpm")
  else: x=0
  return _result(i,m,h*x*x*100,q,i.threshold_heart_rate_bpm or i.reference_max_heart_rate_bpm,"bpm",src,("Carga aproximada basada en frecuencia cardiaca.",) if q is TrainingLoadQuality.LOW else ())
 if m is TrainingLoadMethod.DURATION_ONLY:return TrainingLoadResult(i.sport,round(h*50,2),TrainingLoadUnit.LOAD_POINTS,m,TrainingLoadCoverage.PARTIAL,TrainingLoadQuality.LOW,TrainingLoadReason.CALCULATED,ALGORITHM_VERSION,d,warnings=("Carga basada únicamente en duración; precisión limitada.",))
 return TrainingLoadResult(i.sport,None,TrainingLoadUnit.LOAD_POINTS,TrainingLoadMethod.DURATION_ONLY,TrainingLoadCoverage.NOT_APPLICABLE,None,TrainingLoadReason.UNSUPPORTED_SPORT,ALGORITHM_VERSION,d)


