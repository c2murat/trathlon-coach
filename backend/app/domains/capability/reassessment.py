"""Read-only recommendations to remeasure references, never reference estimates."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domains.planning.contracts import FrozenModel, PerformanceSnapshot
from app.domains.planning.execution_adaptation import (
    AdaptationReasonCode, AdaptationSignalKind, ExecutionAdaptationContext,
    MIN_STRUCTURED_COMPARISONS, MIN_RECENT_STRUCTURED_COMPARISONS,
    RECENT_WINDOW_DAYS, build_execution_adaptation_context, interpret_signal,
)
from app.domains.planning.execution_evidence import (
    ComparisonConfidence, CompletionStatus, PrescribedCompletedEvidenceContext,
    TargetExecutionRelation,
)
from app.domains.planning.models import StructuredWorkoutDefinition

CAPABILITY_REASSESSMENT_VERSION = "0.8G.2C.7"
WINDOW_DAYS = 84
MIN_COMPARISONS = MIN_STRUCTURED_COMPARISONS
MIN_RECENT_COMPARISONS = MIN_RECENT_STRUCTURED_COMPARISONS
MIN_HIGH_CONFIDENCE_COMPARISONS = 5
MIN_HIGH_CONFIDENCE_RECENT = 3
MIN_HIGH_QUALITY_COMPARISONS = 4
MAX_MEDIUM_FOR_HIGH_CONFIDENCE = 1
ELIGIBLE_CONFIDENCE = frozenset((ComparisonConfidence.HIGH, ComparisonConfidence.MEDIUM))


class CapabilityKind(StrEnum):
    CYCLING_FTP = "CYCLING_FTP"
    RUNNING_THRESHOLD_PACE = "RUNNING_THRESHOLD_PACE"
    SWIMMING_CSS = "SWIMMING_CSS"


class ReassessmentStatus(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NO_REASSESSMENT_NEEDED = "NO_REASSESSMENT_NEEDED"
    REASSESSMENT_CANDIDATE = "REASSESSMENT_CANDIDATE"
    INCONSISTENT_EVIDENCE = "INCONSISTENT_EVIDENCE"
    REFERENCE_UNAVAILABLE = "REFERENCE_UNAVAILABLE"


class ReassessmentConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class ReassessmentReason(StrEnum):
    REPEATED_ABOVE_ANCHORED_TARGET = "REPEATED_ABOVE_ANCHORED_TARGET"
    REPEATED_FASTER_THAN_ANCHORED_TARGET = "REPEATED_FASTER_THAN_ANCHORED_TARGET"
    RECENT_EVIDENCE_SUFFICIENT = "RECENT_EVIDENCE_SUFFICIENT"
    REFERENCE_MISSING = "REFERENCE_MISSING"
    RECENT_PARTIALS_PRESENT = "RECENT_PARTIALS_PRESENT"
    EXTREME_OVERSHOOT_PRESENT = "EXTREME_OVERSHOOT_PRESENT"
    EVIDENCE_CONTRADICTORY = "EVIDENCE_CONTRADICTORY"
    STRUCTURED_EVIDENCE_INSUFFICIENT = "STRUCTURED_EVIDENCE_INSUFFICIENT"
    RECENT_EVIDENCE_INSUFFICIENT = "RECENT_EVIDENCE_INSUFFICIENT"
    TARGET_NOT_CAPABILITY_ANCHORED = "TARGET_NOT_CAPABILITY_ANCHORED"
    UNKNOWN_MAJORITY = "UNKNOWN_MAJORITY"
    UNMATCHED_MAJORITY = "UNMATCHED_MAJORITY"
    INDEPENDENT_ACTIVITIES_INSUFFICIENT = "INDEPENDENT_ACTIVITIES_INSUFFICIENT"
    NO_REPEATED_REASSESSMENT_SIGNAL = "NO_REPEATED_REASSESSMENT_SIGNAL"


# Audited production session families. No easy/endurance/drill/strength aliases.
SEMANTICS = (
    (CapabilityKind.CYCLING_FTP, "cycling", "FTP", "power", "watts",
     "cycling_ftp_watts", frozenset(("BIKE_TEMPO", "BIKE_THRESHOLD", "BIKE_INTERVAL"))),
    (CapabilityKind.RUNNING_THRESHOLD_PACE, "running", "threshold_pace", "pace", "seconds_per_km",
     "running_threshold_pace_seconds_per_km", frozenset(("RUN_TEMPO", "RUN_THRESHOLD", "RUN_INTERVAL"))),
    (CapabilityKind.SWIMMING_CSS, "swimming", "CSS", "swim_pace", "seconds_per_100m",
     "swimming_css_seconds_per_100m", frozenset(("SWIM_THRESHOLD", "SWIM_INTERVAL"))),
)


class ReassessmentReferences(FrozenModel):
    athlete_profile_id: UUID
    as_of_date: date
    performance: PerformanceSnapshot


class CapabilityTargetSnapshot(FrozenModel):
    athlete_profile_id: UUID
    planned_session_id: UUID
    planned_date: date
    sport: str
    session_type: str
    reference: str
    reference_value: Decimal
    metric: str
    unit: str
    minimum: Decimal
    maximum: Decimal
    repetitions: int


def snapshot_capability_target(*, athlete_profile_id: UUID, planned_session_id: UUID,
                               planned_date: date, sport: str, session_type: str,
                               workout: StructuredWorkoutDefinition | None) -> CapabilityTargetSnapshot | None:
    """Copy provenance of C.1's first repeated work target; never resolve a target."""
    if workout is None or workout.sport != sport:
        return None
    for block in workout.steps:
        if block.kind != "repeat":
            continue
        work = next((step for step in block.steps or () if step.phase == "work" and step.target), None)
        if work is None or work.target is None or work.duration is None:
            continue
        target = work.target
        # Preserve C.1 _work_spec's block selection before checking provenance.
        low = target.resolved_minimum if target.resolved_minimum is not None else target.minimum
        high = target.resolved_maximum if target.resolved_maximum is not None else target.maximum
        unit = target.resolved_unit or target.reference_unit
        if low is None or high is None or unit not in {"watts", "seconds_per_km", "seconds_per_100m"}:
            continue
        if (target.mode != "percent_reference" or target.reference is None
                or target.reference_value is None or target.resolved_unit is None
                or target.resolved_minimum is None or target.resolved_maximum is None
                or target.adaptation is not None or target.planning_adaptation is not None):
            return None
        return CapabilityTargetSnapshot(
            athlete_profile_id=athlete_profile_id, planned_session_id=planned_session_id,
            planned_date=planned_date, sport=sport, session_type=session_type,
            reference=target.reference, reference_value=Decimal(str(target.reference_value)),
            metric=target.metric, unit=target.resolved_unit,
            minimum=Decimal(str(target.resolved_minimum)), maximum=Decimal(str(target.resolved_maximum)),
            repetitions=block.repetitions,
        )
    return None


