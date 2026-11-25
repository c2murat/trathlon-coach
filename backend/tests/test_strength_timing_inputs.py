"""Numeric timings are synthetic fixtures, not athlete values/defaults."""
import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import context_fingerprint
from app.domains.planning.models import WorkoutNode,WorkoutDuration,WorkoutTarget
from app.domains.planning.strength_timing import (
    TimingComponent,TimingProvenance,SecondsInterval,RepeatTiming,empty_timing_snapshot,estimate_strength_timing,
)
from app.domains.planning.strength_timing_inputs import (
    GapTimingInput,TempoInput,RepetitionRange,SetRestInput,ExerciseExecutionInput,
    BoundaryTimingInput,RepeatTimingInput,EdgeTimingInput,StrengthTimingInputs,
    compile_strength_timing_inputs,estimate_strength_timing_inputs,build_strength_timing_inputs_shadow,
)
from tests.test_weekly_intent_shadow import profile_context
from tests.test_endurance_volume_authority import pipeline

P=TimingProvenance(source="explicit_prescription",source_id="synthetic-only",version="test")
C=TimingProvenance(source="configurable_prescription",source_id="synthetic-config-only",version="test")


def value(a,b=None,p=P):
    return TimingComponent(state="specified",seconds=SecondsInterval(minimum=a,maximum=a if b is None else b),provenance=p)


def absent():return TimingComponent(state="not_prescribed",provenance=P)
def na():return TimingComponent(state="not_applicable",provenance=P)
def whole(c):return GapTimingInput(whole=c)


@pytest.fixture(scope="module")
def base():
    ctx=profile_context();artifact=pipeline(ctx)[0]
    w=next(x.workout for x in artifact.sessions if x.prescription.discipline=="strength")
    return ctx,artifact,w


def workout(base,nodes):
    ctx,_,w=base
    definition=w.definition.model_copy(update={"steps":list(nodes)})
    return w.model_copy(update={"definition":definition,"fingerprint":context_fingerprint({"definition":definition})})


def node(base,unilateral=False,reps=5,sets=2):
    return base[2].definition.steps[0].model_copy(update={"unilateral":unilateral,"reps":reps,"sets":sets,"rest_seconds":10})


def rep(path=(0,),**updates):
    args=dict(node_path=path,mode="repetitions",seconds_per_rep=value(2,3),rep_scope="total",rep_time_scope="counted_cycle",
        side_execution="not_applicable",scope_provenance=P,between_sets=SetRestInput(timing=value(10)))
    args.update(updates);return ExerciseExecutionInput(**args)


def inputs(ctx,w,executions=(),**kwargs):
    return StrengthTimingInputs(snapshot=empty_timing_snapshot(ctx,w),executions=executions,warmup=whole(absent()),cooldown=whole(absent()),**kwargs)


def bounds(result):
    assert result.coverage=="complete",result.model_dump_json()
    return result.duration_seconds.minimum,result.duration_seconds.maximum


def test_explicit_repetitions_and_no_time_source(base):
    ctx,_,_=base;w=workout(base,[node(base)])
    assert bounds(estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(rep(),))))==(30,40)
    r=estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(rep(seconds_per_rep=TimingComponent()),)))
    assert r.duration_seconds is None and r.coverage=="partial"
    assert all(c.component_id!="steps[0].execution" for c in r.known_components)


@pytest.mark.parametrize("mode",["timed","isometric"])
def test_explicit_timed_or_isometric_set(base,mode):
    ctx,_,_=base;w=workout(base,[node(base)])
    x=ExerciseExecutionInput(node_path=(0,),mode=mode,per_set=value(20,25),timed_scope="all_sides_included",scope_provenance=P,between_sets=SetRestInput(timing=value(10)))
    assert bounds(estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,))))==(50,60)


def test_tempo_units_semantics_and_provenance(base):
    ctx,_,_=base;w=workout(base,[node(base)])
    tempo=TempoInput(eccentric=value(2,p=C),first_pause=value(0,p=C),concentric=value(1,p=C),final_pause=value(0,p=C))
    x=rep(seconds_per_rep=TimingComponent(),tempo=tempo)
    compiled=compile_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,)))
    assert bounds(estimate_strength_timing(ctx,w,compiled.snapshot))==(40,40)
    p=compiled.snapshot.exercises[0].execution_per_set.provenance
    assert p.source=="derived_prescription" and any("configurable_prescription" in v for v in p.inputs)
    assert compiled.inputs.executions[0].tempo.eccentric.provenance.source=="configurable_prescription"
    with pytest.raises(ValidationError):TempoInput(unit="seconds_per_minute")
    with pytest.raises(ValidationError):rep(tempo=tempo)
    with pytest.raises(ValidationError):value("X")


