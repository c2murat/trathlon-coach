from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from uuid import UUID

from app.domains.capability.models import (
    CAPABILITY_WINDOW_DAYS, AthleteCapabilityContext, CapabilityConfidence,
    CapabilityPoint, LongSessionTolerance, OverallTrainingSummary,
    RECENCY_WEIGHTS, ReferenceStalenessSignal, RepeatLikeEffort, SportCapabilityProfile,
    SportTrainingSummary,
)
from app.domains.planning.contracts import PerformanceSnapshot


RUN_DURATIONS = (20, 30, 60, 120, 180, 300, 600, 1200, 1800, 2400)
BIKE_DURATIONS = (60, 180, 300, 600, 1200, 2400, 3600)
SWIM_DISTANCES = (50, 100, 200, 400)
TREND_TOLERANCE = Decimal("0.15")
REPEAT_CLUSTER_TOLERANCE = Decimal("0.12")
SWIM_MIN_MOVING_TO_ELAPSED_RATIO = Decimal("0.75")


@dataclass(frozen=True)
class ActivityEvidence:
    activity_id: UUID
    sport: str
    local_date: date
    duration_seconds: int
    distance_m: Decimal | None
    average_speed_mps: Decimal | None = None
    average_power_w: Decimal | None = None
    coverage: Decimal = Decimal("1")


@dataclass(frozen=True)
class LapEvidence:
    activity_id: UUID
    sport: str
    local_date: date
    lap_index: int
    duration_seconds: int
    distance_m: Decimal | None
    average_speed_mps: Decimal | None
    average_power_w: Decimal | None
    coverage: Decimal = Decimal("1")
    elapsed_seconds: int | None = None
    moving_seconds: int | None = None


def capability_window(as_of_date: date) -> tuple[date, date]:
    return as_of_date - timedelta(days=CAPABILITY_WINDOW_DAYS - 1), as_of_date


def _bucket(as_of: date, day: date) -> str:
    age = (as_of - day).days
    return "RECENT" if age < 28 else "MID" if age < 56 else "OLDER"


def _weighted_median(rows, as_of: date) -> Decimal:
    ordered = sorted(rows, key=lambda pair: pair[0])
    weighted = [(value, RECENCY_WEIGHTS[_bucket(as_of, lap.local_date)]) for value, lap in ordered]
    threshold = sum((weight for _, weight in weighted), Decimal(0)) / 2
    cumulative = Decimal(0)
    for value, weight in weighted:
        cumulative += weight
        if cumulative >= threshold:
            return _q(value)
    return _q(weighted[-1][0])


def _confidence(support: int, days: int, coverage: Decimal) -> CapabilityConfidence:
    if support <= 0:
        return CapabilityConfidence.INSUFFICIENT
    if support >= 4 and days <= 28 and coverage >= Decimal("0.75"):
        return CapabilityConfidence.HIGH
    if support >= 2 and days <= 56 and coverage >= Decimal("0.50"):
        return CapabilityConfidence.MEDIUM
    return CapabilityConfidence.LOW


def _context_confidence(activity_count: int, weeks: int, coverage: Decimal) -> CapabilityConfidence:
    if activity_count == 0:
        return CapabilityConfidence.INSUFFICIENT
    if weeks >= 8 and activity_count >= 12 and coverage >= Decimal("0.66"):
        return CapabilityConfidence.HIGH
    if weeks >= 4 and activity_count >= 6:
        return CapabilityConfidence.MEDIUM
    return CapabilityConfidence.LOW


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _classify(item: ActivityEvidence, sport: str, performance: PerformanceSnapshot) -> str:
    long_cutoff = 75 * 60 if sport == "cycling" else 60 * 60 if sport == "running" else None
    if long_cutoff and item.duration_seconds >= long_cutoff:
        return "long"
    if sport == "cycling" and item.average_power_w and performance.cycling_ftp_watts:
        ratio = item.average_power_w / performance.cycling_ftp_watts
        return "recovery" if ratio < Decimal("0.55") else "easy/endurance" if ratio < Decimal("0.76") else "tempo" if ratio < Decimal("0.91") else "threshold" if ratio <= Decimal("1.05") else "interval/VO2"
    if sport == "running" and item.average_speed_mps and performance.running_threshold_pace_seconds_per_km:
        ratio = (Decimal(1000) / item.average_speed_mps) / performance.running_threshold_pace_seconds_per_km
        return "easy/endurance" if ratio > Decimal("1.12") else "tempo" if ratio > Decimal("1.03") else "threshold" if ratio >= Decimal("0.97") else "interval/VO2"
    if sport == "swimming" and item.average_speed_mps and performance.swimming_css_seconds_per_100m:
        ratio = (Decimal(100) / item.average_speed_mps) / performance.swimming_css_seconds_per_100m
        return "easy/endurance" if ratio > Decimal("1.08") else "tempo" if ratio > Decimal("1.03") else "threshold" if ratio >= Decimal("0.97") else "interval/VO2"
    return "unknown"


