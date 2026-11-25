"""All numeric timing ranges here are synthetic test data, never defaults."""
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import context_fingerprint
from app.domains.planning.strength_timing import (
    SecondsInterval, TimingProvenance, TimingComponent, PauseTiming, ExerciseTiming,
    TransitionTiming, StrengthTimingSnapshot, estimate_strength_timing, empty_timing_snapshot,
    build_strength_timing_shadow, definition_fingerprint,
)
from tests.test_endurance_volume_authority import pipeline
from tests.test_weekly_intent_shadow import profile_context


P = TimingProvenance(source="explicit_prescription",source_id="synthetic-test-only",version="test-1")


def specified(a,b):
    return TimingComponent(state="specified",seconds=SecondsInterval(minimum=a,maximum=b),provenance=P)


def absent():
    return TimingComponent(state="not_prescribed",provenance=P)


@pytest.fixture(scope="module")
def source():
    ctx=profile_context()
    artifact=pipeline(ctx)[0]
    workout=next(s.workout for s in artifact.sessions if s.prescription.discipline=="strength")
    return ctx,artifact,workout


def complete(ctx,workout):
    s=empty_timing_snapshot(ctx,workout)
    exercises=tuple(ExerciseTiming(node_path=(i,),execution_per_set=specified(10,20),sets_scope="all_sides_included",
        pauses=(PauseTiming(after_sets=tuple(range(1,n.sets)),timing=specified(30,40)),))
        for i,n in enumerate(workout.definition.steps))
    transitions=tuple(TransitionTiming(after_node_path=(i,),before_node_path=(i+1,),timing=specified(5,10))
        for i in range(len(exercises)-1))
    return s.model_copy(update={"exercises":exercises,"transitions":transitions,"warmup":specified(60,90),"cooldown":specified(10,20)})


def test_no_snapshot_or_empty_snapshot_is_unavailable(source):
    ctx,_,w=source
    for s in (None,empty_timing_snapshot(ctx,w)):
        r=estimate_strength_timing(ctx,w,s)
        assert r.coverage=="unavailable"
        assert r.duration_seconds is None
        assert r.known_subtotal_seconds.minimum==r.known_subtotal_seconds.maximum==0
        assert not r.known_components and r.missing_components
        assert r.validation_state=="not_evaluated"
        assert "NO_INDEPENDENT_TIMING_DATA" in r.diagnostics


def test_complete_interval_is_sum_of_disjoint_components_not_midpoint(source):
    ctx,_,w=source
    r=estimate_strength_timing(ctx,w,complete(ctx,w))
    assert r.coverage=="complete"
    assert (r.duration_seconds.minimum,r.duration_seconds.maximum)==(635,1000)
    assert r.known_subtotal_seconds==r.duration_seconds
    assert not r.missing_components
    assert r.validation_state=="not_evaluated"  # completeness is not calibration
    assert "confidence" not in r.model_dump()
    assert "midpoint" not in r.model_dump()
    assert len({c.component_id for c in r.known_components})==len(r.known_components)


def test_unknown_is_not_zero_or_not_prescribed(source):
    ctx,_,w=source
    s=complete(ctx,w)
    unknown=s.model_copy(update={"warmup":TimingComponent()})
    r=estimate_strength_timing(ctx,w,unknown)
    assert r.coverage=="partial" and r.duration_seconds is None
    assert "warmup_whole_prefix" in r.missing_components
    zero=estimate_strength_timing(ctx,w,s.model_copy(update={"warmup":absent()}))
    assert zero.coverage=="complete"
    assert (zero.duration_seconds.minimum,zero.duration_seconds.maximum)==(575,910)


def test_partial_keeps_only_known_subtotal(source):
    ctx,_,w=source
    s=empty_timing_snapshot(ctx,w).model_copy(update={"warmup":specified(60,90)})
    r=estimate_strength_timing(ctx,w,s)
    assert r.coverage=="partial" and r.duration_seconds is None
    assert (r.known_subtotal_seconds.minimum,r.known_subtotal_seconds.maximum)==(60,90)
    # No use of rest_seconds=90 from the workout, allocated time, or RPE.
    assert len(r.known_components)==1
    assert any("execution" in key for key in r.missing_components)


