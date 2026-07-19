"""Dominio puro de perfil de rendimiento y zonas (0.7a.1).

Contrato: intervalos [inferior, superior), con la última zona abierta.
Para ritmo, los valores menores son más intensos; las zonas se presentan de
rápido a lento y la clasificación usa los mismos intervalos numéricos.
Los cortes se calculan con precisión completa y se redondean una sola vez a
2 decimales; la frontera compartida se reutiliza literalmente.
"""
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Sequence
class Sport(str,Enum): RUNNING="running"; CYCLING="cycling"; SWIMMING="swimming"
class MetricType(str,Enum): HEART_RATE="heart_rate"; POWER="power"; PACE="pace"; SWIM_PACE="swim_pace"
class Unit(str,Enum): BPM="bpm"; WATT="W"; KMH="km/h"; SECOND_PER_KM="s/km"; SECOND_PER_100M="s/100m"
class CalculationMethod(str,Enum): HR_MAX_PERCENT="hr_max_percent"; FTP_PERCENT="ftp_percent"; THRESHOLD_PACE_PERCENT="threshold_pace_percent"; CSS_PERCENT="css_percent"
class DataOrigin(str,Enum): MANUAL="manual"; MEASURED="measured"; IMPORTED="imported"; DERIVED="derived"; ESTIMATED="estimated"; ATHLETE_ENTERED="manual"
class IntensityDirection(str,Enum): ASCENDING="ascending"; DESCENDING="descending"
class QualityLevel(str,Enum): LOW="low"; MEDIUM="medium"; HIGH="high"; CONFIRMED="confirmed"
ALGORITHM_VERSION="0.7a.1"
@dataclass(frozen=True,slots=True)
class PerformanceReference:
 sport:Sport; metric:MetricType; value:float; unit:Unit; origin:DataOrigin=DataOrigin.ATHLETE_ENTERED; algorithm_version:str=ALGORITHM_VERSION; effective_from:object|None=None; calculation_method:CalculationMethod|None=None; source_note:str|None=None; quality_level:QualityLevel|None=None; measured_at:object|None=None
@dataclass(frozen=True,slots=True)
class AthletePerformanceInputs:
 max_heart_rate:float|None=None; resting_heart_rate:float|None=None; cycling_threshold_heart_rate:float|None=None; running_threshold_heart_rate:float|None=None; cycling_ftp:float|None=None; running_threshold_pace:float|None=None; swimming_css:float|None=None
@dataclass(frozen=True,slots=True)
class DerivedPerformanceValue:
 value:float; unit:Unit; source_value:float; source_unit:Unit; formula:str; algorithm_version:str=ALGORITHM_VERSION
@dataclass(frozen=True,slots=True)
class TrainingZone:
 number:int; name:str; lower:float; upper:float|None; unit:Unit; reference_value:float; method:CalculationMethod; algorithm_version:str=ALGORITHM_VERSION
@dataclass(frozen=True,slots=True)
class ZoneSet:
 sport:Sport; metric:MetricType; reference:PerformanceReference; zones:tuple[TrainingZone,...]; direction:IntensityDirection; algorithm_version:str=ALGORITHM_VERSION
 def __post_init__(self): validate_zone_set(self)

def _valid(ref,sport,metric,unit):
 if ref.sport is not sport or ref.metric is not metric or ref.unit is not unit: raise ValueError("Referencia incompatible")
 if not ref.algorithm_version or not isinstance(ref.value,(int,float)) or isinstance(ref.value,bool) or not isfinite(ref.value) or ref.value<=0: raise ValueError("La referencia debe ser positiva y finita")
def _round(x): return round(float(x),2)
def _build(sport,metric,ref,unit,method,names,bounds,direction):
 cuts=tuple(_round(x) for x in bounds); zones=tuple(TrainingZone(i+1,n,cuts[i],None if i==len(names)-1 else cuts[i+1],unit,ref.value,method) for i,n in enumerate(names)); return ZoneSet(sport,metric,ref,zones,direction)
def heart_rate_zones(ref):
 _valid(ref,ref.sport,MetricType.HEART_RATE,Unit.BPM); return _build(ref.sport,MetricType.HEART_RATE,ref,Unit.BPM,CalculationMethod.HR_MAX_PERCENT,("Recuperación","Aeróbica","Tempo","Umbral","Máxima"),tuple(ref.value*x for x in (0,.6,.7,.8,.9)),IntensityDirection.ASCENDING)
def cycling_power_zones(ref):
 _valid(ref,Sport.CYCLING,MetricType.POWER,Unit.WATT); return _build(Sport.CYCLING,MetricType.POWER,ref,Unit.WATT,CalculationMethod.FTP_PERCENT,("Recuperación","Resistencia","Tempo","Umbral","VO2 máx","Capacidad anaeróbica","Neuromuscular"),tuple(ref.value*x for x in (0,.55,.75,.9,1.05,1.2,1.5)),IntensityDirection.ASCENDING)
