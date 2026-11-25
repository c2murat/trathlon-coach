"""Synthetic explicit timings only; generic policy introduces NO seconds."""
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import context_fingerprint
from app.domains.planning.strength_timing import (
    TimingComponent,TimingProvenance,SecondsInterval,StrengthTimingEstimate,empty_timing_snapshot,RepeatTiming,
)
from app.domains.planning.strength_timing_inputs import (
    StrengthTimingInputs,ExerciseExecutionInput,TempoInput,SetRestInput,RepeatTimingInput,
    BoundaryTimingInput,GapTimingInput,
)
from app.domains.planning.strength_timing_policy import (
    VERSION,StrengthPolicyScope,select_strength_temporal_policy,prescribe_strength_temporal_inputs,
    compare_strength_legacy,build_strength_temporal_policy_shadow,
)
from tests.test_endurance_volume_authority import pipeline
from tests.test_weekly_intent_shadow import profile_context
from tests.test_strength_timing_inputs import value,absent,whole,rep,P


@pytest.fixture(scope="module")
def base():
    ctx=profile_context();artifact=pipeline(ctx)[0]
    item=next(s for s in artifact.sessions if s.prescription.discipline=="strength")
    return ctx,artifact,item


def single(base,unilateral=False,sets=2,reps=5,rest=10):
    ctx,_,item=base
    node=item.workout.definition.steps[0].model_copy(update={"unilateral":unilateral,"sets":sets,"reps":reps,"rest_seconds":rest})
    definition=item.workout.definition.model_copy(update={"steps":[node]})
    w=item.workout.model_copy(update={"definition":definition,"fingerprint":context_fingerprint({"definition":definition})})
    return w


def evaluate(base,w,specific=None,legacy=1):
    ctx,artifact,item=base
    p=item.prescription.model_copy(update={"target_duration_minutes":legacy})
    sample=artifact.model_copy(update={"sessions":(item.model_copy(update={"prescription":p,"workout":w}),)})
    report=build_strength_temporal_policy_shadow(ctx,sample,(specific,) if specific else ())
    return report.evaluations[0]


def explicit(ctx,w,x,**kwargs):
    return StrengthTimingInputs(snapshot=empty_timing_snapshot(ctx,w),executions=(x,),warmup=whole(absent()),cooldown=whole(absent()),**kwargs)


@pytest.mark.parametrize("goal",["triathlon","duathlon","aquathlon","running","cycling","swimming"])
def test_supported_objectives_have_deterministic_traceable_scopes(goal):
    scope=StrengthPolicyScope(role="GENERAL_STRENGTH",phase="BASE",objectives=(goal,))
    a=select_strength_temporal_policy(scope);b=select_strength_temporal_policy(scope)
    assert a==b and a.applicable
    assert goal in a.policy_id
    assert a.version==VERSION
    assert a.source_references
    assert "seconds" not in a.model_dump() # no numeric goal-specific default


@pytest.mark.parametrize("scope,reason",[
    (StrengthPolicyScope(role="MAX_STRENGTH",phase="BASE",objectives=("triathlon",)),"UNSUPPORTED_STRENGTH_ROLE"),
    (StrengthPolicyScope(role="GENERAL_STRENGTH",phase="UNKNOWN",objectives=("triathlon",)),"UNSUPPORTED_PHASE"),
    (StrengthPolicyScope(role="GENERAL_STRENGTH",phase="BASE",objectives=()),"SPORT_OBJECTIVE_UNKNOWN"),
    (StrengthPolicyScope(role="GENERAL_STRENGTH",phase="BASE",objectives=("strength_maximum",)),"UNSUPPORTED_SPORT_OBJECTIVE"),
])
def test_policy_not_applicable_does_not_invent_other_strength_types(scope,reason):
    r=select_strength_temporal_policy(scope)
    assert not r.applicable and r.policy_id is None and r.reason==reason


def test_real_policy_only_exposes_known_prescribed_rest_without_guessing_execution(base):
    ctx,artifact,_=base
    before=artifact.model_dump_json()
    report=build_strength_temporal_policy_shadow(ctx,artifact)
    assert artifact.model_dump_json()==before
    assert report.evaluations
    first=report.evaluations[0]
    assert first.estimate.coverage=="partial"
    assert first.estimate.known_subtotal_seconds.minimum==first.estimate.known_subtotal_seconds.maximum==900
    assert first.estimate.duration_seconds is None
    assert first.comparison.status=="INDETERMINATE_PARTIAL"
    assert any(d.reason=="UNILATERAL_COMPLETE_SET_SCOPE_NOT_ASSUMED_BY_GENERIC_POLICY" for d in first.parameter_decisions)
    assert all(c.provenance.source=="derived_prescription" for c in first.estimate.known_components)


