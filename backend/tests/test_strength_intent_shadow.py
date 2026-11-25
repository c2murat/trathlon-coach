from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import context_fingerprint
from app.domains.planning.strength_intent import build_strength_shadow, StructuredStrengthShadowReport
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_endurance_volume_authority import pipeline
from tests.test_structural_weekly_intent import inputs
from tests.test_weekly_intent_shadow import profile_context


@pytest.fixture(scope="module")
def observed():
    ctx = profile_context()
    artifact, _, volume = pipeline(ctx)
    config = inputs(ctx)[2]
    before = artifact.model_dump_json()
    report = build_strength_shadow(ctx, artifact, config)
    assert artifact.model_dump_json() == before
    return ctx, artifact, volume, config, report


def test_shadow_preserves_artifact_and_workout_bytes_and_fingerprints(observed):
    ctx, artifact, volume, config, report = observed
    before = artifact.model_dump_json()
    for _ in range(2):
        rebuilt = build_strength_shadow(ctx, artifact, config)
        assert rebuilt.model_dump_json() == report.model_dump_json()
    assert artifact.model_dump_json() == before
    assert report.artifact_fingerprint == artifact.fingerprint
    assert "strength_shadow" not in artifact.model_dump_json()
    wc = WorkoutBuilderConfig(version="test", algorithm_version="test")
    for session in artifact.sessions:
        assert session.workout.model_dump_json() == build_structured_workout(ctx,session.prescription,wc).model_dump_json()


def test_missing_independent_timing_never_invents_duration(observed):
    for week in observed[-1].weeks:
        for session in week.sessions:
            assert session.structured_estimated_duration_minutes is None
            assert session.estimated_working_seconds is None
            assert session.estimated_rest_seconds is None
            assert session.estimated_transition_seconds is None
            assert session.variance_minutes is None
            assert session.confidence == "UNAVAILABLE"
            assert session.selected_duration_minutes == session.legacy_duration_minutes == 24
            assert session.fallback_reason == "INSUFFICIENT_INDEPENDENT_TIMING_POLICY"
            assert "REST_SCOPE_AND_INCLUSION_SEMANTICS" in session.missing_data
            assert session.warmup_intent is None and session.cooldown_intent is None


def test_two_sessions_are_observations_not_new_a_b_roles(observed):
    first = observed[-1].weeks[0]
    assert len(first.sessions) == 2
    a,b = first.sessions
    assert a.role == b.role == "GENERAL_STRENGTH"
    assert (a.occurrence,b.occurrence) == (1,2)
    assert first.same_structure_within_week is True
    assert a.structure == b.structure
    assert first.strength_minutes_target == first.placed_strength_minutes == 48
    assert a.structure.nominal_sets == 18
    assert a.structure.nominal_repetitions == 180  # no unilateral doubling
    assert a.structure.exercises[2].unilateral is True
    assert a.structure.exercises[2].target_rpe == (Decimal(5),Decimal(7))


def test_existing_progression_and_previous_structure_are_recorded(observed):
    weeks = observed[-1].weeks
    assert weeks[0].sessions[0].previous_structure is None
    assert weeks[1].sessions[0].previous_structure == weeks[0].sessions[0].structure
    assert weeks[1].sessions[0].structure.variant_index == 1
    assert weeks[0].sessions[0].structure.variant_index == 0
    assert weeks[1].sessions[0].structure.nominal_repetitions == 144
    for week in weeks:
        for session in week.sessions:
            assert session.proposed_structure == session.final_structure == session.structure
            assert session.structure_cap is None and session.structure_floor is None
            assert session.progression_source == "workout_builder._progression_level/_strength_steps"
            assert session.provenance


@pytest.mark.parametrize("phase,exercises,sets,reps,rest,rpe", [
    ("BASE",6,3,10,90,(5,7)),("BUILD",6,3,10,90,(5,7)),
    ("RECOVERY",4,2,10,60,(4,6)),("TAPER",3,2,6,60,(4,6)),
    ("COMPETITION",6,3,10,90,(5,7)),("SPECIFIC",5,3,8,90,(5,7)),
])
def test_actual_phase_profiles_are_observed_not_reimplemented(observed,phase,exercises,sets,reps,rest,rpe):
    from app.domains.planning.season_structure import SeasonPhase
    ctx, artifact, _, config, _ = observed
    target = next(x for x in artifact.sessions if x.prescription.discipline == "strength")
    prescription = target.prescription.model_copy(update={"phase": SeasonPhase(phase)})
    draft = build_structured_workout(ctx,prescription,WorkoutBuilderConfig(version="test",algorithm_version="test"))
    sample = target.model_copy(update={"prescription":prescription,"workout":draft})
    report = build_strength_shadow(ctx,artifact.model_copy(update={"sessions":(sample,)}),config)
    session = report.weeks[0].sessions[0]
    assert session.phase == phase
    assert session.structure.exercise_count == exercises
    assert all(e.sets == sets and e.reps == reps and e.rest_seconds == rest and e.target_rpe == tuple(map(Decimal,rpe)) for e in session.structure.exercises)
    assert session.structured_estimated_duration_minutes is None