def _summary(sport: str, activities: tuple[ActivityEvidence, ...], as_of: date, performance: PerformanceSnapshot) -> SportTrainingSummary:
    selected = tuple(item for item in activities if item.sport == sport)
    weeks = {(as_of - item.local_date).days // 7 for item in selected}
    durations = [item.duration_seconds for item in selected]
    by_bucket = {name: sum(item.duration_seconds for item in selected if _bucket(as_of, item.local_date) == name) for name in ("RECENT", "MID", "OLDER")}
    recent = by_bucket["RECENT"]; mid = by_bucket["MID"]
    if not recent or not mid:
        trend = "insufficient_data"
    else:
        ratio = Decimal(recent) / Decimal(mid)
        trend = "increasing" if ratio > 1 + TREND_TOLERANCE else "decreasing" if ratio < 1 - TREND_TOLERANCE else "stable"
    coverage = _q(sum((item.coverage for item in selected), Decimal(0)) / len(selected)) if selected else Decimal(0)
    consistency = _q(Decimal(len(weeks)) / Decimal(12))
    long_tolerance = None
    if sport in {"running", "cycling"}:
        weekly = defaultdict(list)
        for item in selected: weekly[(as_of - item.local_date).days // 7].append(item)
        weekly_longs = [max(x.duration_seconds for x in values) for values in weekly.values()]
        long_cutoff = 75 * 60 if sport == "cycling" else 60 * 60
        long_rows = [item for item in selected if item.duration_seconds >= long_cutoff]
        long_tolerance = LongSessionTolerance(
            longest_duration_seconds=max(durations, default=None),
            longest_last_4w_seconds=max((item.duration_seconds for item in selected if (as_of-item.local_date).days < 28), default=None),
            median_weekly_longest_seconds=round(median(weekly_longs)) if weekly_longs else None,
            long_session_count=len(long_rows),
            days_since_last_long=min(((as_of-item.local_date).days for item in long_rows), default=None),
        )
    distances = [item.distance_m for item in selected if item.distance_m is not None]
    classifications = [_classify(item, sport, performance) for item in selected]
    classification_counts = {name: classifications.count(name) for name in ("recovery", "easy/endurance", "long", "tempo", "threshold", "interval/VO2", "unknown")}
    distribution = {
        "easy": sum(item.duration_seconds for item, kind in zip(selected, classifications) if kind in {"recovery", "easy/endurance", "long"}),
        "moderate": sum(item.duration_seconds for item, kind in zip(selected, classifications) if kind == "tempo"),
        "threshold": sum(item.duration_seconds for item, kind in zip(selected, classifications) if kind == "threshold"),
        "above_threshold": sum(item.duration_seconds for item, kind in zip(selected, classifications) if kind == "interval/VO2"),
    }
    quality_count = sum(kind in {"tempo", "threshold", "interval/VO2"} for kind in classifications)
    return SportTrainingSummary(
        sport=sport, activity_count=len(selected), weeks_active=len(weeks),
        sessions_per_week=_q(Decimal(len(selected))/12),
        minutes_per_week=_q(Decimal(sum(durations))/Decimal(60*12)),
        distance_per_week_m=_q(sum(distances, Decimal(0))/12) if sport != "strength" and distances else None,
        recent_4w_minutes=_q(Decimal(recent)/60), mid_4w_minutes=_q(Decimal(mid)/60), older_4w_minutes=_q(Decimal(by_bucket["OLDER"])/60),
        longest_session_duration_seconds=max(durations, default=None),
        longest_session_last_4w_seconds=max((item.duration_seconds for item in selected if (as_of-item.local_date).days < 28), default=None),
        median_session_duration_seconds=round(median(durations)) if durations else None,
        quality_session_count=quality_count,
        high_intensity_exposure_seconds=distribution["threshold"] + distribution["above_threshold"],
        session_classification_counts=classification_counts, intensity_distribution_seconds=distribution,
        consistency=consistency, trend=trend, training_summary_coverage=coverage,
        confidence=_context_confidence(len(selected), len(weeks), coverage), long_tolerance=long_tolerance,
    )


def _effort_value(lap: LapEvidence, sport: str) -> Decimal | None:
    if sport == "cycling":
        value = lap.average_power_w
        return _q(value) if value is not None and Decimal("20") <= value <= Decimal("2000") else None
    if lap.distance_m is None or lap.distance_m < 20 or lap.duration_seconds <= 0:
        return None
    if sport == "running":
        value = Decimal(lap.duration_seconds) * Decimal(1000) / lap.distance_m
        return _q(value) if Decimal("120") <= value <= Decimal("900") else None
    if sport == "swimming":
        if lap.elapsed_seconds and lap.moving_seconds is not None and Decimal(lap.moving_seconds) < Decimal(lap.elapsed_seconds) * SWIM_MIN_MOVING_TO_ELAPSED_RATIO:
            return None
        value = Decimal(lap.duration_seconds) * Decimal(100) / lap.distance_m
        return _q(value) if Decimal("45") <= value <= Decimal("300") else None
    return None


def _normalize_usable(points: list[CapabilityPoint], sport: str) -> tuple[CapabilityPoint, ...]:
    """Project raw representatives onto the sport's monotonic duration curve with weighted PAVA."""
    if sport not in {"running", "cycling"}:
        return tuple(points)
    blocks: list[dict] = []
    for index, point in enumerate(points):
        weight = Decimal(point.representative_support_count)
        blocks.append({"start": index, "end": index, "weight": weight, "total": point.representative_value * weight})
        while len(blocks) >= 2:
            left, right = blocks[-2], blocks[-1]
            left_value = left["total"] / left["weight"]
            right_value = right["total"] / right["weight"]
            violates = left_value > right_value if sport == "running" else left_value < right_value
            if not violates:
                break
            blocks[-2:] = [{"start": left["start"], "end": right["end"], "weight": left["weight"] + right["weight"], "total": left["total"] + right["total"]}]
    usable = [Decimal(0)] * len(points)
    for block in blocks:
        value = _q(block["total"] / block["weight"])
        for index in range(block["start"], block["end"] + 1):
            usable[index] = value
    return tuple(point.model_copy(update={"usable_representative_value": usable[index]}) for index, point in enumerate(points))


def _points(laps: tuple[LapEvidence, ...], sport: str, as_of: date) -> tuple[CapabilityPoint, ...]:
    targets = SWIM_DISTANCES if sport == "swimming" else BIKE_DURATIONS if sport == "cycling" else RUN_DURATIONS
    out = []
    for target_index, target in enumerate(targets):
        candidates = []
        for lap in laps:
            if lap.sport != sport or lap.coverage < Decimal("0.50"):
                continue
            if lap.lap_index >= 10000 and lap.lap_index != 10000 + target_index:
                continue
            actual = lap.distance_m if sport == "swimming" else Decimal(lap.duration_seconds)
            tolerance = Decimal("0.12") if sport == "swimming" else Decimal("0.35")
            if actual is None or abs(actual - Decimal(target)) > Decimal(target) * tolerance:
                continue
            value = _effort_value(lap, sport)
            if value is not None:
                candidates.append((value, lap))
        if not candidates:
            continue
        candidates.sort(key=lambda pair: pair[0], reverse=sport == "cycling")
        top = candidates[:min(4, len(candidates))]
        representative = _weighted_median(top, as_of)
        best, source = top[0]
        newest = max(lap.local_date for _, lap in candidates)
        avg_coverage = _q(sum((lap.coverage for _, lap in candidates), Decimal(0))/len(candidates))
        representative_sources = tuple(dict.fromkeys(lap.activity_id for _, lap in top))
        out.append(CapabilityPoint(
            duration_seconds=None if sport == "swimming" else target,
            distance_m=target if sport == "swimming" else None,
            best_value=best, representative_value=representative, usable_representative_value=representative,
            unit="watts" if sport == "cycling" else "seconds_per_100m" if sport == "swimming" else "seconds_per_km",
            representative_support_count=len(candidates), representative_latest_evidence_date=newest,
            representative_days_since_evidence=(as_of-newest).days,
            representative_confidence=_confidence(len(candidates), (as_of-newest).days, avg_coverage),
            representative_source_activity_ids=representative_sources, evidence_coverage=avg_coverage,
            best_source_activity_id=source.activity_id, best_source_date=source.local_date,
            best_source_lap_index=source.lap_index,
        ))
    return _normalize_usable(out, sport)


def _repeats(laps: tuple[LapEvidence, ...], sport: str, as_of: date) -> tuple[RepeatLikeEffort, ...]:
    grouped = defaultdict(list)
    for lap in laps:
        if lap.lap_index < 10000 and lap.sport == sport and lap.coverage >= Decimal("0.50") and _effort_value(lap, sport) is not None:
            grouped[lap.activity_id].append(lap)
    out = []
    for activity_id, activity_rows in grouped.items():
        rows = []
        candidates = []
        for seed in activity_rows:
            seed_value = _effort_value(seed, sport)
            cluster = []
            for row in activity_rows:
                value = _effort_value(row, sport)
                duration_close = abs(Decimal(row.duration_seconds - seed.duration_seconds)) <= Decimal(seed.duration_seconds) * REPEAT_CLUSTER_TOLERANCE
                distance_close = row.distance_m is not None and seed.distance_m is not None and abs(row.distance_m - seed.distance_m) <= seed.distance_m * REPEAT_CLUSTER_TOLERANCE
                shape_close = duration_close if sport == "cycling" else distance_close
                value_close = value is not None and seed_value is not None and abs(value - seed_value) <= seed_value * REPEAT_CLUSTER_TOLERANCE
                if shape_close and value_close:
                    cluster.append(row)
            if len(cluster) >= 3:
                signature = tuple(sorted(row.lap_index for row in cluster))
                if signature not in {item[0] for item in candidates}:
                    values = [_effort_value(row, sport) for row in cluster]
                    candidates.append((signature, cluster, _q(median(values))))
        if candidates:
            candidates.sort(key=lambda item: (-len(item[1]), -item[2] if sport == "cycling" else item[2], item[0]))
            rows = candidates[0][1]
        if len(rows) < 3:
            continue
        durations = [row.duration_seconds for row in rows]
        typical = Decimal(str(median(durations)))
        variation = _q((Decimal(max(durations))-Decimal(min(durations))) / typical) if typical else Decimal(1)
        distances = [row.distance_m for row in rows if row.distance_m is not None]
        if variation > REPEAT_CLUSTER_TOLERANCE or (distances and (max(distances)-min(distances))/Decimal(str(median(distances))) > REPEAT_CLUSTER_TOLERANCE):
            continue
        values = [_effort_value(row, sport) for row in rows]
        day = max(row.local_date for row in rows)
        out.append(RepeatLikeEffort(
            repeat_count=len(rows), typical_duration_seconds=round(typical),
            typical_distance_m=round(median(distances)) if distances else None,
            representative_value=_q(median(values)), unit="watts" if sport == "cycling" else "seconds_per_100m" if sport == "swimming" else "seconds_per_km",
            variation_ratio=variation, evidence_date=day, days_since_evidence=(as_of-day).days,
            confidence=_confidence(len(rows), (as_of-day).days, min(row.coverage for row in rows)), source_activity_id=activity_id,
        ))
    return tuple(sorted(out, key=lambda item: (item.days_since_evidence, str(item.source_activity_id))))


def _staleness(performance: PerformanceSnapshot, profiles: dict[str, SportCapabilityProfile]) -> tuple[ReferenceStalenessSignal, ...]:
    checks = (
        ("cycling_ftp_watts", performance.cycling_ftp_watts, "cycling", 1200, Decimal("1.08"), True),
        ("running_threshold_pace_seconds_per_km", performance.running_threshold_pace_seconds_per_km, "running", 1200, Decimal("0.95"), False),
        ("swimming_css_seconds_per_100m", performance.swimming_css_seconds_per_100m, "swimming", 400, Decimal("0.95"), False),
    )
    signals = []
    for name, reference, sport, target, factor, higher in checks:
        if reference is None:
            continue
        points = profiles[sport].distance_efforts if sport == "swimming" else profiles[sport].duration_efforts
        point = next((item for item in points if (item.distance_m if sport == "swimming" else item.duration_seconds) == target and item.representative_confidence in {CapabilityConfidence.HIGH, CapabilityConfidence.MEDIUM}), None)
        if point and ((point.usable_representative_value > Decimal(reference)*factor) if higher else (point.usable_representative_value < Decimal(reference)*factor)):
            signals.append(ReferenceStalenessSignal(reference_type=name, reference_value=Decimal(reference), evidence_value=point.usable_representative_value, evidence_date=point.representative_latest_evidence_date, confidence=point.representative_confidence, reason="recent_repeated_evidence_differs_materially_from_persisted_reference"))
    return tuple(signals)


def build_capability_context(*, athlete_id: UUID, as_of_date: date, activities: tuple[ActivityEvidence, ...], laps: tuple[LapEvidence, ...], performance: PerformanceSnapshot, training_status=None, relevant_future_sports=()) -> AthleteCapabilityContext:
    start, end = capability_window(as_of_date)
    activities = tuple(sorted((item for item in activities if start <= item.local_date <= end), key=lambda item: (item.local_date, str(item.activity_id))))
    laps = tuple(sorted((item for item in laps if start <= item.local_date <= end), key=lambda item: (item.local_date, str(item.activity_id), item.lap_index)))
    active_weeks = {(as_of_date-item.local_date).days//7 for item in activities}
    earliest = min((item.local_date for item in activities), default=None)
    available_days = min(CAPABILITY_WINDOW_DAYS, (as_of_date-earliest).days+1) if earliest else 0
    coverage = _q(Decimal(len(active_weeks))/12)
    profiles = {}
    for sport in ("running", "cycling", "swimming", "strength"):
        summary = _summary(sport, activities, as_of_date, performance)
        points = _points(laps, sport, as_of_date) if sport != "strength" else ()
        profiles[sport] = SportCapabilityProfile(summary=summary, duration_efforts=points if sport != "swimming" else (), distance_efforts=points if sport == "swimming" else (), repeat_like_efforts=_repeats(laps, sport, as_of_date) if sport != "strength" else ())
    overall = OverallTrainingSummary(
        activity_count=len(activities), weeks_with_training=len(active_weeks), total_minutes=_q(Decimal(sum(item.duration_seconds for item in activities))/60), consistency=coverage,
        training_status_date=getattr(training_status, "local_date", None), fitness=getattr(training_status, "fitness", None), fatigue=getattr(training_status, "fatigue", None), form=getattr(training_status, "form", None),
    )
    return AthleteCapabilityContext(
        athlete_profile_id=athlete_id, as_of_date=as_of_date, window_start=start, window_end=end,
        available_history_days=available_days, weeks_with_training=len(active_weeks), coverage_ratio=coverage,
        activity_count=len(activities), confidence=_context_confidence(len(activities), len(active_weeks), coverage),
        performance_references=performance, running=profiles["running"], cycling=profiles["cycling"], swimming=profiles["swimming"], strength=profiles["strength"],
        overall_training_summary=overall, reference_staleness_signals=_staleness(performance, profiles), relevant_future_sports=tuple(sorted(set(relevant_future_sports))),
    )
