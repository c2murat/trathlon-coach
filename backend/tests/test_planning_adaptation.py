from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.application.execution_proposals import ExecutionAdaptationProposalAssembler
from app.application.planning_preview import PlanningPreviewApplication
from app.db.models import TrainingPlanPreview
from app.domains.planning.contracts import (
    PerformanceSnapshot, PlanningAdaptationInput, PlanningAdaptationItem,
)
from app.domains.planning.execution_adaptation import AdaptationSignalConfidence, AdaptationSignalKind
from app.domains.planning.execution_adaptation import build_execution_adaptation_context
from app.domains.planning.execution_evidence import ExecutionHistorySummary, PrescribedCompletedEvidenceContext, TargetExecutionRelation
from app.domains.planning.execution_proposals import (
    PrescriptionRange, ProposalDirection, ProposalKind,
    build_execution_adaptation_proposal_context,
)
from app.domains.planning.planning_adaptation import (
    PlanningAdaptationAthleteMismatchError, PlanningAdaptationCutoffMismatchError,
    PlanningAdaptationDecisionStatus, normalize_planning_adaptation,
    with_planning_adaptation,
)
from app.domains.planning.session_planning import SessionType
from app.domains.planning.workout_builder import (
    WorkoutBuilderConfig, WorkoutDecisionCode, build_structured_workout,
)
from tests.test_execution_proposals import adaptation, signal
from tests.test_execution_proposals import factual_session
from tests.test_planning_preview_artifact import artifact
from tests.test_planning_preview_application import seeded
from tests.test_workout_builder import phase_targets, prescription, source
from tests.test_session_planning import with_running_frequency
from tests.test_weekly_budget import context as base_context


CONFIG = WorkoutBuilderConfig(version="workout-1", algorithm_version="workout-algorithm-1")


def proposal_context(kind=AdaptationSignalKind.PROGRESSION_CANDIDATE, *, sport="running", session_type="RUN_INTERVAL", target_kind="RUN_PACE", confidence=AdaptationSignalConfidence.HIGH):
    c3 = build_execution_adaptation_proposal_context(adaptation((signal(
        kind, sport=sport, session_type=session_type,
        target_kind=target_kind, confidence=confidence,
    ),)))
    return c3


def numeric_context(*, sport, session_type, target_kind, kind, direction, current, proposed, confidence=AdaptationSignalConfidence.MEDIUM):
    c3 = proposal_context(
        AdaptationSignalKind.PROGRESSION_CANDIDATE if kind == ProposalKind.INCREASE_TARGET else AdaptationSignalKind.REGRESSION_CANDIDATE,
        sport=sport, session_type=session_type, target_kind=target_kind,
        confidence=AdaptationSignalConfidence.HIGH,
    )
    item = c3.proposals[0].model_copy(update={
        "proposal_kind": kind, "proposed_direction": direction,
        "confidence": confidence,
        "current_prescription": PrescriptionRange(minimum=current[0], maximum=current[1], unit=current[2]),
        "proposed_range": PrescriptionRange(minimum=proposed[0], maximum=proposed[1], unit=proposed[2]),
        "applied_guards": (),
    })
    return c3.model_copy(update={"proposals": (item,)})


@pytest.mark.parametrize(("kind", "status"), [
    (AdaptationSignalKind.INSUFFICIENT_EVIDENCE, PlanningAdaptationDecisionStatus.NOT_APPLICABLE),
    (AdaptationSignalKind.MAINTAIN, PlanningAdaptationDecisionStatus.NO_CHANGE),
    (AdaptationSignalKind.INCONSISTENT_EXECUTION, PlanningAdaptationDecisionStatus.NOT_APPLICABLE),
])
def test_no_action_proposals_do_not_create_planning_input(kind, status):
    c3 = proposal_context(kind)
    projection = normalize_planning_adaptation(proposals=c3, athlete_id=c3.athlete_profile_id, cutoff_date=c3.as_of_date)
    assert projection.planning_input is None
    assert projection.decisions[0].status == status


