from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.domains.planning.contracts import AdaptiveCapabilityPointSnapshot, AdaptiveCapabilitySnapshot
from app.domains.planning.models import WorkoutTarget, WorkoutTargetAdaptation
from app.domains.planning.session_planning import SessionPrescription, SessionType


ADAPTIVE_PRESCRIPTION_VERSION = "0.8G.2B"
CONFIDENCE_BLEND = {"HIGH": Decimal("0.90"), "MEDIUM": Decimal("0.40")}
PHASE_BLEND = {"PREPARATION": Decimal("0.45"), "BASE": Decimal("0.60"), "MAINTENANCE": Decimal("0.50"), "BUILD": Decimal("1.00"), "SPECIFIC": Decimal("1.00")}


def _interpolate(points: tuple[AdaptiveCapabilityPointSnapshot, ...], dimension: int):
    eligible = tuple(point for point in points if point.confidence in CONFIDENCE_BLEND)
    exact = next((point for point in eligible if point.dimension == dimension), None)
    if exact:
        return exact, exact.usable_value
    lower = max((point for point in eligible if point.dimension < dimension), key=lambda item: item.dimension, default=None)
    upper = min((point for point in eligible if point.dimension > dimension), key=lambda item: item.dimension, default=None)
    if lower is None or upper is None:
        return None
    fraction = Decimal(dimension - lower.dimension) / Decimal(upper.dimension - lower.dimension)
    value = lower.usable_value + (upper.usable_value - lower.usable_value) * fraction
    conservative = lower if lower.confidence == "MEDIUM" or lower.days_since_evidence > upper.days_since_evidence else upper
    return conservative, value


def _repeat_support(snapshot, sport, effort_seconds, effort_meters, evidence, capability_value):
    repeats = snapshot.running_repeats if sport == "running" else snapshot.swimming_repeats if sport == "swimming" else ()
    candidates = []
    for item in repeats:
        if item.confidence not in CONFIDENCE_BLEND:
            continue
        duration_close = effort_seconds and abs(item.typical_duration_seconds - effort_seconds) <= effort_seconds * Decimal("0.20")
        distance_close = effort_meters and item.typical_distance_m and abs(item.typical_distance_m - effort_meters) <= effort_meters * Decimal("0.20")
        if duration_close or distance_close:
            candidates.append(item)
    if not candidates:
        return capability_value, False, None
    item = sorted(candidates, key=lambda row: (-row.repeat_count, row.days_since_evidence, row.typical_duration_seconds))[0]
    overlap = item.source_activity_id is not None and item.source_activity_id in evidence.source_activity_ids
    if sport == "swimming":
        return capability_value, True, overlap
    return (capability_value + item.representative_value) / 2, True, overlap


def adapt_target(*, target: WorkoutTarget, snapshot: AdaptiveCapabilitySnapshot | None, session: SessionPrescription, family: str, effort_seconds: int | None = None, effort_meters: int | None = None, repeat_count: int = 1) -> WorkoutTarget:
    if snapshot is None or target.resolved_minimum is None or target.resolved_maximum is None:
        return target
    if session.phase.value in {"RECOVERY", "TAPER", "COMPETITION"}:
        return target
    eligible = (
        session.session_type is SessionType.RUN_INTERVAL or
        session.session_type is SessionType.BIKE_INTERVAL or
        session.session_type is SessionType.SWIM_INTERVAL or
        (session.discipline == "swimming" and family == "threshold")
    )
    if not eligible:
        return target
    dimension = effort_meters if session.discipline == "swimming" else effort_seconds
    if not dimension:
        return target
    points = snapshot.swimming_distance if session.discipline == "swimming" else snapshot.cycling_duration if session.discipline == "cycling" else snapshot.running_duration
    interpolated = _interpolate(points, dimension)
    if interpolated is None:
        return target
    evidence, capability_value = interpolated
    capability_value, repeat_used, repeat_overlap = _repeat_support(snapshot, session.discipline, effort_seconds, effort_meters, evidence, capability_value)
    reference_min = Decimal(str(target.resolved_minimum)); reference_max = Decimal(str(target.resolved_maximum))
    reference_center = (reference_min + reference_max) / 2
    faster = capability_value < reference_center if session.discipline == "running" else capability_value > reference_center
    if session.discipline != "swimming" and not faster:
        return target
    recency = Decimal("1.00") if evidence.days_since_evidence <= 27 else Decimal("0.75") if evidence.days_since_evidence <= 55 else Decimal("0.50")
    repetition = max(Decimal("0.60"), Decimal("1.00") - Decimal("0.05") * Decimal(max(0, repeat_count - 1)))
    blend = CONFIDENCE_BLEND[evidence.confidence] * recency * PHASE_BLEND.get(session.phase.value, Decimal("0")) * repetition
    if repeat_used and not repeat_overlap:
        blend = min(Decimal("1"), blend + Decimal("0.05"))
    if blend <= 0:
        return target
    if session.discipline == "cycling":
        capability_min, capability_max = capability_value * Decimal("0.92"), capability_value
    elif session.discipline == "swimming":
        confidence = CONFIDENCE_BLEND[evidence.confidence] * recency
        if repeat_used and not repeat_overlap:
            confidence = min(Decimal("1"), confidence + Decimal("0.05"))
        center = reference_center + (capability_value - reference_center) * confidence
        half_width = (reference_max - reference_min) / 2 * (Decimal("1") - Decimal("0.80") * confidence)
        center += capability_value * Decimal("0.02") * (Decimal("1") - repetition)
        final_min = max(center - half_width, capability_value * Decimal("0.98"))
        final_max = center + half_width
        blend = confidence
    else:
        capability_min, capability_max = capability_value * Decimal("0.98"), capability_value * Decimal("1.05")
    if session.discipline != "swimming":
        final_min = reference_min + (capability_min - reference_min) * blend
        final_max = reference_max + (capability_max - reference_max) * blend
    quantum = Decimal("1")
    final_min = final_min.quantize(quantum, rounding=ROUND_HALF_UP)
    final_max = final_max.quantize(quantum, rounding=ROUND_HALF_UP)
    adaptation = WorkoutTargetAdaptation(
        algorithm_version=ADAPTIVE_PRESCRIPTION_VERSION,
        reference_based_minimum=float(reference_min), reference_based_maximum=float(reference_max),
        capability_dimension=dimension, capability_value=float(capability_value), confidence=evidence.confidence,
        days_since_evidence=evidence.days_since_evidence, blend_factor=float(blend), repeat_factor=float(repetition),
        repeat_evidence_used=repeat_used, repeat_source_overlap=repeat_overlap,
        final_minimum=float(final_min), final_maximum=float(final_max),
    )
    return target.model_copy(update={"resolved_minimum": float(final_min), "resolved_maximum": float(final_max), "adaptation": adaptation})
