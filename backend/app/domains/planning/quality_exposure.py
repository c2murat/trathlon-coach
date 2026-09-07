from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median

from app.domains.capability.analysis import LapEvidence, effort_value
from app.domains.planning.contracts import PerformanceSnapshot, QualityExposureSignal, QualityExposureSnapshot


QUALITY_SELECTION_VERSION = "0.8G.2B.3.2"
RECENCY_WEIGHTS = ((27, Decimal("1.00")), (55, Decimal("0.60")), (83, Decimal("0.30")))

SESSION_STIMULUS = {
    "RUN_TEMPO": ("running", "TEMPO"), "RUN_THRESHOLD": ("running", "THRESHOLD"),
    "RUN_INTERVAL": ("running", "INTERVAL"), "BIKE_TEMPO": ("cycling", "TEMPO"),
    "BIKE_THRESHOLD": ("cycling", "THRESHOLD"), "BIKE_INTERVAL": ("cycling", "INTERVAL"),
    "SWIM_TECHNIQUE": ("swimming", "TECHNIQUE"), "SWIM_AEROBIC": ("swimming", "AEROBIC"),
    "SWIM_THRESHOLD": ("swimming", "THRESHOLD"), "SWIM_INTERVAL": ("swimming", "INTERVAL"),
}


@dataclass(frozen=True)
class QualityExposureEvidence:
    activity_id: object
    local_date: date
    discipline: str
    stimulus: str
    confidence: str


@dataclass(frozen=True)
class StructuredExposureClassification:
    stimulus: str
    structure: str
    relative_intensity: Decimal
    rule: str


def _homogeneous(rows, sport: str, *, minimum: int, require_recovery: bool = False, recovery_rows=()):
    candidates = []
    for seed in rows:
        seed_value = effort_value(seed, sport)
        cluster = []
        for row in rows:
            value = effort_value(row, sport)
            duration_close = abs(Decimal(row.duration_seconds - seed.duration_seconds)) <= Decimal(seed.duration_seconds) * Decimal("0.12")
            distance_close = row.distance_m is not None and seed.distance_m is not None and abs(row.distance_m - seed.distance_m) <= seed.distance_m * Decimal("0.12")
            shape_close = duration_close if sport == "cycling" else distance_close
            value_close = value is not None and seed_value is not None and abs(value - seed_value) <= seed_value * Decimal("0.12")
            if shape_close and value_close:
                cluster.append(row)
        cluster.sort(key=lambda item: item.lap_index)
        recovery_indices = {row.lap_index for row in recovery_rows}
        separated = all(any(left.lap_index < index < right.lap_index for index in recovery_indices) for left, right in zip(cluster, cluster[1:]))
        if len(cluster) >= minimum and (not require_recovery or separated):
            candidates.append(tuple(cluster))
    return min(candidates, key=lambda group: (-len(group), tuple(item.lap_index for item in group))) if candidates else ()


