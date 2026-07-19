from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models.performance_profile import AthletePerformanceProfileVersion
class PerformanceProfileError(ValueError): pass
class PerformanceProfileRepository:
 def __init__(self,session:Session): self.session=session
 def add_version(self,athlete_id:UUID,**values):
  fields=("resting_heart_rate_bpm","maximum_heart_rate_bpm","weight_kg","cycling_ftp_watts","cycling_threshold_heart_rate_bpm","running_threshold_heart_rate_bpm","running_threshold_pace_seconds_per_km","swimming_css_seconds_per_100m","preferred_pool_length_metres")
  if not values.get("effective_from") or not values.get("data_origin") or not values.get("algorithm_version"): raise PerformanceProfileError("Metadatos obligatorios")
  if not any(values.get(x) is not None for x in fields): raise PerformanceProfileError("El perfil no puede estar vacío")
  if values.get("resting_heart_rate_bpm") is not None and values.get("maximum_heart_rate_bpm") is not None and values["resting_heart_rate_bpm"]>=values["maximum_heart_rate_bpm"]: raise PerformanceProfileError("FC de reposo incompatible")
  if values.get("preferred_pool_length_metres") not in (None,25,50): raise PerformanceProfileError("Longitud de piscina inválida")
  row=AthletePerformanceProfileVersion(athlete_profile_id=athlete_id,**values); self.session.add(row); return row
 def latest(self,athlete_id): return self.session.scalar(select(AthletePerformanceProfileVersion).where(AthletePerformanceProfileVersion.athlete_profile_id==athlete_id).order_by(AthletePerformanceProfileVersion.effective_from.desc()).limit(1))
 def effective(self,athlete_id,at): return self.session.scalar(select(AthletePerformanceProfileVersion).where(AthletePerformanceProfileVersion.athlete_profile_id==athlete_id,AthletePerformanceProfileVersion.effective_from<=at).order_by(AthletePerformanceProfileVersion.effective_from.desc()).limit(1))
 def history(self,athlete_id): return list(self.session.scalars(select(AthletePerformanceProfileVersion).where(AthletePerformanceProfileVersion.athlete_profile_id==athlete_id).order_by(AthletePerformanceProfileVersion.effective_from.desc())))