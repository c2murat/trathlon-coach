from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from statistics import median
from typing import Iterable
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.capability.analysis import LapEvidence, effort_value
from app.domains.planning.models import StructuredWorkoutDefinition, WorkoutNode, WorkoutTarget


EXECUTION_EVIDENCE_VERSION = "0.8G.2C.1"
EXECUTION_WINDOW_DAYS = 84
PARTIAL_DURATION_RATIO = Decimal("0.80")
OVER_DURATION_RATIO = Decimal("1.20")
SHAPE_TOLERANCE = Decimal("0.20")


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompletionStatus(StrEnum):
    UNMATCHED = "UNMATCHED"
    UNKNOWN = "UNKNOWN"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    OVER_DURATION = "OVER_DURATION"


class ComparisonConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class TargetExecutionRelation(StrEnum):
    FASTER_THAN_TARGET = "FASTER_THAN_TARGET"
    SLOWER_THAN_TARGET = "SLOWER_THAN_TARGET"
    ABOVE_POWER_TARGET = "ABOVE_POWER_TARGET"
    BELOW_POWER_TARGET = "BELOW_POWER_TARGET"
    WITHIN_TARGET = "WITHIN_TARGET"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class LinkProvenance(FrozenModel):
    activity_id: UUID
    match_source: str
    match_confidence: str
    matching_algorithm_version: str | None = None


class TargetAdherenceEvidence(FrozenModel):
    planned_target_min: Decimal
    planned_target_max: Decimal
    unit: str
    planned_repetitions: int
    matched_repetitions: int
    actual_representative_value: Decimal
    target_hit_fraction: Decimal
    work_duration_similarity: Decimal
    recovery_similarity: Decimal | None = None
    execution_relation: TargetExecutionRelation
    confidence: ComparisonConfidence


class SessionExecutionEvidence(FrozenModel):
    planned_session_id: UUID
    planned_date: date
    sport: str
    session_type: str
    planned_duration_seconds: int | None = None
    link_count: int
    completed_activity_count: int
    sport_match: bool | None = None
    actual_duration_seconds: int | None = None
    duration_ratio: Decimal | None = None
    planned_distance_m: Decimal | None = None
    actual_distance_m: Decimal | None = None
    distance_ratio: Decimal | None = None
    completion_status: CompletionStatus
    comparison_confidence: ComparisonConfidence
    target_comparison: TargetAdherenceEvidence | None = None
    source_activity_ids: tuple[UUID, ...] = ()
    link_provenance: tuple[LinkProvenance, ...] = ()
    algorithm_version: str = EXECUTION_EVIDENCE_VERSION


class ExecutionHistoryGroup(FrozenModel):
    sport: str
    session_type: str
    session_count: int
    matched_count: int
    unmatched_past_count: int
    completed_duration_count: int
    median_duration_ratio: Decimal | None = None
    structured_target_comparisons: int
    within_target_count: int
    above_or_faster_count: int
    below_or_slower_count: int
    partial_count: int
    unknown_count: int


class ExecutionHistorySummary(FrozenModel):
    groups: tuple[ExecutionHistoryGroup, ...] = ()


class PrescribedCompletedEvidenceContext(FrozenModel):
    athlete_profile_id: UUID
    as_of_date: date
    window_start_date: date
    sessions: tuple[SessionExecutionEvidence, ...] = ()
    summary: ExecutionHistorySummary
    algorithm_version: str = EXECUTION_EVIDENCE_VERSION


class LinkedActivityEvidence(FrozenModel):
    activity_id: UUID
    sport: str
    duration_seconds: int
    distance_m: Decimal | None = None
    match_source: str
    match_confidence: str
    matching_algorithm_version: str | None = None
    laps: tuple[LapEvidence, ...] = ()


class PlannedSessionEvidence(FrozenModel):
    session_id: UUID
    planned_date: date
    sport: str
    session_type: str
    planned_duration_seconds: int | None = None
    planned_distance_m: Decimal | None = None
    workout: StructuredWorkoutDefinition | None = None
    linked_activities: tuple[LinkedActivityEvidence, ...] = ()