class CurrentCapabilityReference(FrozenModel):
    value: Decimal
    unit: str
    profile_version_id: UUID | None = None
    effective_from: datetime | None = None
    age_days: int | None = None
    source: str | None = None
    quality: str | None = None
    algorithm_version: str | None = None


class ReassessmentEvidenceCounts(FrozenModel):
    quality_sessions: int
    anchored_comparisons: int
    eligible_comparisons: int
    recent: int
    background: int
    contradicting: int
    recent_partials: int
    unknown: int
    unmatched: int
    excluded_unanchored: int
    excluded_activity_provenance: int
    high: int
    medium: int


class CapabilityReassessmentCandidate(FrozenModel):
    sport: str
    capability_kind: CapabilityKind
    current_reference: CurrentCapabilityReference | None
    status: ReassessmentStatus
    confidence: ReassessmentConfidence
    reason_codes: tuple[ReassessmentReason, ...]
    supporting_session_types: tuple[str, ...]
    supporting_session_ids: tuple[UUID, ...]
    evidence: ReassessmentEvidenceCounts
    c2_reason_codes: tuple[AdaptationReasonCode, ...]


class ReassessmentSummary(FrozenModel):
    session_count: int
    candidate_count: int
    insufficient_count: int
    inconsistent_count: int
    unavailable_count: int


class CapabilityReassessmentContext(FrozenModel):
    athlete_profile_id: UUID
    as_of_date: date
    window_start_date: date
    algorithm_version: str = CAPABILITY_REASSESSMENT_VERSION
    candidates: tuple[CapabilityReassessmentCandidate, ...]
    summary: ReassessmentSummary