def test_specific_tempo_precedes_unknown_execution_and_generic_policy_fills_rest(base):
    ctx,_,item=base;w=single(base)
    tempo=TempoInput(eccentric=value(2),first_pause=value(0),concentric=value(1),final_pause=value(0))
    x=rep(seconds_per_rep=TimingComponent(),tempo=tempo,between_sets=SetRestInput())
    e=evaluate(base,w,explicit(ctx,w,x))
    assert e.estimate.coverage=="complete"
    assert (e.estimate.duration_seconds.minimum,e.estimate.duration_seconds.maximum)==(40,40)
    assert e.parameter_decisions[0].action=="rest_scope_prescribed"


@pytest.mark.parametrize("mode",["timed","isometric"])
def test_explicit_timed_and_isometric_prescriptions_are_preserved(base,mode):
    ctx,_,_=base;w=single(base)
    x=ExerciseExecutionInput(node_path=(0,),mode=mode,per_set=value(20,25),timed_scope="all_sides_included",scope_provenance=P)
    e=evaluate(base,w,explicit(ctx,w,x))
    assert (e.estimate.duration_seconds.minimum,e.estimate.duration_seconds.maximum)==(50,60)
    assert e.estimate.validation_state=="not_evaluated"


def test_specific_unilateral_protocol_and_rest_are_not_overwritten(base):
    ctx,_,_=base;w=single(base,unilateral=True)
    x=rep(seconds_per_rep=value(2),rep_scope="per_side",rep_time_scope="single_side",side_execution="successive",
        side_sequence="within_each_set",side_count=2,side_gap=whole(value(3)),between_sets=SetRestInput(timing=value(7)))
    e=evaluate(base,w,explicit(ctx,w,x))
    assert e.estimate.duration_seconds.minimum==53 # 40 work+6 side gaps+7 rest
    assert e.parameter_decisions[0].action=="specific_rest_preserved"


def test_specific_rest_and_prescribed_rest_value_win_over_any_generic_value(base):
    ctx,_,_=base;w=single(base,rest=45)
    x=rep(seconds_per_rep=value(2),between_sets=SetRestInput(timing=value(7)))
    e=evaluate(base,w,explicit(ctx,w,x))
    assert e.estimate.duration_seconds.minimum==27
    assert e.parameter_decisions[0].source_kind=="explicit_prescription"
    generic=evaluate(base,w)
    assert generic.estimate.known_subtotal_seconds.minimum==45 # uses actual node, not hardcoded90


def test_measured_source_is_not_relabelled_as_prescription(base):
    ctx,_,_=base;w=single(base)
    observed=TimingProvenance(source="measured_segment",source_id="synthetic-measurement",version="test")
    x=rep(seconds_per_rep=value(2),between_sets=SetRestInput(timing=value(7,p=observed)))
    e=evaluate(base,w,explicit(ctx,w,x))
    assert e.parameter_decisions[0].source_kind=="observed_or_measured"
    assert e.estimate.validation_state=="not_evaluated"


def test_unknown_and_no_between_set_occurrence_are_not_filled(base):
    w=single(base,unilateral=True)
    e=evaluate(base,w)
    assert e.estimate.coverage=="unavailable"
    assert e.comparison.status=="UNAVAILABLE"
    w=single(base,sets=1)
    e=evaluate(base,w)
    assert e.not_applicable_components==("(0,).inter_set_rest",)
    assert e.estimate.coverage=="unavailable"


@pytest.mark.parametrize("role",["circuit","superset"])
def test_specific_sequential_blocks_and_transitions_with_policy(base,role):
    from app.domains.planning.models import WorkoutNode
    ctx,_,item=base
    a=single(base,sets=1).definition.steps[0]
    definition=item.workout.definition.model_copy(update={"steps":[WorkoutNode(kind="repeat",repetitions=3,steps=[a,a])]})
    w=item.workout.model_copy(update={"definition":definition,"fingerprint":context_fingerprint({"definition":definition})})
    s=StrengthTimingInputs(snapshot=empty_timing_snapshot(ctx,w),executions=(rep((0,0),seconds_per_rep=value(2)),rep((0,1),seconds_per_rep=value(2))),
        boundaries=(BoundaryTimingInput(after_node_path=(0,0),before_node_path=(0,1),gap=whole(value(4))),),
        repeats=(RepeatTimingInput(declaration=RepeatTiming(node_path=(0,),role=role,sequence="sequential",provenance=P),between_rounds=whole(value(7))),),
        warmup=whole(absent()),cooldown=whole(absent()))
    e=evaluate(base,w,s)
    assert e.estimate.duration_seconds.minimum==86
    assert all(d.action=="specific_rest_preserved" for d in e.parameter_decisions)


