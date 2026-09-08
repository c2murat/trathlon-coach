from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.application.execution_proposals import ExecutionAdaptationProposalAssembler
from app.domains.planning.contracts import PlanningContext, context_fingerprint
from app.domains.planning.execution_adaptation import (
    AdaptationMetrics, AdaptationReasonCode, AdaptationSignal,
    AdaptationSignalConfidence, AdaptationSignalKind, ExecutionAdaptationContext,
    build_execution_adaptation_context,
)
from app.domains.planning.execution_evidence import (
    ComparisonConfidence, CompletionStatus, ExecutionHistorySummary,
    PrescribedCompletedEvidenceContext, SessionExecutionEvidence,
    TargetAdherenceEvidence, TargetExecutionRelation,
)
from app.domains.planning.execution_proposals import (
    EXECUTION_ADAPTATION_PROPOSAL_VERSION, AdaptationProposal,
    ExecutionProposalAthleteMismatchError, PrescriptionRange, ProposalDirection,
    ProposalGuard, ProposalKind, ProposalReasonCode,
    build_execution_adaptation_proposal_context,
)


AS_OF = date(2026, 9, 8)
ATHLETE_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_ATHLETE_ID = UUID("00000000-0000-0000-0000-000000000002")


def metrics(count=3):
    return AdaptationMetrics(
        session_count=count, evaluable_sessions=count, unmatched_sessions=0,
        duration_comparisons=count, duration_completed=count, partial_sessions=0,
        median_duration_ratio=Decimal("0.98"), structured_comparisons=count,
        eligible_structured_comparisons=count, within_target=count,
        above_or_faster=0, below_or_slower=0, mixed=0, unknown_target=0,
        recent_sessions=count, background_sessions=0,
        recent_structured_comparisons=count, background_structured_comparisons=0,
        recent_within_target=count, recent_above_or_faster=0,
        recent_below_or_slower=0, recent_partial=0,
        evidence_confidence_high=count, evidence_confidence_medium=0,
        evidence_confidence_low=0, evidence_confidence_insufficient=0,
    )


def signal(kind, *, sport="running", session_type="RUN_INTERVAL", target_kind="RUN_PACE", confidence=AdaptationSignalConfidence.MEDIUM, reasons=()):
    return AdaptationSignal(
        sport=sport, session_type=session_type, target_kind=target_kind,
        signal=kind, confidence=confidence, evidence_count=3,
        supporting_metrics=metrics(), reason_codes=tuple(reasons),
        supporting_session_ids=(
            UUID("00000000-0000-0000-0000-000000000003"),
            UUID("00000000-0000-0000-0000-000000000001"),
            UUID("00000000-0000-0000-0000-000000000002"),
        ),
    )


def adaptation(signals=(), session_signals=(), athlete_id=ATHLETE_ID):
    return ExecutionAdaptationContext(
        athlete_profile_id=athlete_id, as_of_date=AS_OF,
        window_start_date=AS_OF - timedelta(days=84), global_summary=metrics(0),
        global_signal=signal(AdaptationSignalKind.INSUFFICIENT_EVIDENCE, sport=None, session_type=None, target_kind=None, confidence=AdaptationSignalConfidence.INSUFFICIENT),
        structured_target_signals=tuple(signals), session_type_signals=tuple(session_signals),
    )


@pytest.mark.parametrize(("source", "expected"), [
    (AdaptationSignalKind.INSUFFICIENT_EVIDENCE, ProposalKind.INSUFFICIENT_EVIDENCE),
    (AdaptationSignalKind.MAINTAIN, ProposalKind.NO_CHANGE),
    (AdaptationSignalKind.PROGRESSION_CANDIDATE, ProposalKind.INCREASE_TARGET),
    (AdaptationSignalKind.REGRESSION_CANDIDATE, ProposalKind.DECREASE_TARGET),
    (AdaptationSignalKind.INCONSISTENT_EXECUTION, ProposalKind.REVIEW_EXECUTION),
])
def test_c2_to_c3_mapping(source, expected):
    result = build_execution_adaptation_proposal_context(adaptation((signal(source),)))
    assert result.proposals[0].proposal_kind == expected
    assert result.proposals[0].source_signal == source


