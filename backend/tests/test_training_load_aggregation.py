from datetime import datetime,timezone
from decimal import Decimal
import pytest
from app.domains.training_load_aggregation import *
def e(i,dt="2026-07-19T22:30:00+00:00",load=10,quality="high",duration=3600,version="0.7b.1"):return ActivityLoadEntry(i,datetime.fromisoformat(dt),load,version,quality=quality,duration_seconds=duration)
def test_daily_timezone_and_nulls():
 r=aggregate_daily_training_load([e("b",load=None),e("a")],timezone_name="Europe/Madrid",source_algorithm_version="0.7b.1")[0];assert r.local_date.isoformat()=="2026-07-20" and r.total_load==Decimal("10.00") and r.activity_count==2 and r.coverage is AggregateCoverage.PARTIAL
def test_week_iso():
 r=aggregate_weekly_training_load([e("a","2025-12-29T12:00:00+00:00")],timezone_name="UTC",source_algorithm_version="0.7b.1")[0];assert (r.iso_year,r.iso_week)==(2026,1) and r.week_start_date.isoformat()=="2025-12-29"
def test_validation():
 with pytest.raises(InvalidAggregationInputError):e("a","2026-01-01T00:00:00",1)
 with pytest.raises(MixedAlgorithmVersionError):aggregate_daily_training_load([e("a"),e("b",version="x")],timezone_name="UTC",source_algorithm_version="0.7b.1")
 with pytest.raises(DuplicateActivityEntryError):aggregate_daily_training_load([e("a"),e("a")],timezone_name="UTC",source_algorithm_version="0.7b.1")
def test_precision_and_quality():
 r=aggregate_daily_training_load([e("a",load=Decimal("10.005")),e("b",load=Decimal("10.005"),quality="medium")],timezone_name="UTC",source_algorithm_version="0.7b.1")[0];assert r.total_load==Decimal("20.01") and r.quality is AggregateQuality.MEDIUM
from dataclasses import FrozenInstanceError
from decimal import Decimal
from datetime import datetime,timezone
import math,pytest
from app.domains.training_load_aggregation import *
def mk(i,dt="2026-07-19T12:00:00+00:00",load=1,q="high",dur=10,v="0.7b.1"):return ActivityLoadEntry(i,datetime.fromisoformat(dt),load,v,quality=q,duration_seconds=dur)
@pytest.mark.parametrize("value",[True,-1,float("nan"),float("inf"),-float("inf"),Decimal("NaN"),Decimal("Infinity")])
def test_invalid_loads(value):
 with pytest.raises(InvalidAggregationInputError):mk("x",load=value)
@pytest.mark.parametrize("dur",[True,-1,float("nan"),float("inf")])
def test_invalid_durations(dur):
 with pytest.raises(InvalidAggregationInputError):mk("x",dur=dur)
def test_empty_and_invalid_timezone():
 assert aggregate_daily_training_load([],timezone_name="Europe/Madrid",source_algorithm_version="0.7b.1")==()
 for z in (""," ","No/Such"):
  with pytest.raises(InvalidTimezoneError):aggregate_daily_training_load([],timezone_name=z,source_algorithm_version="0.7b.1")
def test_madrid_winter_summer_midnight():
 r=aggregate_daily_training_load([mk("a","2026-01-10T23:30:00+00:00"),mk("b","2026-07-19T22:30:00+00:00")],timezone_name="Europe/Madrid",source_algorithm_version="0.7b.1");assert [x.local_date.isoformat() for x in r]==["2026-01-11","2026-07-20"]
def test_zero_vs_null_and_quality():
 z=aggregate_daily_training_load([mk("z",load=0)],timezone_name="UTC",source_algorithm_version="0.7b.1")[0]; n=aggregate_daily_training_load([mk("n",load=None)],timezone_name="UTC",source_algorithm_version="0.7b.1")[0];assert z.loaded_activity_count==1 and z.coverage is AggregateCoverage.COMPLETE and n.loaded_activity_count==0 and n.quality is AggregateQuality.UNAVAILABLE
def test_quality_matrix_and_order():
 r=aggregate_daily_training_load([mk("b",load=2,q="medium"),mk("a",load=1,q="high")],timezone_name="UTC",source_algorithm_version="0.7b.1")[0];assert r.quality is AggregateQuality.MEDIUM and r.activity_ids==("a","b")
def test_duplicate_and_versions():
 with pytest.raises(DuplicateActivityEntryError):aggregate_daily_training_load([mk("x"),mk("x")],timezone_name="UTC",source_algorithm_version="0.7b.1")
 with pytest.raises(MixedAlgorithmVersionError):aggregate_daily_training_load([mk("x"),mk("y",v="0.7b.10")],timezone_name="UTC",source_algorithm_version="0.7b.1")
def test_iso_53_and_immutability_and_precision():
 r=aggregate_weekly_training_load([mk("a","2026-12-31T12:00:00+00:00",load=Decimal("10.004")),mk("b","2026-12-28T12:00:00+00:00",load=Decimal("10.004")),mk("c","2026-12-30T12:00:00+00:00",load=Decimal("10.004"))],timezone_name="UTC",source_algorithm_version="0.7b.1")[0];assert r.iso_week==53 and r.total_load==Decimal("30.01") and r.week_start_date.weekday()==0 and r.week_end_date.weekday()==6
 with pytest.raises(FrozenInstanceError):r.total_load=Decimal(0)
def test_generator_and_determinism():
 xs=[mk("a"),mk("b",dt="2026-07-20T12:00:00+00:00")];assert aggregate_daily_training_load(xs,timezone_name="UTC",source_algorithm_version="0.7b.1")==aggregate_daily_training_load(reversed(xs),timezone_name="UTC",source_algorithm_version="0.7b.1")