def running_pace_zones(ref):
 _valid(ref,Sport.RUNNING,MetricType.PACE,Unit.SECOND_PER_KM); return _build(Sport.RUNNING,MetricType.PACE,ref,Unit.SECOND_PER_KM,CalculationMethod.THRESHOLD_PACE_PERCENT,("Intervalos","Umbral","Tempo","Resistencia","Recuperación"),tuple(ref.value/f for f in (1.15,1.07,1,.93,.86)),IntensityDirection.DESCENDING)
def swimming_zones(ref):
 _valid(ref,Sport.SWIMMING,MetricType.SWIM_PACE,Unit.SECOND_PER_100M); return _build(Sport.SWIMMING,MetricType.SWIM_PACE,ref,Unit.SECOND_PER_100M,CalculationMethod.CSS_PERCENT,("Velocidad","Umbral","Tempo","Resistencia","Recuperación"),tuple(ref.value/f for f in (1.15,1.07,1,.93,.86)),IntensityDirection.DESCENDING)
def validate_zone_set(zone_set:ZoneSet)->None:
 z=zone_set.zones
 if not z or any(x.number!=i+1 for i,x in enumerate(z)): raise ValueError("Zonas no consecutivas")
 if sum(x.upper is None for x in z)!=1 or z[-1].upper is not None: raise ValueError("Solo la última zona puede ser abierta")
 for i,x in enumerate(z):
  if x.lower<0 or (x.upper is not None and x.upper<=x.lower): raise ValueError("Límites inválidos")
  if x.unit is not zone_set.reference.unit or x.algorithm_version!=zone_set.algorithm_version or x.reference_value!=zone_set.reference.value: raise ValueError("Zonas inconsistentes")
  if i and z[i-1].upper!=x.lower: raise ValueError("Hueco o solapamiento")
def classify_value(zone_set:ZoneSet,value:float)->TrainingZone:
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value): raise ValueError("Valor inválido")
 for z in zone_set.zones:
  if value>=z.lower and (z.upper is None or value<z.upper): return z
 raise ValueError("Valor fuera de las zonas")
def pace_to_speed_kmh(pace_seconds_per_km:float)->DerivedPerformanceValue:
 if isinstance(pace_seconds_per_km,bool) or not isfinite(pace_seconds_per_km) or pace_seconds_per_km<=0: raise ValueError("Ritmo inválido")
 return DerivedPerformanceValue(3600/pace_seconds_per_km,Unit.KMH,pace_seconds_per_km,Unit.SECOND_PER_KM,"3600 / segundos_por_km")
def validate_reference_compatibility(sport:Sport, metric:MetricType, unit:Unit)->None:
 allowed={(Sport.CYCLING,MetricType.POWER,Unit.WATT),(Sport.CYCLING,MetricType.HEART_RATE,Unit.BPM),(Sport.RUNNING,MetricType.PACE,Unit.SECOND_PER_KM),(Sport.RUNNING,MetricType.HEART_RATE,Unit.BPM),(Sport.SWIMMING,MetricType.SWIM_PACE,Unit.SECOND_PER_100M)}
 if (sport,metric,unit) not in allowed: raise ValueError("Combinación de deporte, métrica y unidad incompatible")
def speed_kmh_to_pace(speed_kmh:float)->DerivedPerformanceValue:
 if isinstance(speed_kmh,bool) or not isfinite(speed_kmh) or speed_kmh<=0: raise ValueError("Velocidad inválida")
 return DerivedPerformanceValue(3600/speed_kmh,Unit.SECOND_PER_KM,speed_kmh,Unit.WATT,"3600 / kmh")
def reference_priority(origin:DataOrigin)->int:
 return {DataOrigin.MEASURED:5,DataOrigin.MANUAL:4,DataOrigin.IMPORTED:3,DataOrigin.DERIVED:2,DataOrigin.ESTIMATED:1}[origin]
def select_effective_reference(references,at):
 candidates=[r for r in references if r.effective_from is None or r.effective_from<=at]; return max(candidates,key=lambda r:(r.effective_from or 0,reference_priority(r.origin)),default=None)
def select_best_reference(references,at=None):
 candidates=[r for r in references if at is None or r.effective_from is None or r.effective_from<=at]; return max(candidates,key=lambda r:reference_priority(r.origin),default=None)
def is_obsolete(reference,now,max_age_days=365): return bool(reference.effective_from is not None and (now-reference.effective_from).days>max_age_days)