def test_current_direction_only_proposal_is_considered_but_skipped_without_safe_step():
    c3 = proposal_context()
    projection = normalize_planning_adaptation(proposals=c3, athlete_id=c3.athlete_profile_id, cutoff_date=c3.as_of_date)
    assert projection.planning_input is None
    assert projection.decisions[0].status == PlanningAdaptationDecisionStatus.SKIPPED_NO_SAFE_STEP


def test_low_confidence_numeric_proposal_is_not_applied():
    c3 = numeric_context(
        sport="running", session_type="RUN_INTERVAL", target_kind="RUN_PACE",
        kind=ProposalKind.INCREASE_TARGET, direction=ProposalDirection.FASTER_PACE,
        current=(215, 229, "seconds_per_km"), proposed=(212, 226, "seconds_per_km"),
        confidence=AdaptationSignalConfidence.LOW,
    )
    projection = normalize_planning_adaptation(proposals=c3, athlete_id=c3.athlete_profile_id, cutoff_date=c3.as_of_date)
    assert projection.planning_input is None
    assert projection.decisions[0].status == PlanningAdaptationDecisionStatus.SKIPPED_LOW_CONFIDENCE


def test_conflicting_proposals_are_skipped_independently_of_input_order():
    first = numeric_context(
        sport="running", session_type="RUN_INTERVAL", target_kind="RUN_PACE",
        kind=ProposalKind.INCREASE_TARGET, direction=ProposalDirection.FASTER_PACE,
        current=(215, 229, "seconds_per_km"), proposed=(212, 226, "seconds_per_km"),
    )
    decrease = numeric_context(
        sport="running", session_type="RUN_INTERVAL", target_kind="RUN_PACE",
        kind=ProposalKind.DECREASE_TARGET, direction=ProposalDirection.SLOWER_PACE,
        current=(215, 229, "seconds_per_km"), proposed=(218, 232, "seconds_per_km"),
    ).proposals[0]
    def project(items):
        value = first.model_copy(update={"proposals": tuple(items)})
        return normalize_planning_adaptation(proposals=value, athlete_id=value.athlete_profile_id, cutoff_date=value.as_of_date)
    left = project((first.proposals[0], decrease))
    right = project((decrease, first.proposals[0]))
    assert left.model_dump_json() == right.model_dump_json()
    assert left.planning_input is None
    assert {item.status for item in left.decisions} == {PlanningAdaptationDecisionStatus.SKIPPED_CONFLICT}


def test_athlete_and_cutoff_mismatches_are_explicit():
    c3 = proposal_context()
    with pytest.raises(PlanningAdaptationAthleteMismatchError):
        normalize_planning_adaptation(proposals=c3, athlete_id=UUID(int=99), cutoff_date=c3.as_of_date)
    with pytest.raises(PlanningAdaptationCutoffMismatchError):
        normalize_planning_adaptation(proposals=c3, athlete_id=c3.athlete_profile_id, cutoff_date=c3.as_of_date.replace(day=c3.as_of_date.day - 1))


def planning_item(ctx, *, sport, session_type, target_kind, kind, direction, current, proposed):
    return PlanningAdaptationInput(
        athlete_id=ctx.request.athlete_id, proposal_version="0.8G.2C.3",
        cutoff_date=ctx.request.planning_date,
        items=(PlanningAdaptationItem(
            proposal_version="0.8G.2C.3", cutoff_date=ctx.request.planning_date,
            sport=sport, session_type=session_type, target_kind=target_kind,
            proposal_kind=kind, direction=direction, confidence="MEDIUM",
            current_minimum=Decimal(str(current[0])), current_maximum=Decimal(str(current[1])),
            proposed_minimum=Decimal(str(proposed[0])), proposed_maximum=Decimal(str(proposed[1])), unit=current[2],
        ),),
    )