@pytest.mark.parametrize("legacy,status,distance",[(20,"LEGACY_BELOW_INTERVAL",-10),(35,"LEGACY_WITHIN_INTERVAL",0),(50,"LEGACY_ABOVE_INTERVAL",10)])
def test_complete_comparison_is_interval_based_not_midpoint(base,legacy,status,distance):
    ctx,_,_=base;w=single(base)
    e=evaluate(base,w,explicit(ctx,w,rep()))
    assert e.estimate.duration_seconds.minimum==30 and e.estimate.duration_seconds.maximum==40
    c=compare_strength_legacy(e.estimate,legacy)
    assert c.status==status and c.signed_distance_to_interval_seconds==distance


def test_partial_comparison_only_proves_a_known_lower_bound(base):
    e=evaluate(base,single(base,rest=90))
    assert e.estimate.coverage=="partial" and e.estimate.known_subtotal_seconds.minimum==90
    c=compare_strength_legacy(e.estimate,60)
    assert c.status=="LEGACY_BELOW_KNOWN_MINIMUM" and c.known_minimum_shortfall_seconds==30
    assert c.signed_distance_to_interval_seconds is None
    assert compare_strength_legacy(e.estimate,1000).status=="INDETERMINATE_PARTIAL"
    assert compare_strength_legacy(e.estimate,None).status=="LEGACY_UNKNOWN"


def test_scope_cannot_receive_forbidden_inputs():
    with pytest.raises(ValidationError):StrengthPolicyScope(role="GENERAL_STRENGTH",phase="BASE",objectives=("triathlon",),legacy_minutes=40)


def test_selection_and_timing_ignore_forbidden_context_variables(base):
    ctx,artifact,item=base
    numeric=[]
    for legacy,minutes,load,budget in ((24,1,Decimal(1),Decimal(1)),(40,5000,Decimal(9999),Decimal(9999))):
        prefs=ctx.preferences.model_copy(update={"availability_slots":tuple(s.model_copy(update={"available_minutes":minutes}) for s in ctx.preferences.availability_slots)})
        training=ctx.training.model_copy(update={"windows":tuple(w.model_copy(update={"total_training_load":load,"total_duration_seconds":legacy*999}) for w in ctx.training.windows)})
        other=ctx.model_copy(update={"preferences":prefs,"training":training})
        other=other.model_copy(update={"fingerprint":context_fingerprint(other.model_dump(exclude={"fingerprint"}))})
        definition=item.workout.definition.model_copy(update={"steps":[n.model_copy(update={"duration":n.duration.model_copy(update={"seconds":legacy*10})}) for n in item.workout.definition.steps]})
        w=item.workout.model_copy(update={"definition":definition,"context_fingerprint":other.fingerprint,"fingerprint":context_fingerprint({"definition":definition,"context":other.fingerprint})})
        p=item.prescription.model_copy(update={"target_duration_minutes":legacy,"target_load":load})
        sample=artifact.model_copy(update={"context_fingerprint":other.fingerprint,"sessions":(item.model_copy(update={"prescription":p,"workout":w}),),
            "weekly_budget_plan":artifact.weekly_budget_plan.model_copy(update={"budgets":tuple(b.model_copy(update={"target_load":budget}) for b in artifact.weekly_budget_plan.budgets)})})
        result=build_strength_temporal_policy_shadow(other,sample).evaluations[0]
        numeric.append((result.policy.policy_id,result.estimate.coverage,result.estimate.known_subtotal_seconds,result.estimate.duration_seconds))
    assert numeric[0]==numeric[1]


def test_specific_invalid_binding_does_not_silently_fall_back(base):
    ctx,_,_=base;w=single(base)
    s=explicit(ctx,w,rep())
    bad=s.model_copy(update={"snapshot":s.snapshot.model_copy(update={"definition_fingerprint":"f"*64})})
    with pytest.raises(ValueError,match="BINDING_MISMATCH"):evaluate(base,w,bad)


