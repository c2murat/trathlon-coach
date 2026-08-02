from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from app.domains.manual_strength import ALGORITHM_VERSION
from .models import AggregateCoverage, AggregateQuality, DailyTrainingLoadAggregate, WeeklyTrainingLoadAggregate

@dataclass(frozen=True, slots=True)
class CombinedDailyTrainingLoadAggregate:
    local_date: date; timezone: str; source_load_algorithm_version: str; aggregation_algorithm_version: str
    total_load: Decimal; endurance_load: Decimal; strength_load: Decimal; strength_session_count: int
    manual_strength_algorithm_version: str; activity_count: int; loaded_activity_count: int
    null_load_activity_count: int; total_duration_seconds: Decimal; coverage: AggregateCoverage
    quality: AggregateQuality; activity_ids: tuple = (); warnings: tuple = ()

@dataclass(frozen=True, slots=True)
class CombinedWeeklyTrainingLoadAggregate:
    iso_year: int; iso_week: int; week_start_date: date; week_end_date: date; timezone: str
    source_load_algorithm_version: str; aggregation_algorithm_version: str; total_load: Decimal
    endurance_load: Decimal; strength_load: Decimal; strength_session_count: int
    manual_strength_algorithm_version: str; activity_count: int; loaded_activity_count: int
    null_load_activity_count: int; total_duration_seconds: Decimal; coverage: AggregateCoverage
    quality: AggregateQuality; daily_aggregates: tuple = (); activity_ids: tuple = (); warnings: tuple = ()


@dataclass(frozen=True, slots=True)
class ManualStrengthLoadEntry:
    session_id: object
    session_start_at: datetime
    load_value: Decimal | float
    algorithm_version: str


def _money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def combine_daily_training_load(
    endurance: tuple[DailyTrainingLoadAggregate, ...],
    strength_entries: tuple[ManualStrengthLoadEntry, ...],
    *,
    timezone_name: str,
    source_algorithm_version: str,
    manual_strength_algorithm_version: str = ALGORITHM_VERSION,
):
    zone = ZoneInfo(timezone_name)
    strength_by_day = defaultdict(dict)
    for entry in strength_entries:
        if entry.algorithm_version == manual_strength_algorithm_version:
            strength_by_day[entry.session_start_at.astimezone(zone).date()][entry.session_id] = Decimal(str(entry.load_value))
    endurance_by_day = {item.local_date: item for item in endurance}
    results = []
    for local_date in sorted(set(endurance_by_day) | set(strength_by_day)):
        base = endurance_by_day.get(local_date)
        strength_values = strength_by_day.get(local_date, {}).values()
        strength_load = _money(sum(strength_values, Decimal(0)))
        endurance_load = base.total_load if base else Decimal("0.00")
        results.append(CombinedDailyTrainingLoadAggregate(
            local_date=local_date, timezone=timezone_name,
            source_load_algorithm_version=source_algorithm_version,
            aggregation_algorithm_version=base.aggregation_algorithm_version if base else "0.7c.1",
            total_load=_money(endurance_load + strength_load),
            activity_count=base.activity_count if base else 0,
            loaded_activity_count=base.loaded_activity_count if base else 0,
            null_load_activity_count=base.null_load_activity_count if base else 0,
            total_duration_seconds=base.total_duration_seconds if base else Decimal(0),
            coverage=base.coverage if base else AggregateCoverage.UNAVAILABLE,
            quality=base.quality if base else AggregateQuality.UNAVAILABLE,
            activity_ids=base.activity_ids if base else (), warnings=base.warnings if base else (),
            endurance_load=endurance_load, strength_load=strength_load,
            strength_session_count=len(strength_by_day.get(local_date, {})),
            manual_strength_algorithm_version=manual_strength_algorithm_version,
        ))
    return tuple(results)


def combine_weekly_training_load(
    endurance: tuple[WeeklyTrainingLoadAggregate, ...],
    daily: tuple[DailyTrainingLoadAggregate, ...],
    *,
    timezone_name: str,
    source_algorithm_version: str,
    manual_strength_algorithm_version: str = ALGORITHM_VERSION,
):
    endurance_by_week = {(item.iso_year, item.iso_week): item for item in endurance}
    days_by_week = defaultdict(list)
    for item in daily:
        days_by_week[item.local_date.isocalendar()[:2]].append(item)
    results = []
    for key in sorted(set(endurance_by_week) | set(days_by_week)):
        base = endurance_by_week.get(key); days = tuple(sorted(days_by_week[key], key=lambda item: item.local_date))
        start = date.fromisocalendar(key[0], key[1], 1)
        endurance_load = _money(sum((item.endurance_load for item in days), Decimal(0)))
        strength_load = _money(sum((item.strength_load for item in days), Decimal(0)))
        results.append(CombinedWeeklyTrainingLoadAggregate(
            iso_year=key[0], iso_week=key[1], week_start_date=start, week_end_date=start + timedelta(days=6),
            timezone=timezone_name, source_load_algorithm_version=source_algorithm_version,
            aggregation_algorithm_version=base.aggregation_algorithm_version if base else "0.7c.1",
            total_load=_money(endurance_load + strength_load), activity_count=base.activity_count if base else 0,
            loaded_activity_count=base.loaded_activity_count if base else 0,
            null_load_activity_count=base.null_load_activity_count if base else 0,
            total_duration_seconds=base.total_duration_seconds if base else Decimal(0),
            coverage=base.coverage if base else AggregateCoverage.UNAVAILABLE,
            quality=base.quality if base else AggregateQuality.UNAVAILABLE,
            daily_aggregates=days, activity_ids=base.activity_ids if base else (), warnings=base.warnings if base else (),
            endurance_load=endurance_load, strength_load=strength_load,
            strength_session_count=sum(item.strength_session_count for item in days),
            manual_strength_algorithm_version=manual_strength_algorithm_version,
        ))
    return tuple(results)