def test_partial_tempo_keeps_only_known_disjoint_phases(base):
    ctx,_,_=base;w=workout(base,[node(base)])
    x=rep(seconds_per_rep=TimingComponent(),tempo=TempoInput(eccentric=value(2),concentric=value(1)))
    r=estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,)))
    assert r.coverage=="partial" and r.duration_seconds is None
    assert r.known_subtotal_seconds.minimum==40
    assert any("first_pause" in m for m in r.missing_components)


def test_variable_repetitions_when_public_reps_unknown(base):
    ctx,_,_=base;w=workout(base,[node(base,reps=None)])
    x=rep(repetitions=RepetitionRange(minimum=4,maximum=6,provenance=P))
    assert bounds(estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,))))==(26,46)
    fixed=workout(base,[node(base,reps=5)])
    r=estimate_strength_timing_inputs(ctx,fixed,inputs(ctx,fixed,(x,)))
    assert r.diagnostics==("REPETITION_PRESCRIPTION_CONFLICT",)


def test_unilateral_per_side_successive_and_no_double_multiplier(base):
    ctx,_,_=base;w=workout(base,[node(base,unilateral=True)])
    x=rep(seconds_per_rep=value(2),rep_scope="per_side",rep_time_scope="single_side",side_execution="successive",side_sequence="within_each_set",side_count=2,side_gap=whole(value(3)))
    compiled=compile_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,)))
    assert compiled.snapshot.exercises[0].sets_scope=="all_sides_included"
    assert bounds(estimate_strength_timing(ctx,w,compiled.snapshot))==(56,56)


def test_unilateral_total_reps_and_unknown_gap_occurrences(base):
    ctx,_,_=base;w=workout(base,[node(base,unilateral=True)])
    x=rep(seconds_per_rep=value(2),side_execution="successive",side_sequence="within_each_set",side_gap=whole(value(3)),side_gap_occurrences=1)
    assert bounds(estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,))))==(36,36)
    unknown=x.model_copy(update={"side_gap_occurrences":None})
    r=estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(unknown,)))
    assert r.coverage=="partial" and r.duration_seconds is None
    assert "SIDE_GAP_OCCURRENCES_UNKNOWN" in r.diagnostics


def test_unilateral_simultaneous_cycle_and_unknown_semantics(base):
    ctx,_,_=base;w=workout(base,[node(base,unilateral=True)])
    x=rep(seconds_per_rep=value(2),rep_scope="per_side",rep_time_scope="simultaneous_cycle",side_execution="simultaneous",side_count=2)
    assert bounds(estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,))))==(30,30)
    bad=x.model_copy(update={"side_execution":"unknown"})
    r=estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(bad,)))
    assert r.duration_seconds is None and "EXECUTION_SEMANTICS_UNKNOWN" in r.diagnostics


def test_unknown_mode_cannot_guess_from_name_pattern_rpe_or_allocated_time(base):
    ctx,_,_=base;w=workout(base,[node(base)])
    x=ExerciseExecutionInput(node_path=(0,))
    s=StrengthTimingInputs(snapshot=empty_timing_snapshot(ctx,w),executions=(x,))
    r=estimate_strength_timing_inputs(ctx,w,s)
    assert r.coverage=="unavailable" and r.duration_seconds is None


def test_explicit_scope_can_use_prescribed_rest_without_final_rest(base):
    ctx,_,_=base;w=workout(base,[node(base,sets=3)])
    x=rep(seconds_per_rep=value(2),between_sets=SetRestInput(from_prescription=True,scope_provenance=P))
    compiled=compile_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,)))
    assert compiled.snapshot.exercises[0].pauses[0].after_sets==(1,2)
    assert bounds(estimate_strength_timing(ctx,w,compiled.snapshot))==(50,50) # 3*5*2 + 2*10
    with pytest.raises(ValidationError):SetRestInput(from_prescription=True)


