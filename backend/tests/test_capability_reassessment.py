"""Synthetic evidence is test-only; no physiological reference is estimated."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import event

from app.application.capability_reassessment import CapabilityReassessmentAssembler
from app.db.models import AthletePerformanceProfileVersion, AthleteProfile, PlannedTrainingSession, StructuredWorkout
from app.domains.capability.reassessment import (
    CAPABILITY_REASSESSMENT_VERSION, CapabilityReassessmentContext, ReassessmentConfidence,
    ReassessmentReason as Reason, ReassessmentReferences, ReassessmentStatus as Status,
    SEMANTICS, build_capability_reassessment_context, snapshot_capability_target,
)
from app.domains.planning.contracts import PerformanceSnapshot, PlanningContext
from app.domains.planning.execution_adaptation import build_execution_adaptation_context
from app.domains.planning.execution_evidence import (
    ComparisonConfidence, CompletionStatus, TargetExecutionRelation as Relation,
    build_session_execution_evidence,
)
from tests.test_execution_adaptation import AS_OF, ATHLETE_ID, context, session, unmatched
from tests.test_execution_evidence import add_session, alternating, db, linked, planned, workout


def references(**updates):
    values = dict(cycling_ftp_watts=164, running_threshold_pace_seconds_per_km=215,
                  swimming_css_seconds_per_100m=107, source="manual", profile_version_id=UUID(int=50),
                  effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
    values.update(updates)
    return ReassessmentReferences(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
                                  performance=PerformanceSnapshot(**values))


def target_for(row):
    target = row.target_comparison
    if target is None:
        return None
    return snapshot_capability_target(athlete_profile_id=ATHLETE_ID,
        planned_session_id=row.planned_session_id, planned_date=row.planned_date,
        sport=row.sport, session_type=row.session_type,
        workout=workout(row.sport, reps=target.planned_repetitions,
                        low=float(target.planned_target_min), high=float(target.planned_target_max), unit=target.unit))


def rows(sport="running", n=3, **kwargs):
    kind = {"running": "RUN_INTERVAL", "cycling": "BIKE_INTERVAL", "swimming": "SWIM_THRESHOLD"}[sport]
    defaults = dict(relation=Relation.ABOVE_POWER_TARGET if sport == "cycling" else Relation.FASTER_THAN_TARGET,
                    actual={"cycling": 190, "running": 210, "swimming": 104}[sport])
    defaults.update(kwargs)
    return tuple(session(i, sport=sport, session_type=kind, **defaults).model_copy(
        update={"source_activity_ids": (UUID(int=100+i),)}) for i in range(1, n+1))


def run(items=(), *, refs=None, targets=None, **kwargs):
    evidence = context(items)
    return build_capability_reassessment_context(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
        evidence=evidence, adaptation=build_execution_adaptation_context(evidence), references=refs or references(),
        targets=tuple(target for item in items if (target := target_for(item)) is not None) if targets is None else targets,
        **kwargs)


def candidate(result, sport="running"):
    return next(item for item in result.candidates if item.sport == sport)


@pytest.mark.parametrize("sport", ["cycling", "running", "swimming"])
def test_repeated_anchored_evidence_recommends_only_remeasurement(sport):
    result = candidate(run(rows(sport)), sport)
    assert result.status == Status.REASSESSMENT_CANDIDATE
    assert result.confidence == ReassessmentConfidence.MEDIUM
    assert result.evidence.eligible_comparisons == result.evidence.recent == 3
    assert not any("proposed" in key or "delta" in key for key in result.model_dump())


@pytest.mark.parametrize("n", [0, 1, 2])
def test_zero_and_single_sessions_insufficient(n):
    result = candidate(run(rows(n=n)))
    assert result.status == Status.INSUFFICIENT_EVIDENCE
    assert result.confidence == ReassessmentConfidence.INSUFFICIENT


@pytest.mark.parametrize("mode", ["unknown", "unmatched", "low", "duration", "over_duration"])
def test_unreliable_or_global_completion_cannot_produce_candidate(mode):
    good = rows()
    if mode == "unmatched":
        bad = tuple(unmatched(i) for i in range(10, 14))
    else:
        bad = tuple(session(i, target=mode not in ("duration", "over_duration"),
                            confidence=ComparisonConfidence.LOW if mode == "low" else ComparisonConfidence.HIGH,
                            relation=Relation.UNKNOWN) for i in range(10, 14))
        if mode == "over_duration":
            bad = tuple(item.model_copy(update={"completion_status": CompletionStatus.OVER_DURATION,
                                                "actual_duration_seconds": 99999}) for item in bad)
    result = candidate(run((*good, *bad)))
    assert result.status == Status.INSUFFICIENT_EVIDENCE
    assert Reason.UNMATCHED_MAJORITY in result.reason_codes if mode == "unmatched" else Reason.UNKNOWN_MAJORITY in result.reason_codes


@pytest.mark.parametrize("sport,actual", [("cycling", 250), ("running", 150), ("swimming", 70)])
def test_extreme_overshoot_is_inconsistent(sport, actual):
    result = candidate(run(rows(sport, actual=actual)), sport)
    assert result.status == Status.INCONSISTENT_EVIDENCE
    assert Reason.EXTREME_OVERSHOOT_PRESENT in result.reason_codes


@pytest.mark.parametrize("relation", [Relation.SLOWER_THAN_TARGET, Relation.MIXED])
def test_adverse_or_mixed_evidence_never_prescribes_downgrade(relation):
    result = candidate(run(rows(relation=relation, actual=240)))
    assert result.status == Status.INCONSISTENT_EVIDENCE
    assert result.confidence == ReassessmentConfidence.LOW


def test_opposing_directions_and_recent_partials_block():
    good = rows()
    adverse = good[-1].model_copy(update={"target_comparison": good[-1].target_comparison.model_copy(
        update={"execution_relation": Relation.SLOWER_THAN_TARGET, "actual_representative_value": Decimal(240)})})
    assert candidate(run((*good[:2], adverse))).status == Status.INCONSISTENT_EVIDENCE
    partial = good[-1].model_copy(update={"completion_status": CompletionStatus.PARTIAL})
    result = candidate(run((*good[:2], partial)))
    assert result.status == Status.INSUFFICIENT_EVIDENCE
    assert Reason.RECENT_PARTIALS_PRESENT in result.reason_codes


@pytest.mark.parametrize("value", [None, 0, -1])
def test_invalid_reference_is_unavailable(value):
    result = candidate(run(rows(), refs=references(running_threshold_pace_seconds_per_km=value)))
    assert result.status == Status.REFERENCE_UNAVAILABLE
    assert result.current_reference is None


def test_age_is_context_only_and_profile_quality_is_not_invented():
    result = candidate(run(refs=references(effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc))))
    assert result.current_reference.age_days > 2000
    assert result.current_reference.source == "manual" and result.current_reference.quality is None
    assert result.status == Status.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("change", ["missing", "overlap", "reference", "value", "date", "type", "unit", "repetitions"])
def test_nonanchored_or_similar_target_never_contributes(change):
    good = rows()
    targets = tuple(target_for(item) for item in good)
    updates = {"overlap": {"minimum": Decimal(214)}, "reference": {"reference": "FTP"},
               "value": {"reference_value": Decimal(216)}, "date": {"planned_date": AS_OF},
               "type": {"session_type": "RUN_THRESHOLD"}, "unit": {"unit": "watts"},
               "repetitions": {"repetitions": 6}}
    targets = () if change == "missing" else tuple(item.model_copy(update=updates[change]) for item in targets)
    result = candidate(run(good, targets=targets))
    assert result.status == Status.INSUFFICIENT_EVIDENCE
    assert result.evidence.anchored_comparisons == 0


@pytest.mark.parametrize("session_type,sport", [("RUN_EASY", "running"), ("RUN_RECOVERY", "running"),
    ("SWIM_TECHNIQUE", "swimming"), ("GENERAL_STRENGTH", "strength")])
def test_excluded_session_types(session_type, sport):
    evidence = tuple(item.model_copy(update={"session_type": session_type, "sport": sport}) for item in rows())
    result = run(evidence, targets=())
    assert result.summary.candidate_count == 0
    assert all(item.evidence.quality_sessions == 0 for item in result.candidates)
    assert all(item.sport != "strength" for item in result.candidates)


@pytest.mark.parametrize("days,expected", [(0, 0), (-1, 0), (1, 3), (27, 3), (28, 0), (83, 0), (84, 0), (85, 0)])
def test_window_boundaries(days, expected):
    result = candidate(run(rows(days=days)))
    assert result.evidence.recent == expected
    assert result.evidence.background == (3 if days in (28, 83) else 0)
    assert result.status == (Status.REASSESSMENT_CANDIDATE if expected else Status.INSUFFICIENT_EVIDENCE)


def test_reference_effective_date_excludes_prior_reference_sessions():
    result = candidate(run(rows(), refs=references(effective_from=datetime(2026, 9, 5, tzinfo=timezone.utc))))
    assert result.evidence.anchored_comparisons == 0


@pytest.mark.parametrize("missing", [True, False])
def test_one_activity_or_missing_activity_provenance_cannot_prove_repetition(missing):
    evidence = tuple(item.model_copy(update={"source_activity_ids": () if missing else (UUID(int=99),)}) for item in rows())
    result = candidate(run(evidence))
    assert result.status == Status.INSUFFICIENT_EVIDENCE
    assert Reason.INDEPENDENT_ACTIVITIES_INSUFFICIENT in result.reason_codes


def test_confidence_determinism_roundtrip_and_immutability():
    evidence = rows(n=5)
    first = run(evidence)
    second = run(tuple(reversed(evidence)))
    assert first.model_dump_json() == second.model_dump_json()
    assert candidate(first).confidence == ReassessmentConfidence.HIGH
    assert CapabilityReassessmentContext.model_validate_json(first.model_dump_json()) == first
    assert first.algorithm_version == CAPABILITY_REASSESSMENT_VERSION
    with pytest.raises(ValidationError):
        first.algorithm_version = "changed"


@pytest.mark.parametrize("source", ["evidence", "references", "adaptation", "target"])
def test_cross_athlete_rejected(source):
    evidence = context(rows())
    refs = references()
    adaptation = build_execution_adaptation_context(evidence)
    targets = tuple(target_for(item) for item in evidence.sessions)
    wrong = {"athlete_profile_id": UUID(int=999)}
    if source == "evidence": evidence = evidence.model_copy(update=wrong)
    if source == "references": refs = refs.model_copy(update=wrong)
    if source == "adaptation": adaptation = adaptation.model_copy(update=wrong)
    if source == "target": targets = tuple(item.model_copy(update=wrong) for item in targets)
    with pytest.raises(ValueError, match="athlete"):
        build_capability_reassessment_context(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
            evidence=evidence, references=refs, adaptation=adaptation, targets=targets)


def test_stale_c2_and_duplicate_session_rejected():
    evidence = context(rows())
    with pytest.raises(ValueError, match="C.2"):
        build_capability_reassessment_context(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
            evidence=evidence, references=references(), adaptation=build_execution_adaptation_context(context()))
    with pytest.raises(ValueError, match="duplicate"):
        run((rows()[0], rows()[0]))


@pytest.mark.parametrize("sport,scenario", [("cycling", "candidate"), ("running", "candidate"),
    ("swimming", "candidate"), ("cycling", "inconsistent"), ("running", "missing"), ("swimming", "zero")])
def test_c1_laps_to_c2_to_c7_integration(sport, scenario):
    semantic = next(item for item in SEMANTICS if item[1] == sport)
    low, high, actual = {"cycling": (164, 185, 190), "running": (215, 229, 210), "swimming": (107, 113, 104)}[sport]
    if scenario == "inconsistent": actual = 250
    definition = workout(sport, reps=5, low=low, high=high, unit=semantic[4])
    evidence = []
    targets = []
    for index in (() if scenario == "zero" else range(1, 4)):
        activity_id = UUID(int=100+index)
        activity = linked(sport, duration=900, activity_id=activity_id,
                          laps=alternating(activity_id, sport, (actual,)*5))
        prescription = planned(sport=sport, duration=900, activities=(activity,), definition=definition).model_copy(
            update={"session_id": UUID(int=index), "planned_date": AS_OF-timedelta(days=index)})
        fact = build_session_execution_evidence(prescription)
        evidence.append(fact)
        targets.append(target_for(fact))
    refs = references(running_threshold_pace_seconds_per_km=None) if scenario == "missing" else references()
    result = candidate(run(tuple(evidence), targets=tuple(targets), refs=refs), sport)
    assert result.status == {"candidate": Status.REASSESSMENT_CANDIDATE,
        "inconsistent": Status.INCONSISTENT_EVIDENCE, "missing": Status.REFERENCE_UNAVAILABLE,
        "zero": Status.INSUFFICIENT_EVIDENCE}[scenario]
    assert result.evidence.eligible_comparisons == (0 if scenario in ("zero", "missing") else 3)
    # Duration/distance summaries cannot replace or overrule structured work laps.
    changed = tuple(item.model_copy(update={"actual_duration_seconds": 999999, "actual_distance_m": Decimal(999999)}) for item in evidence)
    assert candidate(run(changed, targets=tuple(targets), refs=refs), sport) == result


def test_c7_does_not_change_planning_or_any_preview_workout_fingerprint():
    from tests.test_planning_preview_artifact import artifact
    from tests.test_weekly_budget import context as planning_context
    ctx = planning_context()
    before = artifact(ctx).model_dump_json()
    context_before = ctx.model_dump_json()
    assert run(rows()).summary.candidate_count == 1
    assert artifact(ctx).model_dump_json() == before
    assert ctx.model_dump_json() == context_before
    assert "capability_reassessment" not in PlanningContext.model_fields


def test_assembler_zero_queries_with_supplied_context_and_no_autoflush(db):
    evidence = context(rows())
    db.add(AthleteProfile(display_name="pending", timezone="UTC", unit_system="metric"))
    statements = []
    def count(*args): statements.append(args[2])
    event.listen(db.bind, "before_cursor_execute", count)
    try:
        result = CapabilityReassessmentAssembler(db).assemble(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
            evidence=evidence, adaptation=build_execution_adaptation_context(evidence), capability=references(),
            targets=tuple(target_for(item) for item in evidence.sessions))
        assert result.summary.candidate_count == 1
        assert statements == [] and len(db.new) == 1
    finally:
        event.remove(db.bind, "before_cursor_execute", count)


def test_assembler_one_constant_input_query_is_scoped_and_preserves_missing_cases(db):
    athlete = AthleteProfile(id=ATHLETE_ID, display_name="A", timezone="UTC", unit_system="metric")
    other = AthleteProfile(id=UUID(int=2), display_name="B", timezone="UTC", unit_system="metric")
    db.add_all((athlete, other))
    db.flush()
    for athlete_id, value in ((athlete.id, 215), (other.id, 300)):
        db.add(AthletePerformanceProfileVersion(athlete_profile_id=athlete_id,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc), data_origin="manual", algorithm_version="test",
            running_threshold_pace_seconds_per_km=value))
    for row in rows():
        db.add(PlannedTrainingSession(id=row.planned_session_id, athlete_profile_id=ATHLETE_ID,
            scheduled_date=row.planned_date, timezone="UTC", sport=row.sport, title=row.session_type,
            origin="human", planned_duration_seconds=3600))
        db.add(StructuredWorkout(planned_training_session_id=row.planned_session_id, schema_version=1,
            definition=workout(reps=5).model_dump(mode="json")))
    db.flush()
    statements = []
    def count(*args): statements.append(args[2])
    event.listen(db.bind, "before_cursor_execute", count)
    try:
        result = CapabilityReassessmentAssembler(db).assemble(athlete_profile_id=ATHLETE_ID,
            as_of_date=AS_OF, evidence=context(rows()))
        assert len(statements) == 1
        assert candidate(result).current_reference.value == 215
        assert result.summary.candidate_count == 1
        statements.clear()
        empty = CapabilityReassessmentAssembler(db).assemble(athlete_profile_id=UUID(int=999), as_of_date=AS_OF)
        assert len(statements) == 2  # empty C.1 + one profile/provenance statement
        assert empty.summary.unavailable_count == 3
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)


@pytest.mark.parametrize("n", [1, 8])
def test_standalone_c1_plus_c7_query_budget_constant(db, n):
    athlete = AthleteProfile(id=ATHLETE_ID, display_name="A", timezone="UTC", unit_system="metric")
    db.add(athlete)
    db.flush()
    for index in range(n):
        add_session(db, athlete, day=AS_OF-timedelta(days=index+1), definition=workout())
    statements = []
    def count(*args): statements.append(args[2])
    event.listen(db.bind, "before_cursor_execute", count)
    try:
        result = CapabilityReassessmentAssembler(db).assemble(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF)
        assert len(statements) == 4
        assert result.summary.session_count == n
        assert sum("FROM activity_laps" in sql for sql in statements) == 1
        assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
    finally:
        event.remove(db.bind, "before_cursor_execute", count)


def test_target_confidence_cannot_be_promoted_by_session_confidence():
    evidence = tuple(item.model_copy(update={"target_comparison": item.target_comparison.model_copy(
        update={"confidence": ComparisonConfidence.MEDIUM})}) for item in rows(n=5))
    assert candidate(run(evidence)).confidence == ReassessmentConfidence.MEDIUM


def test_within_target_means_no_reassessment_needed():
    assert candidate(run(rows(relation=Relation.WITHIN_TARGET, actual=220))).status == Status.NO_REASSESSMENT_NEEDED


def test_recent_and_background_thresholds_and_directional_fraction():
    good = rows(n=4)
    background = tuple(item.model_copy(update={"planned_date": AS_OF-timedelta(days=40)}) for item in good[2:])
    result = candidate(run((*good[:2], *background)))
    assert result.status == Status.REASSESSMENT_CANDIDATE
    assert result.evidence.recent == result.evidence.background == 2
    within = good[-1].model_copy(update={"target_comparison": good[-1].target_comparison.model_copy(
        update={"execution_relation": Relation.WITHIN_TARGET, "actual_representative_value": Decimal(220)})})
    # C.2 deliberately uses .67: two of three does not round up to .67.
    assert candidate(run((*good[:2], within))).status == Status.NO_REASSESSMENT_NEEDED
    assert candidate(run((*good[:3], within))).status == Status.REASSESSMENT_CANDIDATE


def test_capability_without_target_provenance_fails_closed_with_zero_queries(db):
    statements = []
    def count(*args): statements.append(args[2])
    event.listen(db.bind, "before_cursor_execute", count)
    try:
        result = CapabilityReassessmentAssembler(db).assemble(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
            evidence=context(rows()), capability=references())
        assert statements == []
        assert candidate(result).status == Status.INSUFFICIENT_EVIDENCE
    finally:
        event.remove(db.bind, "before_cursor_execute", count)


def test_acceptance_never_invokes_c7(monkeypatch):
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication
    from tests.test_planning_preview_application import seeded
    def forbidden(*args, **kwargs): raise AssertionError("acceptance must not recompute C.7")
    monkeypatch.setattr(CapabilityReassessmentAssembler, "assemble", forbidden)
    engine, preview_id, athlete_id, user_id, source = seeded()
    try:
        with Session(engine) as db:
            accepted = PlanningPreviewApplication(db).accept(preview_id=preview_id, athlete_id=athlete_id,
                                                            user_id=user_id, role="athlete")
            assert accepted.source_preview_id == preview_id
    finally:
        engine.dispose()


def test_existing_capability_context_reuses_only_reference_without_queries(db):
    from app.domains.capability.analysis import build_capability_context
    capability = build_capability_context(athlete_id=ATHLETE_ID, as_of_date=AS_OF,
        activities=(), laps=(), performance=references().performance)
    result = CapabilityReassessmentAssembler(db).assemble(athlete_profile_id=ATHLETE_ID,
        as_of_date=AS_OF, evidence=context(rows()), capability=capability,
        targets=tuple(target_for(item) for item in rows()))
    assert result == run(rows())


@pytest.mark.parametrize("field", ["as_of_date", "window_start_date"])
def test_cutoff_and_window_mismatch_rejected(field):
    evidence = context().model_copy(update={field: AS_OF-timedelta(days=1)})
    with pytest.raises(ValueError, match="mismatch"):
        build_capability_reassessment_context(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
            evidence=evidence, references=references())


def test_no_ladder_is_independent_of_reassessment():
    from app.domains.planning.prescription_intensity import build_prescription_intensity_ladder
    from tests.test_numeric_adaptation import bundle
    ctx, prescription, _ = bundle()
    before = build_prescription_intensity_ladder(context=ctx, sport="running",
        session_type=prescription.session_type.value, target_kind="RUN_PACE")
    assert before.status == "NO_SUPPORTED_LADDER"
    assert run().summary.candidate_count == 0
    assert run(rows()).summary.candidate_count == 1
    assert build_prescription_intensity_ladder(context=ctx, sport="running",
        session_type=prescription.session_type.value, target_kind="RUN_PACE") == before


def test_snapshot_rejects_adapted_and_fallback_targets_and_matches_first_comparison():
    from app.domains.planning.models import WorkoutTargetAdaptation
    definition = workout(reps=5)
    target = definition.steps[0].steps[0].target
    target.adaptation = WorkoutTargetAdaptation(algorithm_version="test", reference_based_minimum=215,
        reference_based_maximum=229, capability_dimension=120, capability_value=210, confidence="HIGH",
        days_since_evidence=1, blend_factor=.5, repeat_factor=1, final_minimum=215, final_maximum=229)
    def snapshot():
        return snapshot_capability_target(athlete_profile_id=ATHLETE_ID, planned_session_id=UUID(int=1),
            planned_date=AS_OF-timedelta(days=1), sport="running", session_type="RUN_INTERVAL", workout=definition)
    assert snapshot() is None
    target.adaptation = None
    target.reference_value = None
    assert snapshot() is None