def test_explicit_known_absence_is_partial_even_with_zero_subtotal(source):
    ctx,_,w=source
    s=empty_timing_snapshot(ctx,w).model_copy(update={"warmup":absent()})
    r=estimate_strength_timing(ctx,w,s)
    assert r.coverage=="partial" and r.known_subtotal_seconds.maximum==0
    assert r.duration_seconds is None


@pytest.mark.parametrize("a,b",[(-1,1),(2,1),(True,2),(1.5,2),("1",2)])
def test_invalid_ranges_rejected(a,b):
    with pytest.raises(ValidationError):SecondsInterval(minimum=a,maximum=b)


def test_units_and_provenance_are_required_and_independent():
    with pytest.raises(ValidationError):SecondsInterval(minimum=1,maximum=2,unit="minutes")
    with pytest.raises(ValidationError):TimingComponent(state="specified",seconds=SecondsInterval(minimum=1,maximum=2))
    with pytest.raises(ValidationError):TimingComponent(state="not_prescribed")
    with pytest.raises(ValidationError):TimingComponent(state="unknown",seconds=SecondsInterval(minimum=0,maximum=0))
    with pytest.raises(ValidationError):TimingProvenance(source="historical_duration",source_id="x",version="1")
    with pytest.raises(ValidationError):TimingProvenance(source="explicit_prescription",source_id=" ",version="1")
    with pytest.raises(ValidationError):ExerciseTiming(node_path=(0,),execution_per_set=specified(0,10),sets_scope="all_sides_included")


def test_duplicate_or_overlapping_components_rejected(source):
    ctx,_,w=source
    s=complete(ctx,w)
    with pytest.raises(ValidationError):PauseTiming(after_sets=(1,1),timing=specified(1,2))
    with pytest.raises(ValidationError):ExerciseTiming(node_path=(0,),sets_scope="all_sides_included",pauses=(
        PauseTiming(after_sets=(1,),timing=specified(1,2)),PauseTiming(after_sets=(1,2),timing=specified(1,2))))
    data=s.model_dump()
    data["exercises"]=data["exercises"]+(data["exercises"][0],)
    with pytest.raises(ValidationError):StrengthTimingSnapshot.model_validate(data)
    data=s.model_dump()
    data["transitions"]=data["transitions"]+(data["transitions"][0],)
    with pytest.raises(ValidationError):StrengthTimingSnapshot.model_validate(data)


@pytest.mark.parametrize("after",[3,4])
def test_final_set_pause_cannot_overlap_whole_gap_or_tail(source,after):
    ctx,_,w=source
    s=complete(ctx,w)
    e=s.exercises[0].model_copy(update={"pauses":(PauseTiming(after_sets=(after,),timing=specified(30,40)),)})
    r=estimate_strength_timing(ctx,w,s.model_copy(update={"exercises":(e,)+s.exercises[1:]}))
    assert r.coverage=="unavailable" and not r.known_components
    assert r.diagnostics==("INVALID_PAUSE_OCCURRENCE_FINAL_SET_OR_OUT_OF_RANGE",)


def test_unknown_unilateral_scope_does_not_guess_multiplier(source):
    ctx,_,w=source
    s=empty_timing_snapshot(ctx,w)
    e=ExerciseTiming(node_path=(2,),execution_per_set=specified(10,20))
    r=estimate_strength_timing(ctx,w,s.model_copy(update={"exercises":(e,)}))
    assert r.coverage=="unavailable"
    assert "steps[2].execution_scope" in r.missing_components
    with pytest.raises(ValidationError):ExerciseTiming(node_path=(2,),sets_scope="per_side")
    with pytest.raises(ValidationError):ExerciseTiming(node_path=(2,),sets_scope="all_sides_included",side_count=2)