def test_gap_transition_setup_disjoint_or_included_no_double_count(base):
    ctx,_,_=base;w=workout(base,[node(base),node(base)])
    gap=GapTimingInput(rest=value(20),transition=value(5),preparation=value(3),relationship="disjoint",provenance=P)
    s=inputs(ctx,w,(rep((0,),seconds_per_rep=value(2)),rep((1,),seconds_per_rep=value(2))),
        boundaries=(BoundaryTimingInput(after_node_path=(0,),before_node_path=(1,),gap=gap),))
    assert bounds(estimate_strength_timing_inputs(ctx,w,s))==(88,88) # 2*(20+10)+28
    included=gap.model_copy(update={"relationship":"included_in_rest"})
    s=s.model_copy(update={"boundaries":(s.boundaries[0].model_copy(update={"gap":included}),)})
    assert bounds(estimate_strength_timing_inputs(ctx,w,s))==(80,80)


def test_zero_absence_unknown_and_partial_gap_are_distinct(base):
    ctx,_,_=base;w=workout(base,[node(base),node(base)])
    def run(gap):
        s=inputs(ctx,w,(rep((0,)),rep((1,))),boundaries=(BoundaryTimingInput(after_node_path=(0,),before_node_path=(1,),gap=gap),))
        return estimate_strength_timing_inputs(ctx,w,s)
    assert run(whole(value(0))).coverage=="complete"
    assert run(whole(absent())).coverage=="complete"
    assert run(GapTimingInput()).coverage=="partial"
    partial=run(GapTimingInput(rest=value(5),transition=TimingComponent(),preparation=na(),relationship="disjoint",provenance=P))
    assert partial.coverage=="partial" and partial.duration_seconds is None
    assert partial.known_subtotal_seconds.minimum==65


def test_explicit_edge_nodes_are_not_counted_twice(base):
    ctx,_,_=base
    warm=WorkoutNode(kind="step",phase="warmup",duration=WorkoutDuration(mode="time",seconds=999),target=WorkoutTarget(metric="none",mode="none"))
    cool=warm.model_copy(update={"phase":"cooldown"})
    w=workout(base,[warm,node(base),cool])
    s=StrengthTimingInputs(snapshot=empty_timing_snapshot(ctx,w),executions=(rep((1,),seconds_per_rep=value(2)),),
        edge_nodes=(EdgeTimingInput(node_path=(0,),gap=whole(value(10))),EdgeTimingInput(node_path=(2,),gap=whole(value(5)))))
    assert bounds(estimate_strength_timing_inputs(ctx,w,s))==(45,45)
    duplicate=s.model_copy(update={"warmup":whole(value(10))})
    assert estimate_strength_timing_inputs(ctx,w,duplicate).diagnostics==("DUPLICATE_EDGE_TIMING_SOURCE",)


@pytest.mark.parametrize("role",["circuit","superset"])
def test_existing_repeat_with_explicit_sequential_rounds(base,role):
    ctx,_,_=base
    repeat=WorkoutNode(kind="repeat",repetitions=3,steps=[node(base,sets=1),node(base,sets=1)])
    w=workout(base,[repeat])
    declaration=RepeatTiming(node_path=(0,),role=role,sequence="sequential",provenance=P)
    s=inputs(ctx,w,(rep((0,0),seconds_per_rep=value(2)),rep((0,1),seconds_per_rep=value(2))),
        boundaries=(BoundaryTimingInput(after_node_path=(0,0),before_node_path=(0,1),gap=whole(value(4))),),
        repeats=(RepeatTimingInput(declaration=declaration,between_rounds=whole(value(7))),))
    assert bounds(estimate_strength_timing_inputs(ctx,w,s))==(86,86) # 3*(10+4+10)+2*7, no final-round rest


@pytest.mark.parametrize("sequence",["unknown","simultaneous"])
def test_temporally_ambiguous_blocks_never_produce_complete(base,sequence):
    ctx,_,_=base
    repeat=WorkoutNode(kind="repeat",repetitions=2,steps=[node(base,sets=1)])
    w=workout(base,[repeat])
    d=RepeatTiming(node_path=(0,),sequence=sequence,provenance=P if sequence!="unknown" else None)
    s=inputs(ctx,w,(rep((0,0)),),repeats=(RepeatTimingInput(declaration=d),))
    r=estimate_strength_timing_inputs(ctx,w,s)
    assert r.coverage=="partial" and r.duration_seconds is None
    assert r.diagnostics and any("semantics" in m for m in r.missing_components)