@pytest.mark.parametrize("target",[None,6])
def test_application_policy_diagnostic_is_ephemeral_and_legacy_unchanged(monkeypatch,target):
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication,PlanningContextAssembler,ExecutionAdaptationProposalAssembler
    from app.domains.planning.execution_adaptation import build_execution_adaptation_context
    from app.domains.planning.execution_proposals import build_execution_adaptation_proposal_context
    from tests.test_execution_adaptation import context as evidence_context
    from tests.test_planning_preview_application import seeded
    ctx=profile_context();ctx=ctx.model_copy(update={"preferences":ctx.preferences.model_copy(update={"target_sessions_per_week":target})})
    evidence=evidence_context().model_copy(update={"athlete_profile_id":ctx.request.athlete_id,"as_of_date":ctx.request.planning_date})
    proposals=build_execution_adaptation_proposal_context(build_execution_adaptation_context(evidence))
    monkeypatch.setattr(PlanningContextAssembler,"assemble",lambda *a,**k:ctx)
    monkeypatch.setattr(ExecutionAdaptationProposalAssembler,"assemble",lambda *a,**k:proposals)
    engine,_,_,user,_=seeded()
    with Session(engine) as db:
        app=PlanningPreviewApplication(db);row=app.generate(request=ctx.request,user_id=user)
        assert app.strength_temporal_policy_report.artifact_fingerprint==row.artifact_fingerprint
        assert all(e.comparison.legacy_seconds==24*60 for e in app.strength_temporal_policy_report.evaluations)
        assert "strength_temporal_policy_report" not in row.artifact
        assert all(e.estimate.coverage in {"partial","unavailable"} for e in app.strength_temporal_policy_report.evaluations)
        monkeypatch.setattr(PlanningContextAssembler,"assemble",lambda *a,**k:(_ for _ in ()).throw(ValueError("unavailable")))
        with pytest.raises(ValueError):app.generate(request=ctx.request,user_id=user)
        assert app.strength_temporal_policy_report is None


def test_source_not_applicable_can_still_use_valid_specific_prescription(base):
    ctx,artifact,item=base
    goal=ctx.goals[0].model_copy(update={"category":"unsupported_strength_goal"})
    other=ctx.model_copy(update={"goals":(goal,)}) # fingerprint stays bound to same synthetic fixture
    w=single(base)
    p=item.prescription
    specific=explicit(other,w,rep())
    result=prescribe_strength_temporal_inputs(other,p,w,specific)
    assert not result.selection.applicable
    assert result.decisions[0].action=="specific_rest_preserved"


def test_duplicate_and_orphan_specific_inputs_are_explicit_errors(base):
    ctx,artifact,item=base
    s=explicit(ctx,item.workout,rep())
    with pytest.raises(ValueError,match="DUPLICATE"):build_strength_temporal_policy_shadow(ctx,artifact,(s,s))
    orphan=s.model_copy(update={"snapshot":s.snapshot.model_copy(update={"workout_fingerprint":"f"*64})})
    with pytest.raises(ValueError,match="ORPHAN"):build_strength_temporal_policy_shadow(ctx,artifact,(orphan,))


def test_goal_order_does_not_change_selected_policy():
    a=StrengthPolicyScope(role="GENERAL_STRENGTH",phase="BASE",objectives=("running","triathlon"))
    b=a.model_copy(update={"objectives":tuple(reversed(a.objectives))})
    assert select_strength_temporal_policy(a).policy_id==select_strength_temporal_policy(b).policy_id


def test_real_double_artifact_and_capacity_are_unchanged():
    from collections import defaultdict
    ctx=profile_context()
    prefs=ctx.preferences.model_copy(update={"availability_slots":tuple(s for s in ctx.preferences.availability_slots if s.weekday!=3)})
    ctx=ctx.model_copy(update={"preferences":prefs})
    artifact=pipeline(ctx)[0]
    before=artifact.model_dump_json();report=build_strength_temporal_policy_shadow(ctx,artifact)
    assert artifact.model_dump_json()==before and report.artifact_fingerprint==artifact.fingerprint
    paired=False
    for week in artifact.session_plan.weeks:
        days=defaultdict(list)
        for p in week.sessions:
            if p.discipline!="competition":days[p.date].append(p)
        for day,ss in days.items():
            paired|={s.discipline for s in ss}=={"swimming","strength"}
            assert len(ss)<=prefs.max_sessions_per_day
            assert sum(s.target_duration_minutes for s in ss)<=next(x.available_minutes for x in prefs.availability_slots if x.weekday==day.weekday())
    assert paired


def test_specific_snapshot_keeps_its_provenance_and_no_second_rest(base):
    from app.domains.planning.strength_timing import ExerciseTiming,PauseTiming
    ctx,_,_=base;w=single(base)
    observed=TimingProvenance(source="measured_segment",source_id="synthetic-segment",version="test")
    snapshot=empty_timing_snapshot(ctx,w).model_copy(update={"exercises":(ExerciseTiming(node_path=(0,),
        sets_scope="all_sides_included",execution_per_set=value(10,p=observed),
        pauses=(PauseTiming(after_sets=(1,),timing=value(3,p=observed)),)),),"warmup":absent(),"cooldown":absent()})
    result=evaluate(base,w,StrengthTimingInputs(snapshot=snapshot))
    assert result.estimate.duration_seconds.minimum==23
    assert result.parameter_decisions[0].source_kind=="observed_or_measured"
    assert result.parameter_decisions[0].action=="specific_snapshot_preserved"