def test_declared_sides_are_counted_once_and_bilateral_conflict_rejected(source):
    ctx,_,w=source
    s=complete(ctx,w)
    original=s.exercises[2]
    e=ExerciseTiming(node_path=(2,),execution_per_set=specified(10,20),sets_scope="per_side",side_count=2,
        pauses=(PauseTiming(after_sets=(1,2,3,4,5),timing=absent()),))
    changed=s.model_copy(update={"exercises":s.exercises[:2]+(e,)+s.exercises[3:]})
    r=estimate_strength_timing(ctx,w,changed)
    work=next(k for k in r.known_components if k.component_id=="steps[2].execution")
    assert work.occurrences==6
    assert (work.seconds.minimum,work.seconds.maximum)==(60,120)
    # all_sides_included never multiplied by workout.unilateral=True
    old=estimate_strength_timing(ctx,w,s)
    assert next(k for k in old.known_components if k.component_id=="steps[2].execution").occurrences==3
    bad=e.model_copy(update={"node_path":(0,)})
    r=estimate_strength_timing(ctx,w,s.model_copy(update={"exercises":(bad,)+s.exercises[1:]}))
    assert r.diagnostics==("UNILATERAL_SCOPE_CONFLICT",)


@pytest.mark.parametrize("field,value",[("athlete_id",UUID(int=99)),("context_fingerprint","b"*64),
    ("workout_fingerprint","c"*64),("definition_fingerprint","d"*64)])
def test_wrong_snapshot_identity_never_reuses_partial_values(source,field,value):
    ctx,_,w=source
    r=estimate_strength_timing(ctx,w,complete(ctx,w).model_copy(update={field:value}))
    assert r.coverage=="unavailable" and r.duration_seconds is None
    assert not r.known_components
    assert r.diagnostics==("TIMING_SNAPSHOT_BINDING_MISMATCH",)


def test_wrong_node_and_nonadjacent_transition_rejected(source):
    ctx,_,w=source
    s=complete(ctx,w)
    e=s.exercises[0].model_copy(update={"node_path":(999,)})
    r=estimate_strength_timing(ctx,w,s.model_copy(update={"exercises":(e,)+s.exercises[1:]}))
    assert r.diagnostics==("TIMING_NODE_PATH_OR_BOUNDARY_MISMATCH",)
    t=s.transitions[0].model_copy(update={"before_node_path":(2,)})
    r=estimate_strength_timing(ctx,w,s.model_copy(update={"transitions":(t,)+s.transitions[1:]}))
    assert r.diagnostics==("TIMING_NODE_PATH_OR_BOUNDARY_MISMATCH",)


def test_rebinding_40_vs_24_never_changes_timing_math(source):
    ctx,_,w=source
    s=complete(ctx,w)
    # Synthetic counterfactual: 6 * 400 sec = 40min versus 6 * 240 = 24min.
    def sized(seconds):
        nodes=[n.model_copy(update={"duration":n.duration.model_copy(update={"seconds":seconds})}) for n in w.definition.steps]
        definition=w.definition.model_copy(update={"steps":nodes})
        return w.model_copy(update={"definition":definition,"fingerprint":context_fingerprint({"definition":definition})})
    estimates=[]
    for minutes,seconds in ((40,400),(24,240)):
        draft=sized(seconds)
        rebound=s.model_copy(update={"workout_fingerprint":draft.fingerprint,"definition_fingerprint":definition_fingerprint(draft)})
        result=estimate_strength_timing(ctx,draft,rebound)
        estimates.append(result.duration_seconds)
        assert estimate_strength_timing(ctx,draft).coverage=="unavailable"
        assert estimate_strength_timing(ctx,draft,s).diagnostics==("TIMING_SNAPSHOT_BINDING_MISMATCH",)
    assert estimates[0]==estimates[1]
    assert (estimates[0].minimum,estimates[0].maximum)==(635,1000)


def test_repeat_is_explicitly_unsupported_without_flattening(source):
    from app.domains.planning.models import WorkoutNode
    ctx,_,w=source
    definition=w.definition.model_copy(update={"steps":[WorkoutNode(kind="repeat",repetitions=2,steps=w.definition.steps)]})
    draft=w.model_copy(update={"definition":definition})
    r=estimate_strength_timing(ctx,draft)
    assert r.coverage=="unavailable" and r.duration_seconds is None
    assert r.diagnostics==("UNSUPPORTED_REPEAT_STRUCTURE",)


def test_canonical_order_determinism_and_snapshot_immutability(source):
    ctx,_,w=source
    s=complete(ctx,w)
    data=s.model_dump();data["exercises"]=tuple(reversed(data["exercises"]));data["transitions"]=tuple(reversed(data["transitions"]))
    reordered=StrengthTimingSnapshot.model_validate(data)
    assert estimate_strength_timing(ctx,w,s).model_dump_json()==estimate_strength_timing(ctx,w,reordered).model_dump_json()
    with pytest.raises(ValidationError):s.warmup.state="unknown"