def test_invalid_inputs_provenance_and_identity(base):
    ctx,_,_=base;w=workout(base,[node(base)])
    with pytest.raises(ValidationError):RepetitionRange(minimum=6,maximum=4,provenance=P)
    with pytest.raises(ValidationError):GapTimingInput(relationship="disjoint")
    with pytest.raises(ValidationError):GapTimingInput(whole=value(5),rest=value(5))
    with pytest.raises(ValidationError):TimingProvenance(source="derived_prescription",source_id="x",version="1")
    s=inputs(ctx,w,(rep(),))
    wrong=s.model_copy(update={"snapshot":s.snapshot.model_copy(update={"workout_fingerprint":"f"*64})})
    assert estimate_strength_timing_inputs(ctx,w,wrong).diagnostics==("TIMING_INPUT_BINDING_MISMATCH",)


def test_no_circular_dependency_and_determinism(base):
    ctx,_,_=base
    outputs=[]
    for seconds in (240,400):
        n=node(base).model_copy(update={"duration":WorkoutDuration(mode="time",seconds=seconds)})
        w=workout(base,[n]);s=inputs(ctx,w,(rep(),))
        a=estimate_strength_timing_inputs(ctx,w,s);b=estimate_strength_timing_inputs(ctx,w,s)
        assert a.model_dump_json()==b.model_dump_json()
        outputs.append(bounds(a))
    assert outputs[0]==outputs[1]==(30,40)


def test_shadow_wrapper_does_not_change_artifact(base):
    ctx,artifact,_=base
    before=artifact.model_dump_json()
    report=build_strength_timing_inputs_shadow(ctx,artifact)
    assert artifact.model_dump_json()==before
    assert all(e.coverage=="unavailable" for e in report.estimates)


def test_direct_40_vs_24_and_target_rpe_names_do_not_supply_evidence(base):
    ctx,_,_=base;out=[]
    for seconds,title,rpe in ((240,"Dead bug",5),(400,"Unknown hold",9)):
        n=node(base).model_copy(update={"title":title,"duration":WorkoutDuration(mode="time",seconds=seconds),
            "target":WorkoutTarget(metric="rpe",mode="absolute_range",minimum=rpe,maximum=rpe)})
        w=workout(base,[n]);s=inputs(ctx,w,(rep(),))
        out.append(bounds(estimate_strength_timing_inputs(ctx,w,s)))
        bare=StrengthTimingInputs(snapshot=empty_timing_snapshot(ctx,w))
        assert estimate_strength_timing_inputs(ctx,w,bare).coverage=="unavailable"
    assert out[0]==out[1]


def test_missing_set_time_preserves_explicit_independent_rests(base):
    ctx,_,_=base;w=workout(base,[node(base,sets=3)])
    x=ExerciseExecutionInput(node_path=(0,),between_sets=SetRestInput(from_prescription=True,scope_provenance=P))
    r=estimate_strength_timing_inputs(ctx,w,StrengthTimingInputs(snapshot=empty_timing_snapshot(ctx,w),executions=(x,)))
    assert r.coverage=="partial" and r.duration_seconds is None
    assert r.known_subtotal_seconds.minimum==20


def test_nested_repeat_and_partial_round_rest(base):
    ctx,_,_=base
    inner=WorkoutNode(kind="repeat",repetitions=2,steps=[node(base,sets=1)])
    outer=WorkoutNode(kind="repeat",repetitions=3,steps=[inner])
    w=workout(base,[outer])
    s=inputs(ctx,w,(rep((0,0,0),seconds_per_rep=value(2)),),repeats=(
        RepeatTimingInput(declaration=RepeatTiming(node_path=(0,),sequence="sequential",provenance=P),between_rounds=whole(value(5))),
        RepeatTimingInput(declaration=RepeatTiming(node_path=(0,0),sequence="sequential",provenance=P),between_rounds=whole(value(3)))))
    assert bounds(estimate_strength_timing_inputs(ctx,w,s))==(79,79) # 6*10 +3*3 +2*5
    partial=s.model_copy(update={"repeats":(s.repeats[0].model_copy(update={"between_rounds":None}),s.repeats[1])})
    r=estimate_strength_timing_inputs(ctx,w,partial)
    assert r.coverage=="partial" and r.known_subtotal_seconds.minimum==69


