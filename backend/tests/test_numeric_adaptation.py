from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import PerformanceSnapshot, canonical_json, context_fingerprint
from app.domains.planning.execution_adaptation import AdaptationSignalConfidence, AdaptationSignalKind, build_execution_adaptation_context
from app.domains.planning.execution_proposals import ProposalDirection, ProposalKind, ProposalGuard, PrescriptionRange, build_execution_adaptation_proposal_context
from app.domains.planning.execution_evidence import TargetExecutionRelation
from app.domains.planning.numeric_adaptation import (
    NUMERIC_ADAPTATION_RESOLUTION_VERSION, NumericRange,
    NumericAdaptationAthleteMismatchError, NumericAdaptationCutoffMismatchError,
    NumericResolutionReason, NumericResolutionStatus, resolve_numeric_adaptations,
)
from app.domains.planning.planning_adaptation import normalize_numeric_planning_adaptation, with_planning_adaptation
from app.domains.planning.session_planning import SessionType
from app.domains.planning.season_structure import SeasonPhase
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_planning_adaptation import proposal_context
from tests.test_execution_adaptation import context as evidence_context, session as evidence_session
from tests.test_workout_builder import phase_targets, prescription, source
from tests.test_adaptive_targets import snapshot, point, with_snapshot

CONFIG = WorkoutBuilderConfig(version="0.8F.9", algorithm_version="0.8F.9")
PERFORMANCE = PerformanceSnapshot(
    running_threshold_pace_seconds_per_km=Decimal("250"),
    cycling_ftp_watts=Decimal("200"), swimming_css_seconds_per_100m=Decimal("110"),
)


def bundle(sport="running", session_type=SessionType.RUN_THRESHOLD, *, capability=False):
    context, original = source(PERFORMANCE)
    if capability:
        context = with_snapshot(context, snapshot(run=(point(120, 210), point(180, 215)),
                                                  bike=(point(180, 260),), swim=(point(100, 99), point(200, 102))))
    session = prescription(original, session_type, sport).model_copy(update={
        "phase": SeasonPhase.BUILD, "date": context.request.planning_date + timedelta(days=7),
    })
    return context, session, build_structured_workout(context, session, CONFIG)


def directional(context, session, *, increasing=True, confidence=AdaptationSignalConfidence.MEDIUM, **updates):
    kind = AdaptationSignalKind.PROGRESSION_CANDIDATE if increasing else AdaptationSignalKind.REGRESSION_CANDIDATE
    target_kind = {"running": "RUN_PACE", "cycling": "POWER", "swimming": "SWIM_PACE", "strength": None}[session.discipline]
    proposals = proposal_context(kind, sport=session.discipline, session_type=session.session_type.value,
                                 target_kind=target_kind, confidence=AdaptationSignalConfidence.HIGH)
    item = proposals.proposals[0].model_copy(update={"confidence": confidence, **updates})
    return proposals.model_copy(update={"athlete_profile_id": context.request.athlete_id,
                                        "as_of_date": context.request.planning_date, "proposals": (item,)})


def resolve(context, session, draft, proposals=None, **kwargs):
    return resolve_numeric_adaptations(context=context, prescriptions=(session,), drafts=(draft,),
                                      proposals=proposals or directional(context, session, **kwargs))


@pytest.mark.parametrize("sport,session_type", [
    ("running", SessionType.RUN_EASY), ("running", SessionType.RUN_THRESHOLD), ("running", SessionType.RUN_INTERVAL),
    ("cycling", SessionType.BIKE_EASY), ("cycling", SessionType.BIKE_THRESHOLD), ("cycling", SessionType.BIKE_INTERVAL),
    ("swimming", SessionType.SWIM_EASY), ("swimming", SessionType.SWIM_THRESHOLD), ("swimming", SessionType.SWIM_INTERVAL),
])
@pytest.mark.parametrize("increasing", [True, False])
@pytest.mark.parametrize("capability", [False, True])
def test_no_ordered_levels_never_invents_step_even_at_boundaries(sport, session_type, increasing, capability):
    context, session, draft = bundle(sport, session_type, capability=capability)
    result = resolve(context, session, draft, increasing=increasing)
    item = result.resolutions[0]
    assert item.status in {NumericResolutionStatus.NO_SAFE_STEP, NumericResolutionStatus.GUARDED}
    assert item.reason_codes[0] in {NumericResolutionReason.NO_ORDERED_TARGET_LEVELS, NumericResolutionReason.TARGET_AMBIGUOUS}
    assert item.proposed_range is None
    assert item.confidence == AdaptationSignalConfidence.MEDIUM
    assert item.numeric_policy_version == NUMERIC_ADAPTATION_RESOLUTION_VERSION
    if item.current_range:
        current = phase_targets(draft.definition)[0]
        assert item.current_range.minimum == Decimal(str(current.resolved_minimum))
        assert item.current_range.maximum == Decimal(str(current.resolved_maximum))
    projection = normalize_numeric_planning_adaptation(result)
    assert projection.planning_input is None
    assert with_planning_adaptation(context, projection.planning_input) is context
    assert build_structured_workout(context, session, CONFIG) == draft