def test_fallback_without_structure_or_repetitions(observed):
    ctx,artifact,_,config,_ = observed
    target = next(x for x in artifact.sessions if x.prescription.discipline == "strength")
    empty = target.model_copy(update={"workout":target.workout.model_copy(update={"definition":None})})
    report = build_strength_shadow(ctx,artifact.model_copy(update={"sessions":(empty,)}),config)
    session = report.weeks[0].sessions[0]
    assert session.fallback_reason == "STRENGTH_STRUCTURE_UNAVAILABLE"
    assert session.content_source == "WORKOUT_STRUCTURE_UNAVAILABLE"
    assert session.selected_duration_minutes == 24
    two_empty = tuple(x.model_copy(update={"workout":x.workout.model_copy(update={"definition":None})})
        for x in artifact.sessions if x.prescription.discipline == "strength")
    unknown = build_strength_shadow(ctx,artifact.model_copy(update={"sessions":two_empty}),config)
    assert unknown.weeks[0].same_structure_within_week is None
    nodes = target.workout.definition.steps
    changed = target.model_copy(update={"workout":target.workout.model_copy(update={"definition":target.workout.definition.model_copy(
        update={"steps":[n.model_copy(update={"reps":None}) for n in nodes]})})})
    report = build_strength_shadow(ctx,artifact.model_copy(update={"sessions":(changed,)}),config)
    s = report.weeks[0].sessions[0]
    assert s.structure.nominal_repetitions is None
    assert "REPETITIONS_OR_EXPLICIT_HOLD_TIME" in s.missing_data
    assert s.structured_estimated_duration_minutes is None


def test_allocated_node_time_is_not_a_structural_estimate(observed):
    ctx,artifact,_,config,report = observed
    target = next(x for x in artifact.sessions if x.prescription.discipline == "strength")
    nodes = [n.model_copy(update={"duration":n.duration.model_copy(update={"seconds":10000})}) for n in target.workout.definition.steps]
    changed = target.model_copy(update={"workout":target.workout.model_copy(update={"definition":target.workout.definition.model_copy(update={"steps":nodes})})})
    s = build_strength_shadow(ctx,artifact.model_copy(update={"sessions":(changed,)}),config).weeks[0].sessions[0]
    assert s.structure.fingerprint == report.weeks[0].sessions[0].structure.fingerprint
    assert s.structured_estimated_duration_minutes is None
    assert s.selected_duration_minutes == 24


def test_block4a_and_doubles_capacity_are_not_changed(observed):
    ctx,artifact,volume,config,report = observed
    before = artifact.model_dump_json()
    build_strength_shadow(ctx,artifact,config)
    assert artifact.model_dump_json() == before
    for strength_week, volume_week in zip(report.weeks,volume.weeks,strict=True):
        assert strength_week.strength_minutes_target == volume_week.intent.strength_minutes_target
        assert strength_week.placed_strength_minutes <= strength_week.strength_minutes_target
    assert not any(w.daily_violations for w in volume.weeks)
    assert volume.mode == "ENDURANCE_VOLUME_AUTHORITY_STRENGTH_LEGACY"


def test_report_is_immutable_roundtrips_and_athlete_scoped(observed):
    ctx,artifact,_,config,report = observed
    assert StructuredStrengthShadowReport.model_validate_json(report.model_dump_json()) == report
    with pytest.raises(ValidationError):
        report.weeks[0].sessions[0].role = "OTHER"
    other = UUID("20000000-0000-0000-0000-000000000002")
    new_ctx = ctx.model_copy(update={"request":ctx.request.model_copy(update={"athlete_id":other})})
    new_ctx = new_ctx.model_copy(update={"fingerprint":context_fingerprint(new_ctx.model_dump(exclude={"fingerprint"}))})
    other_artifact = pipeline(new_ctx)[0]
    result = build_strength_shadow(new_ctx,other_artifact,config)
    assert result.athlete_id == other
    assert all(s.athlete_id == other for w in result.weeks for s in w.sessions)
    assert result.context_fingerprint != report.context_fingerprint