def classify_structured_activity(*, discipline: str, laps, performance: PerformanceSnapshot):
    """Classify observed work structure; activity averages and capability are excluded."""
    reference = (
        performance.running_threshold_pace_seconds_per_km if discipline == "running" else
        performance.cycling_ftp_watts if discipline == "cycling" else
        performance.swimming_css_seconds_per_100m if discipline == "swimming" else None
    )
    if reference is None or reference <= 0:
        return None
    valid = tuple(row for row in laps if row.sport == discipline and row.lap_index < 10000 and row.coverage >= Decimal("0.50") and effort_value(row, discipline) is not None)
    if not valid:
        return None

    def ratio(row):
        return effort_value(row, discipline) / Decimal(reference)

    def result(rows, stimulus, rule):
        typical_duration = round(median(row.duration_seconds for row in rows))
        distances = [row.distance_m for row in rows if row.distance_m is not None]
        typical_distance = round(median(distances)) if distances else None
        structure = f"{len(rows)} bouts x ~{typical_duration}s" + (f" / ~{typical_distance}m" if typical_distance else "")
        relative = Decimal(str(median([ratio(row) for row in rows]))).quantize(Decimal("0.01"))
        return StructuredExposureClassification(stimulus, structure, relative, rule)

    if discipline == "running":
        recovery = tuple(row for row in valid if ratio(row) > Decimal("1.12"))
        rows = _homogeneous(tuple(row for row in valid if 20 <= row.duration_seconds <= 300 and ratio(row) <= Decimal("0.96")), discipline, minimum=3, require_recovery=True, recovery_rows=recovery)
        if rows: return result(rows, "INTERVAL", "homogeneous 20-300s fast bouts with interleaved recoveries at <=0.96 threshold-pace ratio")
        rows = _homogeneous(tuple(row for row in valid if row.duration_seconds >= 180 and Decimal("0.97") <= ratio(row) <= Decimal("1.03")), discipline, minimum=2, require_recovery=True, recovery_rows=recovery)
        if rows: return result(rows, "THRESHOLD", "repeated >=180s bouts with recoveries at 0.97-1.03 threshold-pace ratio")
        rows = _homogeneous(tuple(row for row in valid if row.duration_seconds >= 300 and Decimal("1.03") < ratio(row) <= Decimal("1.12")), discipline, minimum=2, require_recovery=True, recovery_rows=recovery)
        if rows: return result(rows, "TEMPO", "repeated >=300s bouts with recoveries at 1.03-1.12 threshold-pace ratio")
    elif discipline == "cycling":
        recovery = tuple(row for row in valid if ratio(row) < Decimal("0.76"))
        rows = _homogeneous(tuple(row for row in valid if 20 <= row.duration_seconds <= 300 and ratio(row) >= Decimal("1.05")), discipline, minimum=3, require_recovery=True, recovery_rows=recovery)
        if rows: return result(rows, "INTERVAL", "homogeneous 20-300s power bouts with interleaved recoveries at >=1.05 FTP")
        rows = _homogeneous(tuple(row for row in valid if row.duration_seconds >= 300 and Decimal("0.95") <= ratio(row) <= Decimal("1.05")), discipline, minimum=2, require_recovery=True, recovery_rows=recovery)
        if rows: return result(rows, "THRESHOLD", "repeated >=300s power bouts with recoveries at 0.95-1.05 FTP")
        rows = _homogeneous(tuple(row for row in valid if row.duration_seconds >= 480 and Decimal("0.80") <= ratio(row) < Decimal("0.95")), discipline, minimum=2, require_recovery=True, recovery_rows=recovery)
        if rows: return result(rows, "SWEET_SPOT", "repeated >=480s power bouts with recoveries at 0.80-0.95 FTP")
    elif discipline == "swimming":
        coherent = tuple(row for row in valid if not row.elapsed_seconds or row.moving_seconds is None or Decimal(row.moving_seconds) >= Decimal(row.elapsed_seconds) * Decimal("0.75"))
        recovery = tuple(row for row in coherent if ratio(row) > Decimal("1.08"))
        rows = _homogeneous(tuple(row for row in coherent if ratio(row) < Decimal("0.97")), discipline, minimum=3, require_recovery=True, recovery_rows=recovery)
        if rows: return result(rows, "INTERVAL", "repeated fast swim bouts with explicit recovery separation below 0.97 CSS-pace ratio")
        rows = _homogeneous(tuple(row for row in coherent if Decimal("0.97") <= ratio(row) <= Decimal("1.03")), discipline, minimum=3)
        if rows: return result(rows, "THRESHOLD", "homogeneous repeated swim set at 0.97-1.03 CSS-pace ratio")
        rows = _homogeneous(tuple(row for row in coherent if Decimal("1.03") < ratio(row) <= Decimal("1.25")), discipline, minimum=3)
        if rows: return result(rows, "AEROBIC", "homogeneous repeated swim set at 1.03-1.25 CSS-pace ratio")
    return None


def recency_weight(days: int) -> Decimal:
    return next((weight for maximum, weight in RECENCY_WEIGHTS if days <= maximum), Decimal("0"))


def build_quality_exposure_snapshot(*, cutoff_date: date, evidence) -> QualityExposureSnapshot:
    grouped = defaultdict(list)
    for item in evidence:
        days = (cutoff_date - item.local_date).days
        if 0 <= days <= 83:
            grouped[(item.discipline, item.stimulus)].append((days, item.confidence))
    signals = []
    for (discipline, stimulus), rows in sorted(grouped.items()):
        signals.append(QualityExposureSignal(
            discipline=discipline, stimulus=stimulus,
            weighted_exposure=sum((recency_weight(days) for days, _ in rows), Decimal("0")),
            count_0_27d=sum(days <= 27 for days, _ in rows),
            count_28_55d=sum(28 <= days <= 55 for days, _ in rows),
            count_56_83d=sum(56 <= days <= 83 for days, _ in rows),
            days_since_last=min(days for days, _ in rows),
            confidence="HIGH" if any(confidence == "HIGH" for _, confidence in rows) else "MEDIUM",
        ))
    return QualityExposureSnapshot(
        algorithm_version=QUALITY_SELECTION_VERSION, cutoff_date=cutoff_date, signals=tuple(signals),
    )


def classify_unlinked(*, discipline: str, effective_intensity: float | None):
    if effective_intensity is None or discipline not in {"running", "cycling"}:
        return None
    value = Decimal(str(effective_intensity))
    if value >= Decimal("1.05"): return "INTERVAL"
    if value >= Decimal("0.95"): return "THRESHOLD"
    if discipline == "cycling" and value >= Decimal("0.88"): return "SWEET_SPOT"
    if value >= Decimal("0.80"): return "TEMPO"
    return None