def test_current_is_actual_adaptive_target_and_ignores_historical_range():
    context, session, draft = bundle(session_type=SessionType.RUN_INTERVAL, capability=True)
    target = phase_targets(draft.definition)[0]
    assert target.adaptation is not None
    proposals = directional(context, session, current_prescription=PrescriptionRange(minimum=500, maximum=600, unit="seconds_per_km"))
    item = resolve(context, session, draft, proposals).resolutions[0]
    assert item.current_range.minimum == Decimal(str(target.resolved_minimum))
    assert item.current_range.minimum != Decimal(str(target.adaptation.reference_based_minimum))
    assert item.proposed_range is None


@pytest.mark.parametrize("confidence", list(AdaptationSignalConfidence))
def test_confidence_is_preserved_and_gates_attempt(confidence):
    context, session, draft = bundle()
    item = resolve(context, session, draft, confidence=confidence).resolutions[0]
    assert item.confidence == confidence
    if confidence in {AdaptationSignalConfidence.LOW, AdaptationSignalConfidence.INSUFFICIENT}:
        assert item.reason_codes == (NumericResolutionReason.LOW_CONFIDENCE,)
    else:
        assert item.status == NumericResolutionStatus.NO_SAFE_STEP
    assert item.proposed_range is None


def replace_work_targets(draft, **updates):
    def visit(nodes):
        return [node.model_copy(update={"steps": visit(node.steps)}) if node.kind == "repeat" else
                node.model_copy(update={"target": node.target.model_copy(update=updates)}) if node.phase == "work" and node.target else node
                for node in nodes]
    return draft.model_copy(update={"definition": draft.definition.model_copy(update={"steps": visit(draft.definition.steps)})})


@pytest.mark.parametrize("updates,reason", [
    ({"resolved_unit": "watts"}, NumericResolutionReason.UNIT_MISMATCH),
    ({"resolved_minimum": -1}, NumericResolutionReason.INVALID_CURRENT_TARGET),
    ({"resolved_minimum": 999}, NumericResolutionReason.INVALID_CURRENT_TARGET),
    ({"resolved_minimum": float("nan")}, NumericResolutionReason.INVALID_CURRENT_TARGET),
    ({"resolved_minimum": None}, NumericResolutionReason.INVALID_CURRENT_TARGET),
])
def test_invalid_current_target_never_yields_range(updates, reason):
    context, session, draft = bundle()
    item = resolve(context, session, replace_work_targets(draft, **updates)).resolutions[0]
    assert item.reason_codes == (reason,)
    assert item.proposed_range is None


@pytest.mark.parametrize("updates,reason", [
    ({"target_kind": "POWER"}, NumericResolutionReason.UNIT_MISMATCH),
    ({"session_type": "BIKE_THRESHOLD"}, NumericResolutionReason.SESSION_TYPE_MISMATCH),
    ({"session_type": "RUN_UNKNOWN"}, NumericResolutionReason.SESSION_TYPE_MISMATCH),
    ({"proposed_direction": ProposalDirection.SLOWER_PACE}, NumericResolutionReason.DIRECTION_MISMATCH),
    ({"applied_guards": (ProposalGuard.EXTREME_OVERSHOOT,)}, NumericResolutionReason.SOURCE_GUARD),
])
def test_source_compatibility_and_guards(updates, reason):
    context, session, draft = bundle()
    item = resolve(context, session, draft, directional(context, session, **updates)).resolutions[0]
    assert item.reason_codes == (reason,)
    assert item.proposed_range is None


def test_strength_explicitly_not_applicable_even_if_directional():
    context, session, draft = bundle("strength", SessionType.GENERAL_STRENGTH)
    for kind in (ProposalKind.INSUFFICIENT_EVIDENCE, ProposalKind.INCREASE_TARGET):
        item = resolve(context, session, draft, directional(context, session, proposal_kind=kind)).resolutions[0]
        assert item.status == NumericResolutionStatus.NOT_APPLICABLE
        assert item.reason_codes == (NumericResolutionReason.STRENGTH_UNSUPPORTED,)