@pytest.mark.parametrize(("sport", "session_type", "performance", "target_kind", "kind", "direction", "delta"), [
    ("running", SessionType.RUN_INTERVAL, PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250")), "RUN_PACE", "INCREASE_TARGET", "FASTER_PACE", -2),
    ("running", SessionType.RUN_INTERVAL, PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250")), "RUN_PACE", "DECREASE_TARGET", "SLOWER_PACE", 2),
    ("cycling", SessionType.BIKE_INTERVAL, PerformanceSnapshot(cycling_ftp_watts=Decimal("200")), "POWER", "INCREASE_TARGET", "HIGHER_POWER", 2),
    ("cycling", SessionType.BIKE_INTERVAL, PerformanceSnapshot(cycling_ftp_watts=Decimal("200")), "POWER", "DECREASE_TARGET", "LOWER_POWER", -2),
    ("swimming", SessionType.SWIM_INTERVAL, PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110")), "SWIM_PACE", "INCREASE_TARGET", "FASTER_PACE", -1),
    ("swimming", SessionType.SWIM_INTERVAL, PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110")), "SWIM_PACE", "DECREASE_TARGET", "SLOWER_PACE", 1),
])
def test_numeric_proposal_changes_only_matching_work_target_and_is_auditable(sport, session_type, performance, target_kind, kind, direction, delta):
    ctx, original_session = source(performance)
    selected = prescription(original_session, session_type, discipline=sport)
    baseline = build_structured_workout(ctx, selected, CONFIG)
    baseline_targets = phase_targets(baseline.definition)
    current = (baseline_targets[0].resolved_minimum, baseline_targets[0].resolved_maximum, baseline_targets[0].resolved_unit)
    proposed = (current[0] + delta, current[1] + delta, current[2])
    adaptation_input = planning_item(
        ctx, sport=sport, session_type=session_type.value, target_kind=target_kind,
        kind=kind, direction=direction, current=current, proposed=proposed,
    )
    adapted_context = with_planning_adaptation(ctx, adaptation_input)
    adapted = build_structured_workout(adapted_context, selected, CONFIG)
    result = phase_targets(adapted.definition)[0]
    assert (result.resolved_minimum, result.resolved_maximum) == proposed[:2]
    assert result.planning_adaptation.before_minimum == current[0]
    assert result.planning_adaptation.after_minimum == proposed[0]
    assert WorkoutDecisionCode.TARGET_ADAPTED_FROM_EXECUTION_PROPOSAL in {item.code for item in adapted.decisions}
    assert [node.duration for node in adapted.definition.steps] == [node.duration for node in baseline.definition.steps]
    assert adapted_context.fingerprint != ctx.fingerprint


def test_nonmatching_session_and_strength_are_unchanged():
    ctx, original_session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250")))
    interval = prescription(original_session, SessionType.RUN_INTERVAL)
    baseline = build_structured_workout(ctx, interval, CONFIG)
    current_target = phase_targets(baseline.definition)[0]
    adaptation_input = planning_item(
        ctx, sport="running", session_type="RUN_THRESHOLD", target_kind="RUN_PACE",
        kind="INCREASE_TARGET", direction="FASTER_PACE",
        current=(current_target.resolved_minimum, current_target.resolved_maximum, current_target.resolved_unit),
        proposed=(current_target.resolved_minimum - 2, current_target.resolved_maximum - 2, current_target.resolved_unit),
    )
    unchanged = build_structured_workout(with_planning_adaptation(ctx, adaptation_input), interval, CONFIG)
    assert phase_targets(unchanged.definition)[0].planning_adaptation is None
    strength = prescription(original_session, SessionType.GENERAL_STRENGTH, discipline="strength")
    assert all(item.planning_adaptation is None for item in phase_targets(build_structured_workout(with_planning_adaptation(ctx, adaptation_input), strength, CONFIG).definition))


def test_no_adaptation_preserves_context_identity_and_fingerprint_and_validation_rejects_bad_ranges():
    ctx, _ = source()
    assert with_planning_adaptation(ctx, None) is ctx
    with pytest.raises(ValidationError):
        PlanningAdaptationItem(
            proposal_version="v", cutoff_date=ctx.request.planning_date,
            sport="running", session_type="RUN_INTERVAL", target_kind="RUN_PACE",
            proposal_kind="INCREASE_TARGET", direction="FASTER_PACE", confidence="MEDIUM",
            current_minimum=Decimal("215"), current_maximum=Decimal("229"),
            proposed_minimum=Decimal("220"), proposed_maximum=Decimal("210"), unit="seconds_per_km",
        )


def test_c1_to_c4_direction_only_chain_preserves_preview_exactly():
    ctx = base_context(windows=with_running_frequency()).model_copy(update={
        "performance": PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250")),
    })
    evidence = PrescribedCompletedEvidenceContext(
        athlete_profile_id=ctx.request.athlete_id, as_of_date=ctx.request.planning_date,
        window_start_date=ctx.request.planning_date - timedelta(days=84),
        sessions=tuple(factual_session(
            index, sport="running", session_type="RUN_INTERVAL",
            relation=TargetExecutionRelation.FASTER_THAN_TARGET,
            days=index * 5, actual=210,
        ).model_copy(update={"planned_date": ctx.request.planning_date - timedelta(days=index * 5)}) for index in range(1, 4)),
        summary=ExecutionHistorySummary(),
    )
    c2 = build_execution_adaptation_context(evidence)
    c3 = build_execution_adaptation_proposal_context(c2, athlete_profile_id=ctx.request.athlete_id)
    projection = normalize_planning_adaptation(
        proposals=c3, athlete_id=ctx.request.athlete_id,
        cutoff_date=ctx.request.planning_date,
    )
    assert projection.planning_input is None
    assert {item.status for item in projection.decisions} == {PlanningAdaptationDecisionStatus.SKIPPED_LOW_CONFIDENCE}
    assert artifact(with_planning_adaptation(ctx, projection.planning_input)).model_dump(mode="json") == artifact(ctx).model_dump(mode="json")


def test_effective_normalized_input_changes_preview_fingerprint_and_audits_before_after():
    ctx = base_context(windows=with_running_frequency()).model_copy(update={
        "performance": PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250")),
    })
    baseline = artifact(ctx)
    candidate = next(item for item in baseline.sessions if item.workout.definition is not None and item.prescription.discipline == "running")
    current_target = phase_targets(candidate.workout.definition)[0]
    adaptation_input = planning_item(
        ctx, sport="running", session_type=candidate.prescription.session_type.value,
        target_kind="RUN_PACE", kind="INCREASE_TARGET", direction="FASTER_PACE",
        current=(current_target.resolved_minimum, current_target.resolved_maximum, current_target.resolved_unit),
        proposed=(current_target.resolved_minimum - 1, current_target.resolved_maximum - 1, current_target.resolved_unit),
    )
    adapted = artifact(with_planning_adaptation(ctx, adaptation_input))
    assert adapted.fingerprint != baseline.fingerprint
    assert len(adapted.sessions) == len(baseline.sessions)
    assert [(item.prescription.date, item.prescription.target_duration_minutes) for item in adapted.sessions] == [(item.prescription.date, item.prescription.target_duration_minutes) for item in baseline.sessions]
    affected = [item for item in adapted.sessions if item.prescription.session_type == candidate.prescription.session_type and item.workout.definition is not None]
    assert affected
    assert all(any(target.planning_adaptation is not None for target in phase_targets(item.workout.definition)) for item in affected)


def test_acceptance_materializes_stored_artifact_without_recomputing_c1_to_c4(monkeypatch):
    engine, preview_id, athlete_id, user_id, source_artifact = seeded()
    monkeypatch.setattr(ExecutionAdaptationProposalAssembler, "assemble", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("accept must not recompute adaptation")))
    with Session(engine) as db:
        plan = PlanningPreviewApplication(db).accept(
            preview_id=preview_id, athlete_id=athlete_id,
            user_id=user_id, role="athlete",
        )
        assert plan.source_preview_id == preview_id
        assert PlanningPreviewApplication(db).artifact(db.get(TrainingPlanPreview, preview_id)) == source_artifact