def _q(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _compatible(planned: str, actual: str) -> bool:
    return planned == actual or planned == "multisport" or actual == "multisport"


def _completion(ratio: Decimal | None) -> CompletionStatus:
    if ratio is None:
        return CompletionStatus.UNKNOWN
    if ratio < PARTIAL_DURATION_RATIO:
        return CompletionStatus.PARTIAL
    if ratio > OVER_DURATION_RATIO:
        return CompletionStatus.OVER_DURATION
    return CompletionStatus.COMPLETED


def _work_spec(workout: StructuredWorkoutDefinition | None):
    if workout is None:
        return None
    for node in workout.steps:
        if node.kind != "repeat" or not node.steps:
            continue
        work = next((step for step in node.steps if step.phase == "work" and step.target), None)
        if work is None or work.duration is None or node.repetitions is None:
            continue
        target = work.target
        minimum = target.resolved_minimum if target.resolved_minimum is not None else target.minimum
        maximum = target.resolved_maximum if target.resolved_maximum is not None else target.maximum
        unit = target.resolved_unit or target.reference_unit
        if minimum is None or maximum is None or unit not in {"watts", "seconds_per_km", "seconds_per_100m"}:
            continue
        recovery = next((step for step in node.steps if step.phase == "recovery" and step.duration), None)
        return node.repetitions, work, recovery, Decimal(str(minimum)), Decimal(str(maximum)), unit
    return None


def _shape_matches(lap: LapEvidence, node: WorkoutNode) -> bool:
    duration = node.duration
    if duration is None:
        return False
    if duration.mode == "time" and duration.seconds:
        return abs(Decimal(lap.duration_seconds - duration.seconds)) <= Decimal(duration.seconds) * SHAPE_TOLERANCE
    if duration.mode == "distance" and duration.meters and lap.distance_m:
        return abs(lap.distance_m - Decimal(duration.meters)) <= Decimal(duration.meters) * SHAPE_TOLERANCE
    return False


def _relation(values: tuple[Decimal, ...], low: Decimal, high: Decimal, unit: str) -> TargetExecutionRelation:
    inside = sum(low <= value <= high for value in values)
    if Decimal(inside) / Decimal(len(values)) >= Decimal("0.60"):
        return TargetExecutionRelation.WITHIN_TARGET
    below = all(value < low for value in values)
    above = all(value > high for value in values)
    if unit in {"seconds_per_km", "seconds_per_100m"}:
        return TargetExecutionRelation.FASTER_THAN_TARGET if below else TargetExecutionRelation.SLOWER_THAN_TARGET if above else TargetExecutionRelation.MIXED
    return TargetExecutionRelation.BELOW_POWER_TARGET if below else TargetExecutionRelation.ABOVE_POWER_TARGET if above else TargetExecutionRelation.MIXED


def compare_structured_target(workout: StructuredWorkoutDefinition | None, activities: tuple[LinkedActivityEvidence, ...]) -> TargetAdherenceEvidence | None:
    spec = _work_spec(workout)
    if spec is None:
        return None
    repetitions, work, recovery, low, high, unit = spec
    laps = sorted((lap for item in activities for lap in item.laps if lap.sport == item.sport and lap.coverage >= Decimal("0.50") and lap.lap_index < 10000), key=lambda lap: (str(lap.activity_id), lap.lap_index))
    if workout and workout.sport == "swimming":
        laps = [lap for lap in laps if not lap.elapsed_seconds or lap.moving_seconds is None or Decimal(lap.moving_seconds) >= Decimal(lap.elapsed_seconds) * Decimal("0.75")]
    work_laps = [lap for lap in laps if _shape_matches(lap, work) and effort_value(lap, workout.sport) is not None]
    if len(work_laps) < min(3, repetitions):
        return None
    selected = tuple(work_laps[:repetitions])
    values = tuple(effort_value(lap, workout.sport) for lap in selected)
    hit = _q(Decimal(sum(low <= value <= high for value in values)) / Decimal(len(values)))
    expected = work.duration.seconds if work.duration.mode == "time" else work.duration.meters
    actual_shapes = [lap.duration_seconds if work.duration.mode == "time" else lap.distance_m for lap in selected]
    shape_similarity = _q(sum((min(Decimal(str(value)), Decimal(expected)) / max(Decimal(str(value)), Decimal(expected)) for value in actual_shapes), Decimal(0)) / len(actual_shapes))
    recovery_similarity = None
    if recovery is not None:
        recovery_laps = [lap for lap in laps if _shape_matches(lap, recovery) and lap not in selected]
        recovery_similarity = _q(Decimal(min(len(recovery_laps), repetitions)) / Decimal(repetitions))
    confidence = ComparisonConfidence.HIGH if len(selected) == repetitions and shape_similarity >= Decimal("0.90") and (recovery_similarity is None or recovery_similarity >= Decimal("0.75")) else ComparisonConfidence.MEDIUM
    return TargetAdherenceEvidence(
        planned_target_min=_q(low), planned_target_max=_q(high), unit=unit,
        planned_repetitions=repetitions, matched_repetitions=len(selected),
        actual_representative_value=_q(median(values)), target_hit_fraction=hit,
        work_duration_similarity=shape_similarity, recovery_similarity=recovery_similarity,
        execution_relation=_relation(values, low, high, unit), confidence=confidence,
    )


def build_session_execution_evidence(item: PlannedSessionEvidence) -> SessionExecutionEvidence:
    unique = {activity.activity_id: activity for activity in item.linked_activities}
    activities = tuple(unique[key] for key in sorted(unique, key=str))
    provenance = tuple(LinkProvenance(activity_id=a.activity_id, match_source=a.match_source, match_confidence=a.match_confidence, matching_algorithm_version=a.matching_algorithm_version) for a in activities)
    if not activities:
        return SessionExecutionEvidence(
            planned_session_id=item.session_id, planned_date=item.planned_date, sport=item.sport,
            session_type=item.session_type, planned_duration_seconds=item.planned_duration_seconds,
            planned_distance_m=item.planned_distance_m, link_count=0, completed_activity_count=0,
            completion_status=CompletionStatus.UNMATCHED, comparison_confidence=ComparisonConfidence.INSUFFICIENT,
        )
    compatible = tuple(activity for activity in activities if _compatible(item.sport, activity.sport))
    all_match = len(compatible) == len(activities)
    actual_duration = sum(activity.duration_seconds for activity in compatible) if compatible else None
    raw_duration_ratio = Decimal(actual_duration) / Decimal(item.planned_duration_seconds) if actual_duration is not None and item.planned_duration_seconds else None
    duration_ratio = _q(raw_duration_ratio) if raw_duration_ratio is not None else None
    distances = [activity.distance_m for activity in compatible if activity.distance_m is not None]
    actual_distance = _q(sum(distances, Decimal(0))) if distances else None
    distance_ratio = _q(actual_distance / item.planned_distance_m) if actual_distance is not None and item.planned_distance_m else None
    target = compare_structured_target(item.workout, compatible) if all_match else None
    link_confidences = {activity.match_confidence.lower() for activity in activities}
    confidence = (
        ComparisonConfidence.LOW if not all_match or "low" in link_confidences else
        ComparisonConfidence.MEDIUM if "medium" in link_confidences else
        ComparisonConfidence.HIGH
    )
    if target is not None and confidence in {ComparisonConfidence.LOW, ComparisonConfidence.MEDIUM}:
        target = target.model_copy(update={"confidence": confidence})
    return SessionExecutionEvidence(
        planned_session_id=item.session_id, planned_date=item.planned_date, sport=item.sport,
        session_type=item.session_type, planned_duration_seconds=item.planned_duration_seconds,
        planned_distance_m=item.planned_distance_m, link_count=len(activities),
        completed_activity_count=len(activities), sport_match=all_match,
        actual_duration_seconds=actual_duration, duration_ratio=duration_ratio,
        actual_distance_m=actual_distance, distance_ratio=distance_ratio,
        completion_status=_completion(raw_duration_ratio), comparison_confidence=confidence,
        target_comparison=target, source_activity_ids=tuple(a.activity_id for a in activities), link_provenance=provenance,
    )


def build_summary(sessions: Iterable[SessionExecutionEvidence]) -> ExecutionHistorySummary:
    grouped = defaultdict(list)
    for item in sessions:
        grouped[(item.sport, item.session_type)].append(item)
    rows = []
    for (sport, session_type), items in sorted(grouped.items()):
        ratios = [item.duration_ratio for item in items if item.duration_ratio is not None]
        targets = [item.target_comparison for item in items if item.target_comparison is not None]
        relations = [item.execution_relation for item in targets]
        rows.append(ExecutionHistoryGroup(
            sport=sport, session_type=session_type, session_count=len(items),
            matched_count=sum(item.completed_activity_count > 0 for item in items),
            unmatched_past_count=sum(item.completion_status == CompletionStatus.UNMATCHED for item in items),
            completed_duration_count=len(ratios), median_duration_ratio=_q(median(ratios)) if ratios else None,
            structured_target_comparisons=len(targets),
            within_target_count=relations.count(TargetExecutionRelation.WITHIN_TARGET),
            above_or_faster_count=sum(value in {TargetExecutionRelation.ABOVE_POWER_TARGET, TargetExecutionRelation.FASTER_THAN_TARGET} for value in relations),
            below_or_slower_count=sum(value in {TargetExecutionRelation.BELOW_POWER_TARGET, TargetExecutionRelation.SLOWER_THAN_TARGET} for value in relations),
            partial_count=sum(item.completion_status == CompletionStatus.PARTIAL or (item.target_comparison is not None and item.target_comparison.matched_repetitions < item.target_comparison.planned_repetitions) for item in items),
            unknown_count=sum(item.target_comparison is None for item in items),
        ))
    return ExecutionHistorySummary(groups=tuple(rows))