def test_no_history_uses_explicit_config_fallback():
    ctx = profile_context()
    windows = tuple(w.model_copy(update={"sports":tuple(s for s in w.sports if s.sport != "strength")}) if w.days == 28 else w for w in ctx.training.windows)
    ctx = ctx.model_copy(update={"training":ctx.training.model_copy(update={"windows":windows})})
    artifact = pipeline(ctx)[0]
    report = build_strength_shadow(ctx,artifact,inputs(ctx)[2])
    first = report.weeks[0].sessions[0]
    assert first.legacy_duration_basis == "CONFIG_DEFAULT_WITHOUT_USABLE_HISTORY"
    assert first.selected_duration_minutes == 40
    assert first.structured_estimated_duration_minutes is None


def test_foreign_athlete_or_context_rejected(observed):
    ctx,artifact,_,config,_ = observed
    other = ctx.model_copy(update={"request":ctx.request.model_copy(update={"athlete_id":UUID(int=2)})})
    with pytest.raises(ValueError,match="CONTEXT_MISMATCH"):
        build_strength_shadow(other,artifact,config)


@pytest.mark.parametrize("target",[None,6])
def test_application_diagnostics_are_ephemeral_and_reset(monkeypatch,target):
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication, PlanningContextAssembler, ExecutionAdaptationProposalAssembler
    from app.domains.planning.execution_adaptation import build_execution_adaptation_context
    from app.domains.planning.execution_proposals import build_execution_adaptation_proposal_context
    from tests.test_execution_adaptation import context as evidence_context
    from tests.test_planning_preview_application import seeded
    ctx = profile_context()
    ctx = ctx.model_copy(update={"preferences":ctx.preferences.model_copy(update={"target_sessions_per_week":target})})
    evidence = evidence_context().model_copy(update={"athlete_profile_id":ctx.request.athlete_id,"as_of_date":ctx.request.planning_date})
    proposals = build_execution_adaptation_proposal_context(build_execution_adaptation_context(evidence))
    monkeypatch.setattr(PlanningContextAssembler,"assemble",lambda *a,**k:ctx)
    monkeypatch.setattr(ExecutionAdaptationProposalAssembler,"assemble",lambda *a,**k:proposals)
    engine,_,_,user,_ = seeded()
    with Session(engine) as session:
        app = PlanningPreviewApplication(session)
        row = app.generate(request=ctx.request,user_id=user)
        assert app.strength_shadow_report is not None
        assert app.strength_shadow_report.artifact_fingerprint == row.artifact_fingerprint
        assert "strength_shadow" not in row.artifact
        assert "strength_shadow_report" not in row.artifact
        monkeypatch.setattr(PlanningContextAssembler,"assemble",lambda *a,**k:(_ for _ in ()).throw(ValueError("unavailable")))
        with pytest.raises(ValueError,match="unavailable"):
            app.generate(request=ctx.request,user_id=user)
        assert app.strength_shadow_report is None


def test_actual_swim_strength_double_keeps_capacity_and_content():
    from collections import defaultdict
    from app.domains.planning.session_compatibility import pair_cost
    ctx = profile_context()
    prefs = ctx.preferences.model_copy(update={"availability_slots":tuple(s for s in ctx.preferences.availability_slots if s.weekday != 3)})
    ctx = ctx.model_copy(update={"preferences":prefs})
    artifact,_,volume = pipeline(ctx)
    before = artifact.model_dump_json()
    report = build_strength_shadow(ctx,artifact,inputs(ctx)[2])
    assert artifact.model_dump_json() == before
    paired = False
    for week in artifact.session_plan.weeks:
        days = defaultdict(list)
        for p in week.sessions:
            if p.discipline != "competition":days[p.date].append(p)
        for day,group in days.items():
            slot = next(s for s in prefs.availability_slots if s.weekday == day.weekday())
            assert len(group)<=prefs.max_sessions_per_day
            assert sum(s.target_duration_minutes for s in group)<=slot.available_minutes
            if len(group)==2:
                assert pair_cost(*group,ctx) is not None
                paired |= {s.discipline for s in group}=={"strength","swimming"}
    assert paired
    assert all(s.structured_estimated_duration_minutes is None for w in report.weeks for s in w.sessions)


def test_distribution_anchor_is_used_for_existing_progression(observed):
    from datetime import timedelta
    ctx,artifact,_,config,_ = observed
    item = next(x for x in artifact.sessions if x.prescription.discipline == "strength")
    p = item.prescription
    moved = p.date+timedelta(days=7)
    placement = p.placement.model_copy(update={"code":"WEEKLY_STRUCTURAL_DISTRIBUTION","context":{
        "original_date":p.date.isoformat(),"distributed_date":moved.isoformat()}})
    changed = item.model_copy(update={"prescription":p.model_copy(update={"date":moved,"placement":placement})})
    report = build_strength_shadow(ctx,artifact.model_copy(update={"sessions":(changed,)}),config)
    s = next(s for w in report.weeks for s in w.sessions)
    assert s.content_anchor_date==p.date
    assert s.scheduled_date==moved
    assert s.progression_level==0
