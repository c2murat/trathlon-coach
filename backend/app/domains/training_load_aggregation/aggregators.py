from datetime import timedelta
from collections import defaultdict
from decimal import Decimal,ROUND_HALF_UP
from .models import *
AGGREGATION_ALGORITHM_VERSION="0.7c.1"
def _zone(name):
 if not isinstance(name,str) or not name.strip(): raise InvalidTimezoneError(name)
 try:return ZoneInfo(name)
 except (ZoneInfoNotFoundError,ValueError) as e:raise InvalidTimezoneError(name) from e
def _prepare(entries,zone,version):
 xs=list(entries); seen=set()
 for x in xs:
  if x.activity_id in seen:raise DuplicateActivityEntryError(str(x.activity_id))
  seen.add(x.activity_id)
  if x.algorithm_version!=version:raise MixedAlgorithmVersionError("algorithm versions cannot be mixed")
 return xs
def _quality(xs,loaded,coverage):
 if not loaded:return AggregateQuality.UNAVAILABLE
 if any((x.quality or "")=="low" for x in xs if x.load_value is not None):return AggregateQuality.LOW
 if coverage is AggregateCoverage.PARTIAL:return AggregateQuality.MEDIUM
 return AggregateQuality.HIGH if all((x.quality or "high")=="high" for x in xs if x.load_value is not None) else AggregateQuality.MEDIUM
def _make(day,xs,tz,version):
 loaded=[x for x in xs if x.load_value is not None]; null=len(xs)-len(loaded);cov=AggregateCoverage.COMPLETE if not null else AggregateCoverage.PARTIAL; warnings=[]
 if null:warnings.append("contains_null_loads")
 if any(x.duration_seconds is None for x in xs):warnings.append("contains_missing_durations")
 return DailyTrainingLoadAggregate(day,tz,version,AGGREGATION_ALGORITHM_VERSION,Decimal(sum((Decimal(str(x.load_value)) for x in loaded),Decimal(0))).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP),len(xs),len(loaded),null,Decimal(sum((Decimal(str(x.duration_seconds)) for x in xs if x.duration_seconds is not None),Decimal(0))),cov,_quality(xs,len(loaded),cov),tuple(str(x.activity_id) for x in sorted(xs,key=lambda x:(x.activity_start_at,x.activity_id))),tuple(warnings))
def aggregate_daily_training_load(entries,*,timezone_name,source_algorithm_version):
 z=_zone(timezone_name); groups=defaultdict(list)
 for x in _prepare(entries,z,source_algorithm_version):groups[x.activity_start_at.astimezone(z).date()].append(x)
 return tuple(_make(d,groups[d],timezone_name,source_algorithm_version) for d in sorted(groups))
def aggregate_weekly_training_load(entries,*,timezone_name,source_algorithm_version):
 xs=_prepare(entries,_zone(timezone_name),source_algorithm_version); daily=aggregate_daily_training_load(xs,timezone_name=timezone_name,source_algorithm_version=source_algorithm_version); groups=defaultdict(list); z=_zone(timezone_name)
 for x in xs: groups[x.activity_start_at.astimezone(z).date().isocalendar()[:2]].append(x)
 byday={(d.local_date):d for d in daily}; out=[]
 for (year,week),items in sorted(groups.items()):
  days=tuple(byday[d] for d in sorted(byday) if d.isocalendar()[:2]==(year,week)); loaded=[x for x in items if x.load_value is not None]; null=len(items)-len(loaded); cov=AggregateCoverage.COMPLETE if not null else AggregateCoverage.PARTIAL; q=_quality(items,len(loaded),cov); start=days[0].local_date-timedelta(days=days[0].local_date.weekday()); end=start+timedelta(days=6); total=Decimal(sum((Decimal(str(x.load_value)) for x in loaded),Decimal(0))).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP); warns=tuple(sorted({w for d in days for w in d.warnings})); ids=tuple(str(x.activity_id) for x in sorted(items,key=lambda x:(x.activity_start_at,x.activity_id)))
  out.append(WeeklyTrainingLoadAggregate(year,week,start,end,timezone_name,source_algorithm_version,AGGREGATION_ALGORITHM_VERSION,total,len(items),len(loaded),null,Decimal(sum((Decimal(str(x.duration_seconds)) for x in items if x.duration_seconds is not None),Decimal(0))),cov,q,days,ids,warns))
 return tuple(out)

