from .models import *
ALGORITHM_VERSION="0.7b.1"
def select_method(i:TrainingLoadInput):
 if i.sport is Sport.CYCLING:
  if (i.normalized_power_watts or i.average_power_watts) and i.ftp_watts:return TrainingLoadMethod.CYCLING_POWER
  if i.average_heart_rate_bpm and (i.resting_heart_rate_bpm is not None and i.reference_max_heart_rate_bpm is not None or i.threshold_heart_rate_bpm):return TrainingLoadMethod.HEART_RATE
 if i.sport is Sport.RUNNING:
  if i.average_pace_seconds_per_km and i.running_threshold_pace_seconds_per_km:return TrainingLoadMethod.RUNNING_PACE
  if i.average_heart_rate_bpm and (i.threshold_heart_rate_bpm or i.resting_heart_rate_bpm is not None and i.reference_max_heart_rate_bpm is not None):return TrainingLoadMethod.HEART_RATE
 if i.sport is Sport.SWIMMING:
  if i.swim_pace_seconds_per_100m and i.swim_css_seconds_per_100m:return TrainingLoadMethod.SWIMMING_CSS
  if i.average_heart_rate_bpm and (i.threshold_heart_rate_bpm or i.resting_heart_rate_bpm is not None and i.reference_max_heart_rate_bpm is not None):return TrainingLoadMethod.HEART_RATE
 if i.average_heart_rate_bpm and (i.threshold_heart_rate_bpm or i.resting_heart_rate_bpm is not None and i.reference_max_heart_rate_bpm is not None):return TrainingLoadMethod.HEART_RATE
 return TrainingLoadMethod.DURATION_ONLY if i.moving_time_seconds else None
