from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from statistics import median
from typing import Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.planning.execution_evidence import (
    ComparisonConfidence, CompletionStatus, PrescribedCompletedEvidenceContext,
    SessionExecutionEvidence, TargetExecutionRelation,
)


EXECUTION_ADAPTATION_VERSION = "0.8G.2C.2"
MIN_EVALUABLE_SESSIONS = 3
MIN_STRUCTURED_COMPARISONS = 3
MIN_RECENT_STRUCTURED_COMPARISONS = 2
RECENT_WINDOW_DAYS = 28
MAX_UNKNOWN_FRACTION = Decimal("0.50")
DIRECTIONAL_FRACTION = Decimal("0.67")
MAX_PROGRESSION_PARTIAL_FRACTION = Decimal("0.20")
EXTREME_POWER_FACTOR = Decimal("1.15")
EXTREME_PACE_FACTOR = Decimal("0.90")


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AdaptationSignalKind(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MAINTAIN = "MAINTAIN"
    PROGRESSION_CANDIDATE = "PROGRESSION_CANDIDATE"
    REGRESSION_CANDIDATE = "REGRESSION_CANDIDATE"
    INCONSISTENT_EXECUTION = "INCONSISTENT_EXECUTION"


class AdaptationSignalConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class AdaptationReasonCode(StrEnum):
    NO_EVIDENCE = "NO_EVIDENCE"
    BELOW_MINIMUM_EVALUABLE_SESSIONS = "BELOW_MINIMUM_EVALUABLE_SESSIONS"
    BELOW_MINIMUM_STRUCTURED_COMPARISONS = "BELOW_MINIMUM_STRUCTURED_COMPARISONS"
    BELOW_MINIMUM_RECENT_EVIDENCE = "BELOW_MINIMUM_RECENT_EVIDENCE"
    UNMATCHED_MAJORITY = "UNMATCHED_MAJORITY"
    UNKNOWN_MAJORITY = "UNKNOWN_MAJORITY"
    STRENGTH_INTENSITY_NOT_OBSERVED = "STRENGTH_INTENSITY_NOT_OBSERVED"
    CONSISTENT_DURATION_EXECUTION = "CONSISTENT_DURATION_EXECUTION"
    CONSISTENT_WITHIN_TARGET = "CONSISTENT_WITHIN_TARGET"
    REPEATED_ABOVE_OR_FASTER = "REPEATED_ABOVE_OR_FASTER"
    REPEATED_BELOW_OR_SLOWER = "REPEATED_BELOW_OR_SLOWER"
    REPEATED_PARTIAL_EXECUTION = "REPEATED_PARTIAL_EXECUTION"
    RECENT_EVIDENCE_CONSISTENT = "RECENT_EVIDENCE_CONSISTENT"
    RECENT_DETERIORATION = "RECENT_DETERIORATION"
    CONTRADICTORY_TARGET_DIRECTIONS = "CONTRADICTORY_TARGET_DIRECTIONS"
    EXTREME_OVERSHOOT_PRESENT = "EXTREME_OVERSHOOT_PRESENT"
    MIXED_WITHOUT_DIRECTION = "MIXED_WITHOUT_DIRECTION"


class AdaptationMetrics(FrozenModel):
    session_count: int
    evaluable_sessions: int
    unmatched_sessions: int
    duration_comparisons: int
    duration_completed: int
    partial_sessions: int
    median_duration_ratio: Decimal | None = None
    structured_comparisons: int
    eligible_structured_comparisons: int
    within_target: int
    above_or_faster: int
    below_or_slower: int
    mixed: int
    unknown_target: int
    recent_sessions: int
    background_sessions: int
    recent_structured_comparisons: int
    background_structured_comparisons: int
    recent_within_target: int
    recent_above_or_faster: int
    recent_below_or_slower: int
    recent_partial: int
    evidence_confidence_high: int
    evidence_confidence_medium: int
    evidence_confidence_low: int
    evidence_confidence_insufficient: int


class AdaptationSignal(FrozenModel):
    sport: str | None = None
    session_type: str | None = None
    target_kind: str | None = None
    signal: AdaptationSignalKind
    confidence: AdaptationSignalConfidence
    evidence_count: int
    supporting_metrics: AdaptationMetrics
    reason_codes: tuple[AdaptationReasonCode, ...]
    supporting_session_ids: tuple[UUID, ...] = ()


class ExecutionAdaptationContext(FrozenModel):
    athlete_profile_id: UUID
    as_of_date: date
    window_start_date: date
    algorithm_version: str = EXECUTION_ADAPTATION_VERSION
    global_summary: AdaptationMetrics
    global_signal: AdaptationSignal
    sport_signals: tuple[AdaptationSignal, ...] = ()
    session_type_signals: tuple[AdaptationSignal, ...] = ()
    structured_target_signals: tuple[AdaptationSignal, ...] = ()


POSITIVE_RELATIONS = {
    TargetExecutionRelation.FASTER_THAN_TARGET,
    TargetExecutionRelation.ABOVE_POWER_TARGET,
}
NEGATIVE_RELATIONS = {
    TargetExecutionRelation.SLOWER_THAN_TARGET,
    TargetExecutionRelation.BELOW_POWER_TARGET,
}
ELIGIBLE_CONFIDENCE = {ComparisonConfidence.HIGH, ComparisonConfidence.MEDIUM}


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _target_kind(item: SessionExecutionEvidence) -> str | None:
    target = item.target_comparison
    if target is None:
        return None
    return {
        "watts": "POWER",
        "seconds_per_km": "RUN_PACE",
        "seconds_per_100m": "SWIM_PACE",
    }.get(target.unit, target.unit.upper())


def _is_evaluable(item: SessionExecutionEvidence) -> bool:
    return (
        item.sport_match is True
        and item.comparison_confidence in ELIGIBLE_CONFIDENCE
        and item.completion_status in {CompletionStatus.PARTIAL, CompletionStatus.COMPLETED, CompletionStatus.OVER_DURATION}
    )


def _is_partial(item: SessionExecutionEvidence) -> bool:
    target = item.target_comparison
    return item.completion_status == CompletionStatus.PARTIAL or (
        target is not None and target.matched_repetitions < target.planned_repetitions
    )


def _is_extreme_overshoot(item: SessionExecutionEvidence) -> bool:
    target = item.target_comparison
    if target is None or target.execution_relation not in POSITIVE_RELATIONS:
        return False
    if target.unit == "watts":
        return target.actual_representative_value > target.planned_target_max * EXTREME_POWER_FACTOR
    return target.actual_representative_value < target.planned_target_min * EXTREME_PACE_FACTOR


def adaptation_metrics(sessions: Iterable[SessionExecutionEvidence], *, as_of_date: date) -> AdaptationMetrics:
    rows = tuple(sessions)
    evaluable = tuple(item for item in rows if _is_evaluable(item))
    structured = tuple(item for item in evaluable if item.target_comparison is not None)
    eligible = tuple(item for item in structured if item.target_comparison.confidence in ELIGIBLE_CONFIDENCE)
    recent = tuple(item for item in rows if 0 <= (as_of_date - item.planned_date).days < RECENT_WINDOW_DAYS)
    background = tuple(item for item in rows if RECENT_WINDOW_DAYS <= (as_of_date - item.planned_date).days < 84)
    recent_targets = tuple(item for item in eligible if item in recent)
    background_targets = tuple(item for item in eligible if item in background)
    relation = lambda item: item.target_comparison.execution_relation
    ratios = [item.duration_ratio for item in evaluable if item.duration_ratio is not None]
    confidence = [item.comparison_confidence for item in rows]
    return AdaptationMetrics(
        session_count=len(rows), evaluable_sessions=len(evaluable),
        unmatched_sessions=sum(item.completion_status == CompletionStatus.UNMATCHED for item in rows),
        duration_comparisons=len(ratios),
        duration_completed=sum(item.completion_status in {CompletionStatus.COMPLETED, CompletionStatus.OVER_DURATION} for item in evaluable),
        partial_sessions=sum(_is_partial(item) for item in evaluable),
        median_duration_ratio=_q(median(ratios)) if ratios else None,
        structured_comparisons=len(structured), eligible_structured_comparisons=len(eligible),
        within_target=sum(relation(item) == TargetExecutionRelation.WITHIN_TARGET for item in eligible),
        above_or_faster=sum(relation(item) in POSITIVE_RELATIONS for item in eligible),
        below_or_slower=sum(relation(item) in NEGATIVE_RELATIONS for item in eligible),
        mixed=sum(relation(item) == TargetExecutionRelation.MIXED for item in eligible),
        unknown_target=sum(item.target_comparison is None or item.target_comparison.confidence not in ELIGIBLE_CONFIDENCE for item in evaluable),
        recent_sessions=len(recent), background_sessions=len(background),
        recent_structured_comparisons=len(recent_targets), background_structured_comparisons=len(background_targets),
        recent_within_target=sum(relation(item) == TargetExecutionRelation.WITHIN_TARGET for item in recent_targets),
        recent_above_or_faster=sum(relation(item) in POSITIVE_RELATIONS for item in recent_targets),
        recent_below_or_slower=sum(relation(item) in NEGATIVE_RELATIONS for item in recent_targets),
        recent_partial=sum(_is_partial(item) for item in recent if _is_evaluable(item)),
        evidence_confidence_high=confidence.count(ComparisonConfidence.HIGH),
        evidence_confidence_medium=confidence.count(ComparisonConfidence.MEDIUM),
        evidence_confidence_low=confidence.count(ComparisonConfidence.LOW),
        evidence_confidence_insufficient=confidence.count(ComparisonConfidence.INSUFFICIENT),
    )


def _signal_confidence(metrics: AdaptationMetrics, signal: AdaptationSignalKind) -> AdaptationSignalConfidence:
    if signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE:
        return AdaptationSignalConfidence.INSUFFICIENT
    if (
        metrics.eligible_structured_comparisons >= 5
        and metrics.recent_structured_comparisons >= 3
        and metrics.evidence_confidence_high >= 4
        and metrics.evidence_confidence_medium <= 1
        and metrics.evidence_confidence_low == 0
    ):
        return AdaptationSignalConfidence.HIGH
    if metrics.evaluable_sessions >= MIN_EVALUABLE_SESSIONS:
        return AdaptationSignalConfidence.MEDIUM
    return AdaptationSignalConfidence.LOW


def interpret_signal(sessions: Iterable[SessionExecutionEvidence], *, as_of_date: date, sport: str | None = None, session_type: str | None = None, target_kind: str | None = None) -> AdaptationSignal:
    rows = tuple(sorted(sessions, key=lambda item: (item.planned_date, str(item.planned_session_id))))
    metrics = adaptation_metrics(rows, as_of_date=as_of_date)
    reasons = []
    signal = AdaptationSignalKind.INSUFFICIENT_EVIDENCE
    if not rows:
        reasons.append(AdaptationReasonCode.NO_EVIDENCE)
    elif sport == "strength":
        reasons.append(AdaptationReasonCode.STRENGTH_INTENSITY_NOT_OBSERVED)
    elif metrics.evaluable_sessions < MIN_EVALUABLE_SESSIONS:
        reasons.append(AdaptationReasonCode.BELOW_MINIMUM_EVALUABLE_SESSIONS)
    elif metrics.unmatched_sessions * 2 > metrics.session_count:
        reasons.append(AdaptationReasonCode.UNMATCHED_MAJORITY)
    elif metrics.eligible_structured_comparisons == 0:
        if metrics.duration_completed >= MIN_EVALUABLE_SESSIONS and metrics.partial_sessions == 0:
            signal = AdaptationSignalKind.MAINTAIN
            reasons.append(AdaptationReasonCode.CONSISTENT_DURATION_EXECUTION)
        else:
            reasons.append(AdaptationReasonCode.BELOW_MINIMUM_STRUCTURED_COMPARISONS)
    elif Decimal(metrics.unknown_target) / Decimal(metrics.evaluable_sessions) > MAX_UNKNOWN_FRACTION:
        reasons.append(AdaptationReasonCode.UNKNOWN_MAJORITY)
    elif metrics.eligible_structured_comparisons < MIN_STRUCTURED_COMPARISONS:
        reasons.append(AdaptationReasonCode.BELOW_MINIMUM_STRUCTURED_COMPARISONS)
    elif metrics.recent_structured_comparisons < MIN_RECENT_STRUCTURED_COMPARISONS:
        reasons.append(AdaptationReasonCode.BELOW_MINIMUM_RECENT_EVIDENCE)
    else:
        eligible = tuple(item for item in rows if _is_evaluable(item) and item.target_comparison is not None and item.target_comparison.confidence in ELIGIBLE_CONFIDENCE)
        total = Decimal(len(eligible))
        directional = Decimal(metrics.above_or_faster) / total
        adverse = Decimal(metrics.below_or_slower) / total
        partial = Decimal(metrics.partial_sessions) / Decimal(metrics.evaluable_sessions)
        extreme = any(_is_extreme_overshoot(item) for item in eligible)
        if (metrics.above_or_faster and metrics.below_or_slower) or metrics.mixed >= 2 or extreme:
            signal = AdaptationSignalKind.INCONSISTENT_EXECUTION
            if metrics.above_or_faster and metrics.below_or_slower:
                reasons.append(AdaptationReasonCode.CONTRADICTORY_TARGET_DIRECTIONS)
            if metrics.mixed >= 2:
                reasons.append(AdaptationReasonCode.MIXED_WITHOUT_DIRECTION)
            if extreme:
                reasons.append(AdaptationReasonCode.EXTREME_OVERSHOOT_PRESENT)
        elif (adverse >= DIRECTIONAL_FRACTION or partial >= DIRECTIONAL_FRACTION) and metrics.recent_below_or_slower + metrics.recent_partial >= 2:
            signal = AdaptationSignalKind.REGRESSION_CANDIDATE
            if adverse >= DIRECTIONAL_FRACTION:
                reasons.append(AdaptationReasonCode.REPEATED_BELOW_OR_SLOWER)
            if partial >= DIRECTIONAL_FRACTION:
                reasons.append(AdaptationReasonCode.REPEATED_PARTIAL_EXECUTION)
            if metrics.background_structured_comparisons and metrics.recent_below_or_slower > metrics.below_or_slower - metrics.recent_below_or_slower:
                reasons.append(AdaptationReasonCode.RECENT_DETERIORATION)
        elif directional >= DIRECTIONAL_FRACTION and metrics.recent_above_or_faster >= 2 and metrics.recent_below_or_slower == 0 and metrics.recent_partial == 0 and partial <= MAX_PROGRESSION_PARTIAL_FRACTION:
            signal = AdaptationSignalKind.PROGRESSION_CANDIDATE
            reasons.extend((AdaptationReasonCode.REPEATED_ABOVE_OR_FASTER, AdaptationReasonCode.RECENT_EVIDENCE_CONSISTENT))
        else:
            signal = AdaptationSignalKind.MAINTAIN
            reasons.append(AdaptationReasonCode.CONSISTENT_WITHIN_TARGET if metrics.within_target else AdaptationReasonCode.MIXED_WITHOUT_DIRECTION)
    return AdaptationSignal(
        sport=sport, session_type=session_type, target_kind=target_kind,
        signal=signal, confidence=_signal_confidence(metrics, signal),
        evidence_count=metrics.evaluable_sessions, supporting_metrics=metrics,
        reason_codes=tuple(reasons), supporting_session_ids=tuple(item.planned_session_id for item in rows),
    )


def build_execution_adaptation_context(evidence: PrescribedCompletedEvidenceContext) -> ExecutionAdaptationContext:
    sessions = evidence.sessions
    by_sport = defaultdict(list)
    by_type = defaultdict(list)
    by_target = defaultdict(list)
    for item in sessions:
        by_sport[item.sport].append(item)
        by_type[(item.sport, item.session_type)].append(item)
        kind = _target_kind(item)
        if kind is not None:
            by_target[(item.sport, item.session_type, kind)].append(item)
    return ExecutionAdaptationContext(
        athlete_profile_id=evidence.athlete_profile_id, as_of_date=evidence.as_of_date,
        window_start_date=evidence.window_start_date,
        global_summary=adaptation_metrics(sessions, as_of_date=evidence.as_of_date),
        global_signal=interpret_signal(sessions, as_of_date=evidence.as_of_date),
        sport_signals=tuple(interpret_signal(rows, as_of_date=evidence.as_of_date, sport=sport) for sport, rows in sorted(by_sport.items())),
        session_type_signals=tuple(interpret_signal(rows, as_of_date=evidence.as_of_date, sport=sport, session_type=session_type) for (sport, session_type), rows in sorted(by_type.items())),
        structured_target_signals=tuple(interpret_signal(rows, as_of_date=evidence.as_of_date, sport=sport, session_type=session_type, target_kind=kind) for (sport, session_type, kind), rows in sorted(by_target.items())),
    )