def test_sidecar_never_mutates_artifact_or_consumes_missing_data(source):
    ctx,artifact,w=source
    before=artifact.model_dump_json()
    r=build_strength_timing_shadow(ctx,artifact)
    assert r.estimates and all(e.coverage=="unavailable" for e in r.estimates)
    provided=build_strength_timing_shadow(ctx,artifact,(complete(ctx,w),))
    assert sum(e.coverage=="complete" for e in provided.estimates)==1
    assert artifact.model_dump_json()==before
    assert provided.artifact_fingerprint==artifact.fingerprint
    duplicate=build_strength_timing_shadow(ctx,artifact,(complete(ctx,w),complete(ctx,w)))
    assert "DUPLICATE_WORKOUT_TIMING_SNAPSHOT" in duplicate.diagnostics
    assert not any(e.coverage=="complete" for e in duplicate.estimates)
    alternative=complete(ctx,w).model_copy(update={"warmup":absent()})
    a=build_strength_timing_shadow(ctx,artifact,(complete(ctx,w),alternative))
    b=build_strength_timing_shadow(ctx,artifact,(alternative,complete(ctx,w)))
    assert a.model_dump_json()==b.model_dump_json()


def test_multiathlete_scope_and_context_are_enforced(source):
    ctx,artifact,w=source
    other=ctx.model_copy(update={"request":ctx.request.model_copy(update={"athlete_id":UUID(int=99)}),"fingerprint":"f"*64})
    r=estimate_strength_timing(other,w,complete(ctx,w))
    assert r.coverage=="unavailable" and r.diagnostics==("WORKOUT_CONTEXT_MISMATCH",)
    with pytest.raises(ValueError,match="CONTEXT_MISMATCH"):build_strength_timing_shadow(other,artifact)


def test_revalidation_blocks_model_copy_bypass(source):
    ctx,_,w=source
    s=complete(ctx,w)
    bad=s.model_copy(update={"exercises":s.exercises+(s.exercises[0],)})
    r=estimate_strength_timing(ctx,w,bad)
    assert r.coverage=="unavailable" and r.diagnostics==("INVALID_TIMING_SNAPSHOT_CONTRACT",)


def test_unbounded_occurrences_fail_closed_without_expanding(source):
    ctx,_,w=source
    e=ExerciseTiming(node_path=(2,),sets_scope="per_side",side_count=100000000,execution_per_set=specified(1,2))
    s=empty_timing_snapshot(ctx,w).model_copy(update={"exercises":(e,)})
    r=estimate_strength_timing(ctx,w,s)
    assert r.diagnostics==("TIMING_OCCURRENCE_LIMIT_EXCEEDED",)
    assert r.duration_seconds is None


def test_orphan_snapshot_is_diagnosed_not_applied(source):
    ctx,artifact,w=source
    s=complete(ctx,w).model_copy(update={"workout_fingerprint":"a"*64})
    r=build_strength_timing_shadow(ctx,artifact,(s,))
    assert r.diagnostics==("ORPHAN_WORKOUT_TIMING_SNAPSHOT",)
    assert all(e.coverage=="unavailable" for e in r.estimates)


@pytest.mark.parametrize("phase",["BASE","BUILD","RECOVERY","TAPER","COMPETITION","SPECIFIC"])
def test_phase_artifact_content_identity_in_shadow(source,phase):
    from app.domains.planning.season_structure import SeasonPhase
    from app.domains.planning.workout_builder import build_structured_workout,WorkoutBuilderConfig
    ctx,artifact,w=source
    item=next(s for s in artifact.sessions if s.prescription.discipline=="strength")
    p=item.prescription.model_copy(update={"phase":SeasonPhase(phase)})
    draft=build_structured_workout(ctx,p,WorkoutBuilderConfig(version="test",algorithm_version="test"))
    before=draft.model_dump_json()
    e=estimate_strength_timing(ctx,draft)
    assert draft.model_dump_json()==before
    sample=artifact.model_copy(update={"sessions":(item.model_copy(update={"prescription":p,"workout":draft}),)})
    artifact_before=sample.model_dump_json()
    report=build_strength_timing_shadow(ctx,sample)
    assert sample.model_dump_json()==artifact_before
    assert report.artifact_fingerprint==sample.fingerprint
    assert e.coverage=="unavailable" and e.duration_seconds is None


