from datetime import datetime, timezone
from app.application.performance_references import PerformanceReferenceRepository
from app.application.performance_profiles import PerformanceProfileRepository
from app.domains.performance_profile.zones import *

def _domain(row):
    return PerformanceReference(Sport(row.sport), MetricType(row.metric_type), float(row.value), Unit(row.unit), DataOrigin(row.data_origin), row.algorithm_version or ALGORITHM_VERSION, row.effective_from, CalculationMethod(row.calculation_method) if row.calculation_method else None, row.source_note, QualityLevel(row.quality_level) if row.quality_level else None, row.measured_at)

def _historical(profile, sport, metric):
    mapping={(Sport.CYCLING,MetricType.POWER):(profile.cycling_ftp_watts,Unit.WATT),(Sport.CYCLING,MetricType.HEART_RATE):(profile.cycling_threshold_heart_rate_bpm or profile.maximum_heart_rate_bpm,Unit.BPM),(Sport.RUNNING,MetricType.PACE):(profile.running_threshold_pace_seconds_per_km,Unit.SECOND_PER_KM),(Sport.RUNNING,MetricType.HEART_RATE):(profile.running_threshold_heart_rate_bpm or profile.maximum_heart_rate_bpm,Unit.BPM),(Sport.SWIMMING,MetricType.SWIM_PACE):(profile.swimming_css_seconds_per_100m,Unit.SECOND_PER_100M)}
    value,unit=mapping[(sport,metric)]
    return None if value is None else PerformanceReference(sport,metric,float(value),unit,DataOrigin.MANUAL,profile.algorithm_version,profile.effective_from,None,"Perfil histórico 0.7A.2",None,None)

def resolve_zone_sets(session, athlete_id, effective_at=None):
    at=effective_at or datetime.now(timezone.utc); refs=PerformanceReferenceRepository(session); profile=PerformanceProfileRepository(session).effective(athlete_id,at); out=[]
    specs=[(Sport.CYCLING,MetricType.POWER,cycling_power_zones),(Sport.CYCLING,MetricType.HEART_RATE,heart_rate_zones),(Sport.RUNNING,MetricType.PACE,running_pace_zones),(Sport.RUNNING,MetricType.HEART_RATE,heart_rate_zones),(Sport.SWIMMING,MetricType.SWIM_PACE,swimming_zones)]
    for sport,metric,calc in specs:
        row=refs.best_effective_reference(athlete_id,sport,metric,at)
        ref=_domain(row) if row else (_historical(profile,sport,metric) if profile else None)
        if ref is None: continue
        zs=calc(ref); source="granular_reference" if row else "historical_profile"
        out.append({"sport":sport.value,"metric_type":metric.value,"zones":[{"number":z.number,"name":z.name,"lower":z.lower,"upper":z.upper,"unit":z.unit.value,"reference":z.reference_value,"method":z.method.value,"algorithm_version":z.algorithm_version} for z in zs.zones],"reference":{"reference_id":str(row.id) if row else None,"value":ref.value,"unit":ref.unit.value,"origin":row.data_origin if row else "manual","quality":row.quality_level if row else None,"effective_from":ref.effective_from,"algorithm_version":ref.algorithm_version},"source_type":source,"obsolete":is_obsolete(ref,at) if source=="granular_reference" else False})
    return out