@pytest.mark.parametrize(("sport", "target_kind", "source", "direction"), [
    ("running", "RUN_PACE", AdaptationSignalKind.PROGRESSION_CANDIDATE, ProposalDirection.FASTER_PACE),
    ("running", "RUN_PACE", AdaptationSignalKind.REGRESSION_CANDIDATE, ProposalDirection.SLOWER_PACE),
    ("cycling", "POWER", AdaptationSignalKind.PROGRESSION_CANDIDATE, ProposalDirection.HIGHER_POWER),
    ("cycling", "POWER", AdaptationSignalKind.REGRESSION_CANDIDATE, ProposalDirection.LOWER_POWER),
    ("swimming", "SWIM_PACE", AdaptationSignalKind.PROGRESSION_CANDIDATE, ProposalDirection.FASTER_PACE),
    ("swimming", "SWIM_PACE", AdaptationSignalKind.REGRESSION_CANDIDATE, ProposalDirection.SLOWER_PACE),
])
def test_supported_targets_have_correct_direction_but_no_invented_numeric_step(sport, target_kind, source, direction):
    proposal = build_execution_adaptation_proposal_context(adaptation((signal(source, sport=sport, session_type="QUALITY", target_kind=target_kind),))).proposals[0]
    assert proposal.proposed_direction == direction
    assert proposal.current_prescription is None and proposal.proposed_range is None
    assert ProposalReasonCode.TARGET_STEP_UNAVAILABLE in proposal.reason_codes
    assert ProposalGuard.NO_CAPABILITY_BOUND_AVAILABLE in proposal.applied_guards


def test_extreme_overshoot_remains_review_and_never_becomes_increase():
    source = signal(
        AdaptationSignalKind.INCONSISTENT_EXECUTION,
        sport="cycling", session_type="BIKE_INTERVAL", target_kind="POWER",
        reasons=(AdaptationReasonCode.EXTREME_OVERSHOOT_PRESENT,),
    )
    proposal = build_execution_adaptation_proposal_context(adaptation((source,))).proposals[0]
    assert proposal.proposal_kind == ProposalKind.REVIEW_EXECUTION
    assert ProposalReasonCode.EXTREME_OVERSHOOT_GUARD in proposal.reason_codes
    assert ProposalGuard.EXTREME_OVERSHOOT in proposal.applied_guards


def test_missing_or_incompatible_target_degrades_conservatively_without_reversing_direction():
    missing = build_execution_adaptation_proposal_context(adaptation((signal(AdaptationSignalKind.PROGRESSION_CANDIDATE, target_kind=None),))).proposals[0]
    assert missing.proposal_kind == ProposalKind.REVIEW_EXECUTION
    assert missing.proposed_direction == ProposalDirection.REVIEW
    incompatible = build_execution_adaptation_proposal_context(adaptation((signal(AdaptationSignalKind.REGRESSION_CANDIDATE, sport="running", target_kind="POWER"),))).proposals[0]
    assert incompatible.proposal_kind == ProposalKind.REVIEW_EXECUTION
    assert ProposalGuard.DISCIPLINE_COMPATIBILITY in incompatible.applied_guards
    assert incompatible.proposal_kind != ProposalKind.INCREASE_TARGET


def test_strength_never_proposes_intensity_kg_or_repetition_change():
    strength = signal(
        AdaptationSignalKind.INSUFFICIENT_EVIDENCE, sport="strength",
        session_type="STRENGTH_A", target_kind=None,
        confidence=AdaptationSignalConfidence.INSUFFICIENT,
    )
    proposal = build_execution_adaptation_proposal_context(adaptation(session_signals=(strength,))).proposals[0]
    assert proposal.proposal_kind == ProposalKind.INSUFFICIENT_EVIDENCE
    assert proposal.proposed_range is None
    assert proposal.applied_guards == (ProposalGuard.STRENGTH_INTENSITY_UNOBSERVED,)


def test_proposal_confidence_never_exceeds_source_and_direction_only_is_degraded():
    high = signal(AdaptationSignalKind.PROGRESSION_CANDIDATE, confidence=AdaptationSignalConfidence.HIGH)
    medium = signal(AdaptationSignalKind.REGRESSION_CANDIDATE, confidence=AdaptationSignalConfidence.MEDIUM)
    result = build_execution_adaptation_proposal_context(adaptation((high, medium))).proposals
    assert [item.confidence for item in result] == [AdaptationSignalConfidence.MEDIUM, AdaptationSignalConfidence.LOW]


def test_invalid_numeric_ranges_are_rejected_even_though_c3_emits_direction_only():
    with pytest.raises(ValidationError):
        PrescriptionRange(minimum=-1, maximum=10, unit="watts")
    with pytest.raises(ValidationError):
        PrescriptionRange(minimum=200, maximum=180, unit="watts")


def test_conflicting_session_types_remain_independent_and_summary_is_transparent():
    increase = signal(AdaptationSignalKind.PROGRESSION_CANDIDATE, session_type="RUN_INTERVAL")
    maintain = signal(AdaptationSignalKind.MAINTAIN, session_type="RUN_THRESHOLD")
    context = build_execution_adaptation_proposal_context(adaptation((maintain, increase)))
    assert [(item.session_type, item.proposal_kind) for item in context.proposals] == [
        ("RUN_INTERVAL", ProposalKind.INCREASE_TARGET),
        ("RUN_THRESHOLD", ProposalKind.NO_CHANGE),
    ]
    assert context.summary.increase_target == 1 and context.summary.no_change == 1
    assert [(item.session_type, item.proposal_kind) for item in context.group_summaries] == [
        ("RUN_INTERVAL", ProposalKind.INCREASE_TARGET),
        ("RUN_THRESHOLD", ProposalKind.NO_CHANGE),
    ]


