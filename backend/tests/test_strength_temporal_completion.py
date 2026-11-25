"""4B.4 diagnostic boundaries; all seconds below are synthetic fixtures."""
import pytest
from scripts.audit_strength_temporal_completion import classify_missing, describe_structure
from tests.test_strength_timing_policy import base, single, evaluate, explicit
from tests.test_strength_timing_inputs import rep, value, whole, absent, P
from app.domains.planning.strength_timing import TimingComponent
from app.domains.planning.strength_timing_inputs import ExerciseExecutionInput, SetRestInput, TempoInput, GapTimingInput
from app.domains.planning.strength_timing_policy import compare_strength_legacy


@pytest.mark.parametrize("legacy,status,shortfall", [(89,"LEGACY_BELOW_KNOWN_MINIMUM",1),(90,"INDETERMINATE_PARTIAL",None),(91,"INDETERMINATE_PARTIAL",None)])
def test_partial_boundary_never_proves_compatibility(base,legacy,status,shortfall):
    e=evaluate(base,single(base,rest=90))
    c=compare_strength_legacy(e.estimate,legacy)
    assert c.status==status and c.known_minimum_shortfall_seconds==shortfall
    assert c.signed_distance_to_interval_seconds is None
    assert e.estimate.duration_seconds is None


@pytest.mark.parametrize("legacy,status,distance",[(29,"LEGACY_BELOW_INTERVAL",-1),(30,"LEGACY_WITHIN_INTERVAL",0),(40,"LEGACY_WITHIN_INTERVAL",0),(41,"LEGACY_ABOVE_INTERVAL",1)])
def test_complete_closed_interval_limits(base,legacy,status,distance):
    ctx,_,_=base; w=single(base)
    e=evaluate(base,w,explicit(ctx,w,rep()))
    c=compare_strength_legacy(e.estimate,legacy)
    assert c.status==status and c.signed_distance_to_interval_seconds==distance


@pytest.mark.parametrize("mode",["timed","isometric"])
def test_explicit_execution_remains_independent_and_unknown_edges_stay_unknown(base,mode):
    ctx,_,_=base; w=single(base)
    x=ExerciseExecutionInput(node_path=(0,),mode=mode,per_set=value(20,25),timed_scope="all_sides_included",scope_provenance=P)
    complete=explicit(ctx,w,x)
    partial=complete.model_copy(update={"warmup":None,"cooldown":None})
    before=w.model_dump_json()
    e=evaluate(base,w,partial)
    assert e.estimate.coverage=="partial" and e.estimate.duration_seconds is None
    assert e.estimate.known_subtotal_seconds.minimum==50
    assert any("warmup" in c for c in e.estimate.missing_components)
    assert w.model_dump_json()==before
    assert evaluate(base,w,complete).estimate.coverage=="complete"


def test_partial_tempo_with_known_rest_does_not_become_complete(base):
    ctx,_,_=base; w=single(base)
    tempo=TempoInput(eccentric=value(2),concentric=TimingComponent(),first_pause=absent(),final_pause=absent())
    x=rep(seconds_per_rep=TimingComponent(),tempo=tempo,between_sets=SetRestInput())
    e=evaluate(base,w,explicit(ctx,w,x))
    assert e.estimate.coverage=="partial"
    assert e.estimate.known_subtotal_seconds.minimum==30
    assert e.estimate.duration_seconds is None


def test_included_transition_is_counted_once_through_policy(base):
    ctx,_,_=base; w=single(base,unilateral=True)
    gap=GapTimingInput(rest=value(5),transition=value(3),preparation=absent(),relationship="included_in_rest",provenance=P)
    x=rep(seconds_per_rep=value(2),rep_scope="per_side",rep_time_scope="single_side",side_execution="successive",side_sequence="within_each_set",side_count=2,side_gap=gap,between_sets=SetRestInput(timing=value(7)))
    e=evaluate(base,w,explicit(ctx,w,x))
    assert e.estimate.duration_seconds.minimum==57 #40 work + 2*5 whole side gaps +7 rest
    assert len({c.component_id for c in e.estimate.known_components})==len(e.estimate.known_components)


def test_unavailable_cannot_compare_even_with_positive_legacy(base):
    e=evaluate(base,single(base,unilateral=True))
    assert e.estimate.coverage=="unavailable"
    for seconds in (0,90,2400):
        assert compare_strength_legacy(e.estimate,seconds).status=="UNAVAILABLE"


@pytest.mark.parametrize("component,kind",[("node:(0,).execution","execution"),("node:(2,).execution_scope","unilateral_scope"),("node:(2,).rest_occurrences","unilateral_scope"),("gap:(0,)->(1,)","transition"),("warmup","session_edge"),("cooldown","session_edge"),("repeat:unknown","structure_or_other")])
def test_missing_data_causes_are_differentiated_and_deterministic(component,kind):
    a=classify_missing(component)
    assert a==classify_missing(component) and a["kind"]==kind
    assert a["required"] and a["causes"]
    if kind=="unilateral_scope":assert "structural_ambiguity" in a["causes"]
    if kind=="execution":assert "independent_evidence" in a["causes"]


@pytest.mark.parametrize("nodes,expected",[([{"kind":"step","phase":"strength"}],"flat_strength"),([{"kind":"repeat"}],"repeat_requires_declared_order"),([{"kind":"step","phase":"warmup"}],"flat_with_edge_nodes")])
def test_structure_audit_does_not_infer_execution_order(nodes,expected):
    assert describe_structure(nodes)==expected