@pytest.mark.parametrize("target",[None,6])
def test_application_reports_unavailable_without_changing_artifacts(monkeypatch,target):
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication,PlanningContextAssembler,ExecutionAdaptationProposalAssembler
    from app.domains.planning.execution_adaptation import build_execution_adaptation_context
    from app.domains.planning.execution_proposals import build_execution_adaptation_proposal_context
    from tests.test_execution_adaptation import context as evidence_context
    from tests.test_planning_preview_application import seeded
    ctx=profile_context()
    ctx=ctx.model_copy(update={"preferences":ctx.preferences.model_copy(update={"target_sessions_per_week":target})})
    evidence=evidence_context().model_copy(update={"athlete_profile_id":ctx.request.athlete_id,"as_of_date":ctx.request.planning_date})
    proposals=build_execution_adaptation_proposal_context(build_execution_adaptation_context(evidence))
    monkeypatch.setattr(PlanningContextAssembler,"assemble",lambda *a,**k:ctx)
    monkeypatch.setattr(ExecutionAdaptationProposalAssembler,"assemble",lambda *a,**k:proposals)
    engine,_,_,user,_=seeded()
    with Session(engine) as db:
        app=PlanningPreviewApplication(db)
        row=app.generate(request=ctx.request,user_id=user)
        r=app.strength_timing_shadow_report
        assert r is not None and r.artifact_fingerprint==row.artifact_fingerprint
        assert r.estimates and all(e.coverage=="unavailable" for e in r.estimates)
        assert "strength_timing" not in row.artifact
        assert "strength_timing_shadow_report" not in row.artifact
        monkeypatch.setattr(PlanningContextAssembler,"assemble",lambda *a,**k:(_ for _ in ()).throw(ValueError("unavailable")))
        with pytest.raises(ValueError,match="unavailable"):app.generate(request=ctx.request,user_id=user)
        assert app.strength_timing_shadow_report is None


def test_actual_double_capacity_and_fingerprints_are_unchanged():
    from collections import defaultdict
    ctx=profile_context()
    prefs=ctx.preferences.model_copy(update={"availability_slots":tuple(s for s in ctx.preferences.availability_slots if s.weekday!=3)})
    ctx=ctx.model_copy(update={"preferences":prefs})
    artifact=pipeline(ctx)[0]
    before=artifact.model_dump_json()
    report=build_strength_timing_shadow(ctx,artifact)
    assert artifact.model_dump_json()==before
    assert report.artifact_fingerprint==artifact.fingerprint
    paired=False
    for week in artifact.session_plan.weeks:
        days=defaultdict(list)
        for s in week.sessions:
            if s.discipline!="competition":days[s.date].append(s)
        for day,ss in days.items():
            paired|={s.discipline for s in ss}=={"strength","swimming"}
            assert len(ss)<=prefs.max_sessions_per_day
            assert sum(s.target_duration_minutes for s in ss)<=next(slot.available_minutes for slot in prefs.availability_slots if slot.weekday==day.weekday())
    assert paired and all(e.coverage=="unavailable" for e in report.estimates)


def test_valid_multiathlete_inputs_are_independent(source):
    ctx,_,w=source
    other=ctx.model_copy(update={"request":ctx.request.model_copy(update={"athlete_id":UUID(int=99)})})
    other=other.model_copy(update={"fingerprint":context_fingerprint(other.model_dump(exclude={"fingerprint"}))})
    artifact=pipeline(other)[0]
    draft=next(s.workout for s in artifact.sessions if s.prescription.discipline=="strength")
    r=estimate_strength_timing(other,draft,complete(other,draft))
    own=estimate_strength_timing(ctx,w,complete(ctx,w))
    assert r.duration_seconds==own.duration_seconds
    assert r.athlete_id!=own.athlete_id
    assert r.timing_snapshot_fingerprint!=own.timing_snapshot_fingerprint
    assert estimate_strength_timing(other,draft,complete(ctx,w)).coverage=="unavailable"