def test_output_is_deterministic_frozen_and_supporting_ids_are_canonical():
    first = build_execution_adaptation_proposal_context(adaptation((signal(AdaptationSignalKind.MAINTAIN),)))
    second = build_execution_adaptation_proposal_context(adaptation(tuple(reversed((signal(AdaptationSignalKind.MAINTAIN),)))))
    assert first.model_dump_json() == second.model_dump_json()
    assert list(first.proposals[0].supporting_session_ids) == sorted(first.proposals[0].supporting_session_ids, key=str)
    assert first.algorithm_version == EXECUTION_ADAPTATION_PROPOSAL_VERSION
    with pytest.raises(ValidationError):
        first.algorithm_version = "changed"


def test_multiathlete_mismatch_is_rejected_explicitly():
    with pytest.raises(ExecutionProposalAthleteMismatchError):
        build_execution_adaptation_proposal_context(adaptation(athlete_id=OTHER_ATHLETE_ID), athlete_profile_id=ATHLETE_ID)


def factual_session(index, *, sport, session_type, relation, days, actual):
    unit = "watts" if sport == "cycling" else "seconds_per_100m" if sport == "swimming" else "seconds_per_km"
    low, high = (164, 185) if unit == "watts" else (107, 113) if unit == "seconds_per_100m" else (215, 229)
    return SessionExecutionEvidence(
        planned_session_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
        planned_date=AS_OF - timedelta(days=days), sport=sport, session_type=session_type,
        planned_duration_seconds=3600, link_count=1, completed_activity_count=1,
        sport_match=True, actual_duration_seconds=3540, duration_ratio=Decimal("0.98"),
        completion_status=CompletionStatus.COMPLETED,
        comparison_confidence=ComparisonConfidence.HIGH,
        target_comparison=TargetAdherenceEvidence(
            planned_target_min=Decimal(low), planned_target_max=Decimal(high), unit=unit,
            planned_repetitions=5, matched_repetitions=5,
            actual_representative_value=Decimal(actual), target_hit_fraction=Decimal("1") if relation == TargetExecutionRelation.WITHIN_TARGET else Decimal("0"),
            work_duration_similarity=Decimal("1"), recovery_similarity=Decimal("1"),
            execution_relation=relation, confidence=ComparisonConfidence.HIGH,
        ),
    )


def test_integrated_c1_to_c2_to_c3_chain_is_pure_for_run_bike_and_swim():
    rows = []
    for offset in range(3):
        rows.extend((
            factual_session(1 + offset, sport="running", session_type="RUN_INTERVAL", relation=TargetExecutionRelation.FASTER_THAN_TARGET, days=5 + offset * 5, actual=210),
            factual_session(4 + offset, sport="cycling", session_type="BIKE_THRESHOLD", relation=TargetExecutionRelation.WITHIN_TARGET, days=5 + offset * 5, actual=175),
            factual_session(7 + offset, sport="swimming", session_type="SWIM_THRESHOLD", relation=TargetExecutionRelation.SLOWER_THAN_TARGET, days=5 + offset * 5, actual=118),
        ))
    evidence = PrescribedCompletedEvidenceContext(
        athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
        window_start_date=AS_OF - timedelta(days=84), sessions=tuple(rows),
        summary=ExecutionHistorySummary(),
    )
    c2 = build_execution_adaptation_context(evidence)
    c3 = build_execution_adaptation_proposal_context(c2, athlete_profile_id=ATHLETE_ID)
    assert {(item.sport, item.proposal_kind) for item in c3.proposals} == {
        ("running", ProposalKind.INCREASE_TARGET),
        ("cycling", ProposalKind.NO_CHANGE),
        ("swimming", ProposalKind.DECREASE_TARGET),
    }
    assert evidence.sessions == tuple(rows)


def test_application_adds_no_query_beyond_c2_and_validates_requested_athlete():
    class NoDatabase:
        pass

    source = adaptation((signal(AdaptationSignalKind.MAINTAIN),))
    service = ExecutionAdaptationProposalAssembler(NoDatabase())
    calls = []
    service.adaptation.assemble = lambda **kwargs: calls.append(kwargs) or source
    result = service.assemble(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF)
    assert calls == [{"athlete_profile_id": ATHLETE_ID, "as_of_date": AS_OF}]
    assert result.athlete_profile_id == ATHLETE_ID


def test_building_proposals_does_not_change_planning_or_fingerprint():
    planning_input = {"athlete_id": str(ATHLETE_ID), "algorithm_version": "0.8F.9", "sessions": ("RUN_EASY",)}
    before = context_fingerprint(planning_input)
    build_execution_adaptation_proposal_context(adaptation((signal(AdaptationSignalKind.MAINTAIN),)))
    assert context_fingerprint(planning_input) == before
    assert "execution_proposals" not in PlanningContext.model_fields