def build_capability_reassessment_context(*, athlete_profile_id: UUID, as_of_date: date,
        evidence: PrescribedCompletedEvidenceContext, references: ReassessmentReferences,
        adaptation: ExecutionAdaptationContext | None = None,
        targets: tuple[CapabilityTargetSnapshot, ...] = ()) -> CapabilityReassessmentContext:
    start = as_of_date - timedelta(days=WINDOW_DAYS)
    for item in (evidence, references, adaptation):
        if item is not None and (item.athlete_profile_id != athlete_profile_id or item.as_of_date != as_of_date):
            raise ValueError("capability reassessment athlete/cutoff mismatch")
    if evidence.window_start_date != start or (adaptation and adaptation.window_start_date != start):
        raise ValueError("capability reassessment window mismatch")
    if any(item.athlete_profile_id != athlete_profile_id for item in targets):
        raise ValueError("capability target athlete mismatch")
    if len({item.planned_session_id for item in evidence.sessions}) != len(evidence.sessions):
        raise ValueError("duplicate evidence session")
    if len({item.planned_session_id for item in targets}) != len(targets):
        raise ValueError("duplicate target snapshot")
    # Supplied C.2 must describe these exact facts, not a stale or unrelated context.
    derived = build_execution_adaptation_context(evidence)
    if adaptation is not None and adaptation != derived:
        raise ValueError("C.2 interpretation does not match C.1 evidence")
    rows = tuple(sorted((item for item in evidence.sessions if start <= item.planned_date < as_of_date),
                        key=lambda item: str(item.planned_session_id)))
    anchors = {item.planned_session_id: item for item in targets}
    performance = references.performance
    candidates = []
    for kind, sport, reference_name, metric, unit, field, types in SEMANTICS:
        value = getattr(performance, field)
        effective = performance.effective_from
        valid = value is not None and value.is_finite() and value > 0 and (
            effective is None or effective.date() < as_of_date)
        reference = CurrentCapabilityReference(
            value=value, unit=unit, profile_version_id=performance.profile_version_id,
            effective_from=effective, age_days=(as_of_date - effective.date()).days if effective else None,
            source=performance.source, algorithm_version=performance.algorithm_version,
        ) if valid else None
        quality = tuple(item for item in rows if item.sport == sport and item.session_type in types)
        anchored = []
        for item in quality:
            target = item.target_comparison
            anchor = anchors.get(item.planned_session_id)
            if (reference and target and anchor and anchor.sport == sport
                    and anchor.session_type == item.session_type and anchor.planned_date == item.planned_date
                    and anchor.reference == reference_name and anchor.reference_value == value
                    and anchor.metric == metric and anchor.unit == target.unit == unit
                    and anchor.minimum == target.planned_target_min and anchor.maximum == target.planned_target_max
                    and anchor.repetitions == target.planned_repetitions
                    and (effective is None or item.planned_date >= effective.date())):
                anchored.append(item)
        eligible = tuple(item for item in anchored if item.sport_match is True
                         and (as_of_date - item.planned_date).days < WINDOW_DAYS
                         and item.comparison_confidence in ELIGIBLE_CONFIDENCE
                         and item.target_comparison.confidence in ELIGIBLE_CONFIDENCE
                         and item.completion_status in (CompletionStatus.COMPLETED, CompletionStatus.PARTIAL, CompletionStatus.OVER_DURATION)
                         and item.target_comparison.execution_relation != TargetExecutionRelation.UNKNOWN)
        uses = Counter(activity for item in eligible for activity in set(item.source_activity_ids))
        independent = tuple(item for item in eligible if item.source_activity_ids
                            and all(uses[activity] == 1 for activity in item.source_activity_ids))
        recent = tuple(item for item in independent if (as_of_date - item.planned_date).days < RECENT_WINDOW_DAYS)
        partials = sum(item.completion_status == CompletionStatus.PARTIAL or (
            item.target_comparison is not None and item.target_comparison.matched_repetitions < item.target_comparison.planned_repetitions)
            for item in quality if (as_of_date - item.planned_date).days < RECENT_WINDOW_DAYS)
        unmatched = sum(item.completion_status == CompletionStatus.UNMATCHED for item in quality)
        unknown = sum(item.completion_status != CompletionStatus.UNMATCHED and (
            item not in eligible) for item in quality)
        negative = {TargetExecutionRelation.BELOW_POWER_TARGET, TargetExecutionRelation.SLOWER_THAN_TARGET, TargetExecutionRelation.MIXED}
        contradicting = sum(item.target_comparison.execution_relation in negative for item in independent)
        signal = interpret_signal(independent, as_of_date=as_of_date, sport=sport)
        reasons = set()
        if len(anchored) < len(quality):
            reasons.add(ReassessmentReason.TARGET_NOT_CAPABILITY_ANCHORED)
        if len(independent) < len(eligible):
            reasons.add(ReassessmentReason.INDEPENDENT_ACTIVITIES_INSUFFICIENT)
        if partials:
            reasons.add(ReassessmentReason.RECENT_PARTIALS_PRESENT)
        if unknown * 2 > len(quality):
            reasons.add(ReassessmentReason.UNKNOWN_MAJORITY)
        if unmatched * 2 > len(quality):
            reasons.add(ReassessmentReason.UNMATCHED_MAJORITY)
        if len(independent) < MIN_COMPARISONS:
            reasons.add(ReassessmentReason.STRUCTURED_EVIDENCE_INSUFFICIENT)
        if len(recent) < MIN_RECENT_COMPARISONS:
            reasons.add(ReassessmentReason.RECENT_EVIDENCE_INSUFFICIENT)
        status = ReassessmentStatus.INSUFFICIENT_EVIDENCE
        confidence = ReassessmentConfidence.INSUFFICIENT
        if reference is None:
            status = ReassessmentStatus.REFERENCE_UNAVAILABLE
            reasons.add(ReassessmentReason.REFERENCE_MISSING)
        elif (len(independent) >= MIN_COMPARISONS and len(recent) >= MIN_RECENT_COMPARISONS
              and unknown * 2 <= len(quality) and unmatched * 2 <= len(quality)):
            if AdaptationReasonCode.EXTREME_OVERSHOOT_PRESENT in signal.reason_codes:
                reasons.add(ReassessmentReason.EXTREME_OVERSHOOT_PRESENT)
            if contradicting or signal.signal in (AdaptationSignalKind.INCONSISTENT_EXECUTION, AdaptationSignalKind.REGRESSION_CANDIDATE):
                status = ReassessmentStatus.INCONSISTENT_EVIDENCE
                confidence = ReassessmentConfidence.LOW
                reasons.add(ReassessmentReason.EVIDENCE_CONTRADICTORY)
            elif not partials:
                if signal.signal == AdaptationSignalKind.PROGRESSION_CANDIDATE:
                    status = ReassessmentStatus.REASSESSMENT_CANDIDATE
                    high = sum(item.comparison_confidence == ComparisonConfidence.HIGH
                               and item.target_comparison.confidence == ComparisonConfidence.HIGH for item in independent)
                    confidence = (ReassessmentConfidence.HIGH if len(independent) >= MIN_HIGH_CONFIDENCE_COMPARISONS
                                  and len(recent) >= MIN_HIGH_CONFIDENCE_RECENT
                                  and high >= MIN_HIGH_QUALITY_COMPARISONS
                                  and len(independent)-high <= MAX_MEDIUM_FOR_HIGH_CONFIDENCE
                                  else ReassessmentConfidence.MEDIUM)
                    reasons.update((ReassessmentReason.RECENT_EVIDENCE_SUFFICIENT,
                        ReassessmentReason.REPEATED_ABOVE_ANCHORED_TARGET if sport == "cycling"
                        else ReassessmentReason.REPEATED_FASTER_THAN_ANCHORED_TARGET))
                else:
                    status = ReassessmentStatus.NO_REASSESSMENT_NEEDED
                    reasons.add(ReassessmentReason.NO_REPEATED_REASSESSMENT_SIGNAL)
        candidates.append(CapabilityReassessmentCandidate(
            sport=sport, capability_kind=kind, current_reference=reference, status=status, confidence=confidence,
            reason_codes=tuple(sorted(reasons)),
            supporting_session_types=tuple(sorted({item.session_type for item in independent})),
            supporting_session_ids=tuple(sorted((item.planned_session_id for item in independent), key=str)),
            evidence=ReassessmentEvidenceCounts(quality_sessions=len(quality), anchored_comparisons=len(anchored),
                eligible_comparisons=len(independent), recent=len(recent), background=len(independent)-len(recent),
                contradicting=contradicting, recent_partials=partials, unknown=unknown, unmatched=unmatched,
                excluded_unanchored=len(quality)-len(anchored), excluded_activity_provenance=len(eligible)-len(independent),
                high=sum(item.comparison_confidence == ComparisonConfidence.HIGH and item.target_comparison.confidence == ComparisonConfidence.HIGH for item in independent),
                medium=sum(item.comparison_confidence == ComparisonConfidence.MEDIUM or item.target_comparison.confidence == ComparisonConfidence.MEDIUM for item in independent)),
            c2_reason_codes=tuple(sorted(signal.reason_codes)),
        ))
    statuses = Counter(item.status for item in candidates)
    return CapabilityReassessmentContext(athlete_profile_id=athlete_profile_id, as_of_date=as_of_date,
        window_start_date=start, candidates=tuple(candidates), summary=ReassessmentSummary(
            session_count=len(rows), candidate_count=statuses[ReassessmentStatus.REASSESSMENT_CANDIDATE],
            insufficient_count=statuses[ReassessmentStatus.INSUFFICIENT_EVIDENCE],
            inconsistent_count=statuses[ReassessmentStatus.INCONSISTENT_EVIDENCE],
            unavailable_count=statuses[ReassessmentStatus.REFERENCE_UNAVAILABLE]))