def test_identity_cutoff_and_base_context_are_enforced():
    context, session, draft = bundle()
    proposals = directional(context, session)
    with pytest.raises(NumericAdaptationAthleteMismatchError):
        resolve(context, session, draft, proposals.model_copy(update={"athlete_profile_id": UUID(int=999)}))
    with pytest.raises(NumericAdaptationCutoffMismatchError):
        resolve(context, session, draft, proposals.model_copy(update={"as_of_date": context.request.planning_date - timedelta(days=1)}))
    bad_context = context.model_copy(update={"adaptive_capability": snapshot().model_copy(update={"cutoff_date": context.request.planning_date - timedelta(days=1)})})
    with pytest.raises(NumericAdaptationCutoffMismatchError):
        resolve(bad_context, session, draft, proposals)
    with pytest.raises(ValueError, match="base context"):
        resolve(context, session, draft.model_copy(update={"context_fingerprint": "0" * 64}), proposals)
    with pytest.raises(ValueError, match="prescription"):
        resolve(context, session, draft.model_copy(update={"session_type": SessionType.RUN_EASY}), proposals)
    with pytest.raises(ValueError):
        resolve_numeric_adaptations(context=context, proposals=proposals, prescriptions=(session,), drafts=())


def test_conflicts_and_duplicates_are_order_independent_including_legacy_numeric_values():
    context, session, draft = bundle()
    first = directional(context, session)
    alternatives = [directional(context, session, increasing=False).proposals[0],
                    directional(context, session, confidence=AdaptationSignalConfidence.HIGH).proposals[0],
                    directional(context, session, current_prescription=PrescriptionRange(minimum=200, maximum=250, unit="seconds_per_km")).proposals[0]]
    for other in alternatives:
        results = [resolve(context, session, draft, first.model_copy(update={"proposals": items})) for items in
                   ((first.proposals[0], other), (other, first.proposals[0], other))]
        assert canonical_json(results[0]) == canonical_json(results[1])
        assert {item.status for item in results[0].resolutions} == {NumericResolutionStatus.CONFLICT}
        assert {item.status for item in normalize_numeric_planning_adaptation(results[0]).decisions} == {"SKIPPED_CONFLICT"}
    assert resolve(context, session, draft, first) == resolve(context, session, draft, first.model_copy(update={"proposals": first.proposals * 2}))


@pytest.mark.parametrize("minimum,maximum", [(0, 1), (-1, 2), (2, 1), (float("inf"), float("inf")), (float("nan"), 2)])
def test_numeric_range_validation(minimum, maximum):
    with pytest.raises(ValidationError):
        NumericRange(minimum=minimum, maximum=maximum, unit="watts")


@pytest.mark.parametrize("sport,session_type,relation,actual,partial", [
    ("running", SessionType.RUN_THRESHOLD, TargetExecutionRelation.FASTER_THAN_TARGET, 210, False),
    ("running", SessionType.RUN_THRESHOLD, TargetExecutionRelation.SLOWER_THAN_TARGET, 245, True),
    ("cycling", SessionType.BIKE_THRESHOLD, TargetExecutionRelation.ABOVE_POWER_TARGET, 190, False),
    ("swimming", SessionType.SWIM_THRESHOLD, TargetExecutionRelation.SLOWER_THAN_TARGET, 120, True),
])
def test_evidence_to_proposal_to_numeric_to_c4_to_preview(sport, session_type, relation, actual, partial):
    from app.domains.planning.execution_evidence import build_session_execution_evidence
    from tests.test_execution_evidence import planned, linked, workout, alternating
    from tests.test_planning_preview_artifact import artifact
    context, session, draft = bundle(sport, session_type)
    low, high, unit = {"running": (215, 229, "seconds_per_km"), "cycling": (164, 185, "watts"),
                       "swimming": (107, 113, "seconds_per_100m")}[sport]
    facts = []
    for index in range(1, 6):
        activity_id = UUID(int=index + 100)
        activity = linked(sport, duration=1440, activity_id=activity_id,
                          laps=alternating(activity_id, sport, [actual] * 8))
        prescription_evidence = planned(sport=sport, duration=1440, activities=(activity,),
                                               definition=workout(sport, low=low, high=high, unit=unit)).model_copy(update={
                                        "session_id": UUID(int=index), "session_type": session_type.value,
                                        "planned_date": context.request.planning_date - timedelta(days=index * 5)})
        fact = build_session_execution_evidence(prescription_evidence)
        assert fact.target_comparison.execution_relation == relation
        facts.append(fact)
    c1 = evidence_context(tuple(facts))
    c1 = c1.model_copy(update={"athlete_profile_id": context.request.athlete_id, "as_of_date": context.request.planning_date})
    c3 = build_execution_adaptation_proposal_context(build_execution_adaptation_context(c1))
    assert c3.proposals[0].proposal_kind in {ProposalKind.INCREASE_TARGET, ProposalKind.DECREASE_TARGET}
    c5 = resolve(context, session, draft, c3)
    assert c5.resolutions[0].status in {NumericResolutionStatus.NO_SAFE_STEP, NumericResolutionStatus.GUARDED}
    c4 = normalize_numeric_planning_adaptation(c5)
    assert c4.planning_input is None
    assert artifact(with_planning_adaptation(context, c4.planning_input)) == artifact(context)
    assert resolve(context, session, draft, c3).model_dump_json() == c5.model_dump_json()