def test_ambiguous_repeat_keeps_only_known_outside_components(base):
    ctx,_,_=base
    block=WorkoutNode(kind="repeat",repetitions=2,steps=[node(base,sets=1)])
    w=workout(base,[node(base,sets=1),block])
    s=inputs(ctx,w,(rep((0,),seconds_per_rep=value(2)),rep((1,0))),boundaries=(
        BoundaryTimingInput(after_node_path=(0,),before_node_path=(1,),gap=whole(value(4))),))
    r=estimate_strength_timing_inputs(ctx,w,s)
    assert r.coverage=="partial" and r.duration_seconds is None
    assert r.known_subtotal_seconds.minimum==14
    assert "AMBIGUOUS_REPEAT_ORDER" in r.diagnostics


def test_isometric_single_side_and_invalid_side_gap(base):
    ctx,_,_=base;w=workout(base,[node(base,unilateral=True)])
    x=ExerciseExecutionInput(node_path=(0,),mode="isometric",per_set=value(30),timed_scope="per_side",side_count=1,
        side_execution="successive",side_sequence="within_each_set",scope_provenance=P,between_sets=SetRestInput(timing=value(10)))
    assert bounds(estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,))))==(70,70)
    bad=x.model_copy(update={"side_count":2,"side_gap_occurrences":3})
    assert estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(bad,))).diagnostics==("SIDE_GAP_OCCURRENCE_CONFLICT",)


def test_provenance_invalid_units_unknowns_and_no_empirical_confidence(base):
    ctx,_,_=base;w=workout(base,[node(base)])
    with pytest.raises(ValidationError):ExerciseExecutionInput(node_path=(0,),mode="timed",timed_scope="all_sides_included")
    with pytest.raises(ValidationError):RepetitionRange(minimum=True,maximum=3,provenance=P)
    with pytest.raises(ValidationError):RepetitionRange(minimum=1,maximum=3,unit="seconds",provenance=P)
    with pytest.raises(ValidationError):value(-1)
    with pytest.raises(ValidationError):value(3,1)
    result=estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(rep(),)))
    assert result.validation_state=="not_evaluated"
    assert "confidence" not in result.model_dump()
    compiled=compile_strength_timing_inputs(ctx,w,inputs(ctx,w,(rep(),)))
    assert compiled.snapshot.schema_version==2


def test_included_transition_cannot_exceed_known_container(base):
    ctx,_,_=base;w=workout(base,[node(base),node(base)])
    gap=GapTimingInput(rest=value(2),transition=value(5),relationship="included_in_rest",provenance=P)
    s=inputs(ctx,w,(rep((0,)),rep((1,))),boundaries=(BoundaryTimingInput(after_node_path=(0,),before_node_path=(1,),gap=gap),))
    assert estimate_strength_timing_inputs(ctx,w,s).diagnostics==("INCLUDED_COMPONENT_EXCEEDS_CONTAINER",)


def test_foreign_athlete_and_duplicate_sources_do_not_modify_workouts(base):
    from uuid import UUID
    ctx,artifact,w=base
    s=inputs(ctx,w,(rep(),))
    foreign=s.model_copy(update={"snapshot":s.snapshot.model_copy(update={"athlete_id":UUID(int=99)})})
    assert estimate_strength_timing_inputs(ctx,w,foreign).diagnostics==("TIMING_INPUT_BINDING_MISMATCH",)
    before=artifact.model_dump_json()
    result=build_strength_timing_inputs_shadow(ctx,artifact,(s,s))
    assert artifact.model_dump_json()==before
    assert any("DUPLICATE_STRENGTH_TIMING_INPUT" in e.diagnostics for e in result.estimates)


def test_successive_side_order_changes_rest_occurrences_explicitly(base):
    ctx,_,_=base;w=workout(base,[node(base,unilateral=True)])
    x=rep(seconds_per_rep=value(2),rep_scope="per_side",rep_time_scope="single_side",side_execution="successive",
        side_sequence="all_sets_per_side",side_count=2,side_gap=whole(value(3)))
    assert bounds(estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(x,))))==(63,63) # 4*10 work,2*10 rests,1*3 side change
    unknown=x.model_copy(update={"side_sequence":"unknown"})
    r=estimate_strength_timing_inputs(ctx,w,inputs(ctx,w,(unknown,)))
    assert r.coverage=="partial" and r.known_subtotal_seconds.minimum==40
    assert "SIDE_SET_ORDER_UNKNOWN" in r.diagnostics
