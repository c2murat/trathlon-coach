from app.domains.performance_profile.zones import *
def test_hr_zones_contiguous_and_deterministic():
 r=PerformanceReference(Sport.RUNNING,MetricType.HEART_RATE,190,Unit.BPM); a=heart_rate_zones(r); assert a==heart_rate_zones(r); assert a.zones[0].lower==0; assert a.zones[-1].upper is None
def test_power_zones_from_ftp():
 z=cycling_power_zones(PerformanceReference(Sport.CYCLING,MetricType.POWER,250,Unit.WATT)); assert z.zones[1].lower==137.5; assert z.zones[-1].upper is None
def test_pace_is_inverse_and_ordered():
 z=running_pace_zones(PerformanceReference(Sport.RUNNING,MetricType.PACE,300,Unit.SECOND_PER_KM)); assert z.zones[0].lower<z.zones[1].lower; assert z.zones[0].upper==z.zones[1].lower
def test_swim_css_and_invalid():
 z=swimming_zones(PerformanceReference(Sport.SWIMMING,MetricType.SWIM_PACE,100,Unit.SECOND_PER_100M)); assert z.zones[-1].upper is None
 try: cycling_power_zones(PerformanceReference(Sport.CYCLING,MetricType.POWER,0,Unit.WATT)); assert False
 except ValueError: pass
def test_classification_boundaries_and_derivations():
 r=PerformanceReference(Sport.CYCLING,MetricType.POWER,200,Unit.WATT); z=cycling_power_zones(r); assert classify_value(z,z.zones[1].lower) is z.zones[1]; assert classify_value(z,999) is z.zones[-1]
 p=pace_to_speed_kmh(300); assert round(p.value,2)==12; assert speed_kmh_to_pace(p.value).value==300

def test_invalid_bool_nan_and_mixed_reference():
 for value in (0,-1,True,float("nan"),float("inf")):
  try: cycling_power_zones(PerformanceReference(Sport.CYCLING,MetricType.POWER,value,Unit.WATT)); assert False
  except ValueError: pass

def test_reference_metadata_and_priority():
 validate_reference_compatibility(Sport.CYCLING,MetricType.POWER,Unit.WATT)
 try: validate_reference_compatibility(Sport.CYCLING,MetricType.PACE,Unit.SECOND_PER_KM); assert False
 except ValueError: pass