def test_zero_evidence_preserves_preview():
    from tests.test_planning_preview_artifact import artifact
    context, session, draft = bundle()
    c1 = evidence_context().model_copy(update={"athlete_profile_id": context.request.athlete_id, "as_of_date": context.request.planning_date})
    c3 = build_execution_adaptation_proposal_context(build_execution_adaptation_context(c1))
    result = resolve(context, session, draft, c3)
    assert result.resolutions == ()
    assert artifact(with_planning_adaptation(context, normalize_numeric_planning_adaptation(result).planning_input)) == artifact(context)


def test_legacy_c4_hash_excludes_absent_numeric_version():
    from tests.test_planning_adaptation import planning_item
    context, _, _ = bundle()
    item = planning_item(context, sport="running", session_type="RUN_THRESHOLD", target_kind="RUN_PACE",
                         kind="INCREASE_TARGET", direction="FASTER_PACE",
                         current=(240, 260, "seconds_per_km"), proposed=(239, 259, "seconds_per_km"))
    legacy = item.model_dump(mode="python")
    legacy.pop("numeric_policy_version")
    for row in legacy["items"]:
        row.pop("numeric_policy_version")
    assert canonical_json(item) == canonical_json(legacy)
    assert context_fingerprint({"input": item}) == context_fingerprint({"input": legacy})


@pytest.mark.parametrize("case", ["zero", "run_progression", "run_regression", "bike_progression", "swim_regression"])
def test_normal_preview_generation_uses_c5_and_preserves_active_plan(monkeypatch, case):
    from sqlalchemy import select, event
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication
    from app.application.planning_context import PlanningContextAssembler
    from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
    from app.db.models import TrainingPlan, PlannedTrainingSession, StructuredWorkout
    from tests.test_planning_preview_application import seeded

    context, _, _ = bundle()
    engine, _, athlete_id, user_id, baseline_artifact = seeded()
    monkeypatch.setattr(PlanningContextAssembler, "assemble", lambda *args, **kwargs: context)
    empty = evidence_context().model_copy(update={"athlete_profile_id": athlete_id, "as_of_date": context.request.planning_date})
    monkeypatch.setattr(PrescribedCompletedEvidenceAssembler, "assemble", lambda *args, **kwargs: empty)
    captured = []
    real_resolver = resolve_numeric_adaptations

    def capture(**kwargs):
        statements = []

        def count(*args):
            statements.append(1)

        event.listen(engine, "before_cursor_execute", count)
        try:
            result = real_resolver(**kwargs)
            normalize_numeric_planning_adaptation(result)
            assert statements == []
        finally:
            event.remove(engine, "before_cursor_execute", count)
        captured.append(result)
        return result

    monkeypatch.setattr("app.application.planning_preview.resolve_numeric_adaptations", capture)
    with Session(engine) as db:
        active = TrainingPlan(athlete_profile_id=athlete_id, title="Existing active plan", status="active", origin="human",
                              start_date=baseline_artifact.plan_start, end_date=baseline_artifact.plan_end)
        db.add(active)
        db.commit()
        app = PlanningPreviewApplication(db)
        baseline = app.artifact(app.generate(request=context.request, user_id=user_id))
        if case != "zero":
            sport, kind, relation, actual, partial = {
                "run_progression": ("running", "RUN_THRESHOLD", TargetExecutionRelation.FASTER_THAN_TARGET, 210, False),
                "run_regression": ("running", "RUN_THRESHOLD", TargetExecutionRelation.SLOWER_THAN_TARGET, 245, True),
                "bike_progression": ("cycling", "BIKE_THRESHOLD", TargetExecutionRelation.ABOVE_POWER_TARGET, 190, False),
                "swim_regression": ("swimming", "SWIM_THRESHOLD", TargetExecutionRelation.SLOWER_THAN_TARGET, 120, True),
            }[case]
            evidence = empty.model_copy(update={"sessions": tuple(
                evidence_session(index, sport=sport, session_type=kind, relation=relation, actual=actual, partial=partial)
                .model_copy(update={"planned_date": context.request.planning_date - timedelta(days=index * 5)})
                for index in range(1, 6)
            )})
            monkeypatch.setattr(PrescribedCompletedEvidenceAssembler, "assemble", lambda *args, **kwargs: evidence)
        generated = app.artifact(app.generate(request=context.request, user_id=user_id))
        assert generated.model_dump_json() == baseline.model_dump_json()
        assert captured[-1].resolutions or case == "zero"
        assert all(item.proposed_range is None for item in captured[-1].resolutions)
        assert db.scalars(select(TrainingPlan)).all() == [active]
        assert active.status == "active" and active.title == "Existing active plan"
        assert db.scalars(select(PlannedTrainingSession)).all() == []
        assert db.scalars(select(StructuredWorkout)).all() == []
    engine.dispose()


@pytest.mark.parametrize("version", [None, "0.8G.2C.5"])
def test_stored_c4_numeric_artifacts_accept_without_recomputation(monkeypatch, version):
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication
    from tests.test_planning_adaptation import planning_item
    from tests.test_planning_preview_artifact import artifact
    from tests.test_planning_preview_application import seeded

    context, _, _ = bundle()
    baseline = artifact(context)
    candidate = next(item for item in baseline.sessions if item.prescription.discipline == "running" and item.workout.definition)
    current = phase_targets(candidate.workout.definition)[0]
    # Synthetic C.4 transport fixture only. C.5 never derives this test delta.
    item = planning_item(context, sport="running", session_type=candidate.prescription.session_type.value, target_kind="RUN_PACE",
                         kind="INCREASE_TARGET", direction="FASTER_PACE",
                         current=(current.resolved_minimum, current.resolved_maximum, current.resolved_unit),
                         proposed=(current.resolved_minimum - 1, current.resolved_maximum - 1, current.resolved_unit))
    item = item.model_copy(update={"numeric_policy_version": version, "items": tuple(row.model_copy(update={"numeric_policy_version": version}) for row in item.items)})
    stored = artifact(with_planning_adaptation(context, item))
    assert stored.fingerprint != baseline.fingerprint
    assert artifact(with_planning_adaptation(context, item)).fingerprint == stored.fingerprint
    engine, preview_id, athlete_id, user_id, _ = seeded(stored)

    def forbidden(*args, **kwargs):
        raise AssertionError("acceptance must not execute generation")

    for name in ("resolve_numeric_adaptations", "normalize_numeric_planning_adaptation", "build_structured_workout"):
        monkeypatch.setattr("app.application.planning_preview." + name, forbidden)
    monkeypatch.setattr("app.application.execution_proposals.ExecutionAdaptationProposalAssembler.assemble", forbidden)
    with Session(engine) as db:
        app = PlanningPreviewApplication(db)
        plan = app.accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        assert plan.source_preview_id == preview_id
        assert app.artifact(app.get(preview_id=preview_id, athlete_id=athlete_id)) == stored
    engine.dispose()


@pytest.mark.parametrize("changed", ["minimum", "maximum", "unit"])
def test_c4_rejects_even_a_near_current_target(changed):
    from tests.test_planning_adaptation import planning_item
    from app.domains.planning.planning_adaptation import apply_planning_adaptation

    context, session, draft = bundle()
    target = phase_targets(draft.definition)[0]
    item = planning_item(context, sport="running", session_type=session.session_type.value, target_kind="RUN_PACE",
                         kind="INCREASE_TARGET", direction="FASTER_PACE",
                         current=(target.resolved_minimum, target.resolved_maximum, target.resolved_unit),
                         proposed=(target.resolved_minimum - 1, target.resolved_maximum - 1, target.resolved_unit))
    field = "resolved_" + changed
    value = "seconds_per_100m" if changed == "unit" else getattr(target, field) + 0.001
    near = target.model_copy(update={field: value})
    result, decision = apply_planning_adaptation(target=near, context=with_planning_adaptation(context, item),
                                                sport="running", session_type=session.session_type.value, target_kind="RUN_PACE")
    assert result is near
    assert decision.status == "SKIPPED_GUARD"
    assert decision.reason == "CURRENT_TARGET_MISMATCH"
