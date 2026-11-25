"""Independent prescriptive inputs compiled to the ONE 4B.1 timing model.

No catalog-name/RPE/legacy-duration inference and no temporal defaults. Sources
marked configurable or derived remain prescriptions, never athlete observations.
"""
from pydantic import Field, field_validator, model_validator
from typing import Literal

from app.domains.planning.contracts import FrozenModel
from app.domains.planning.strength_timing import (
    Text, Positive, NodePath, SecondsInterval, TimingProvenance, TimingComponent,
    ExerciseTiming, PauseTiming, TransitionTiming, RepeatTiming, EdgeNodeTiming,
    StrengthTimingSnapshot, StrengthTimingEstimate, StrengthTimingShadowReport,
    definition_fingerprint, estimate_strength_timing, MAX_TIMING_EVENTS,
)


class TimingInputError(ValueError):
    pass


def derived(key, operation, sources):
    refs=set()
    for s in sources:
        if s is not None:
            refs.add(f"{s.source}:{s.source_id}@{s.version}")
            refs.update(s.inputs)
    refs=tuple(sorted(refs))
    if not refs:raise TimingInputError("DERIVATION_SOURCE_MISSING")
    return TimingProvenance(source="derived_prescription", source_id=key, version="strength-inputs-4b2",
        derivation=operation, inputs=refs)


def scaled(component, lo, hi, key, sources=()):
    if component.state=="unknown":return component
    provenance=derived(key,f"interval * count[{lo},{hi}]",(component.provenance,)+tuple(sources))
    interval=component.seconds if component.seconds is not None else SecondsInterval(minimum=0,maximum=0)
    return TimingComponent(state=component.state,seconds=SecondsInterval(minimum=interval.minimum*lo,maximum=interval.maximum*hi)
        if component.state in {"specified","partial"} else None,provenance=provenance,missing=component.missing)


def summed(parts,key,provenance=None):
    known=[(name,c) for name,c in parts if c.state!="unknown"]
    absent=[name for name,c in parts if c.state=="unknown"]
    absent += [f"{name}.{m}" for name,c in known for m in c.missing]
    if not known:return TimingComponent()
    p=derived(key,"sum_disjoint",tuple(c.provenance for _,c in known)+(provenance,))
    total=SecondsInterval(minimum=sum(c.seconds.minimum if c.seconds else 0 for _,c in known),
        maximum=sum(c.seconds.maximum if c.seconds else 0 for _,c in known))
    return TimingComponent(state="partial" if absent else "specified",seconds=total,provenance=p,missing=tuple(absent))


class GapTimingInput(FrozenModel):
    purpose: Literal["exercise_change","equipment_change","station_setup","side_change","round_boundary","session_prefix","session_tail","other"]="other"
    whole: TimingComponent | None=None
    rest: TimingComponent=Field(default_factory=TimingComponent)
    transition: TimingComponent=Field(default_factory=TimingComponent)
    preparation: TimingComponent=Field(default_factory=TimingComponent)
    relationship: Literal["unknown","disjoint","included_in_rest"]="unknown"
    provenance: TimingProvenance | None=None

    @model_validator(mode="after")
    def scopes(self):
        if self.whole is not None and (self.relationship!="unknown" or any(c.state!="unknown" for c in (self.rest,self.transition,self.preparation))):
            raise ValueError("WHOLE_GAP_CANNOT_HAVE_ANOTHER_TIMING_SOURCE")
        if self.relationship!="unknown" and self.provenance is None:
            raise ValueError("GAP_RELATIONSHIP_REQUIRES_PROVENANCE")
        return self

    def compile(self,key):
        if self.whole is not None:return self.whole
        if self.relationship=="unknown":return TimingComponent()
        if self.relationship=="disjoint":
            return summed((("rest",self.rest),("transition",self.transition),("preparation",self.preparation)),key,self.provenance)
        if self.rest.state=="unknown":return TimingComponent()
        bound=self.rest.seconds.maximum if self.rest.seconds else 0
        if self.rest.state!="partial" and any(c.seconds and c.seconds.minimum>bound for c in (self.transition,self.preparation)):
            raise TimingInputError("INCLUDED_COMPONENT_EXCEEDS_CONTAINER")
        p=derived(key,"rest_includes_transition_and_preparation_count_once",(self.rest.provenance,self.transition.provenance,self.preparation.provenance,self.provenance))
        return self.rest.model_copy(update={"provenance":p})


class TempoInput(FrozenModel):
    eccentric: TimingComponent=Field(default_factory=TimingComponent)
    first_pause: TimingComponent=Field(default_factory=TimingComponent)
    concentric: TimingComponent=Field(default_factory=TimingComponent)
    final_pause: TimingComponent=Field(default_factory=TimingComponent)
    unit: Literal["seconds_per_full_repetition"]="seconds_per_full_repetition"

    def compile(self,key):
        return summed(tuple((name,getattr(self,name)) for name in ("eccentric","first_pause","concentric","final_pause")),key)


class RepetitionRange(FrozenModel):
    minimum: Positive
    maximum: Positive
    unit: Literal["repetitions"]="repetitions"
    provenance: TimingProvenance

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum>self.maximum:raise ValueError("REPETITION_RANGE_REVERSED")
        return self


class SetRestInput(FrozenModel):
    timing: TimingComponent=Field(default_factory=TimingComponent)
    from_prescription: bool=Field(default=False,strict=True)
    scope: Literal["between_complete_sets_only_no_final_rest"]="between_complete_sets_only_no_final_rest"
    scope_provenance: TimingProvenance | None=None

    @model_validator(mode="after")
    def source(self):
        if self.from_prescription and (self.scope_provenance is None or self.timing.state!="unknown"):
            raise ValueError("REST_FROM_WORKOUT_REQUIRES_SCOPE_WITHOUT_DUPLICATE_VALUE")
        return self


class ExerciseExecutionInput(FrozenModel):
    node_path: NodePath=Field(min_length=1)
    mode: Literal["unknown","repetitions","timed","isometric"]="unknown"
    seconds_per_rep: TimingComponent=Field(default_factory=TimingComponent)
    tempo: TempoInput | None=None
    per_set: TimingComponent=Field(default_factory=TimingComponent)
    repetitions: RepetitionRange | None=None
    rep_scope: Literal["unknown","total","per_side"]="unknown"
    rep_time_scope: Literal["unknown","counted_cycle","single_side","simultaneous_cycle"]="unknown"
    side_execution: Literal["unknown","not_applicable","successive","simultaneous"]="unknown"
    side_sequence: Literal["unknown","within_each_set","all_sets_per_side"]="unknown"
    side_count: Positive | None=None
    timed_scope: Literal["unknown","all_sides_included","per_side"]="unknown"
    side_gap: GapTimingInput | None=None
    side_gap_occurrences: Positive | None=None
    between_sets: SetRestInput=Field(default_factory=SetRestInput)
    scope_provenance: TimingProvenance | None=None

    @model_validator(mode="after")
    def exclusive_sources(self):
        if (self.rep_scope!="unknown" or self.timed_scope!="unknown" or self.side_count is not None) and self.scope_provenance is None:
            raise ValueError("EXECUTION_SCOPE_REQUIRES_PROVENANCE")
        if self.tempo is not None and self.seconds_per_rep.state!="unknown":raise ValueError("TEMPO_AND_PER_REP_TIME_CONFLICT")
        if self.mode!="repetitions" and (self.tempo is not None or self.seconds_per_rep.state!="unknown" or self.repetitions is not None):
            raise ValueError("REPETITION_DATA_REQUIRES_REPETITION_MODE")
        if self.mode not in {"timed","isometric"} and self.per_set.state!="unknown":raise ValueError("PER_SET_TIME_REQUIRES_TIMED_MODE")
        if self.mode=="repetitions" and self.per_set.state!="unknown":raise ValueError("EXECUTION_SOURCES_CONFLICT")
        return self


class BoundaryTimingInput(FrozenModel):
    after_node_path: NodePath=Field(min_length=1)
    before_node_path: NodePath=Field(min_length=1)
    gap: GapTimingInput


class RepeatTimingInput(FrozenModel):
    declaration: RepeatTiming
    between_rounds: GapTimingInput | None=None


class EdgeTimingInput(FrozenModel):
    node_path: NodePath=Field(min_length=1)
    gap: GapTimingInput


class StrengthTimingInputs(FrozenModel):
    snapshot: StrengthTimingSnapshot
    executions: tuple[ExerciseExecutionInput,...]=()
    boundaries: tuple[BoundaryTimingInput,...]=()
    repeats: tuple[RepeatTimingInput,...]=()
    edge_nodes: tuple[EdgeTimingInput,...]=()
    warmup: GapTimingInput | None=None
    cooldown: GapTimingInput | None=None

    @model_validator(mode="after")
    def unique(self):
        groups=((x.node_path for x in self.executions),((x.after_node_path,x.before_node_path) for x in self.boundaries),
            (x.declaration.node_path for x in self.repeats),(x.node_path for x in self.edge_nodes))
        for group in groups:
            values=list(group)
            if len(values)!=len(set(values)):raise ValueError("DUPLICATE_TEMPORAL_INPUT_PATH")
        return self


class TimingInputCompilation(FrozenModel):
    inputs: StrengthTimingInputs
    snapshot: StrengthTimingSnapshot
    diagnostics: tuple[str,...]


def compile_strength_timing_inputs(context,workout,inputs):
    # Revalidate even frozen copies. All identity checks precede derivation.
    inputs=StrengthTimingInputs.model_validate(inputs.model_dump(mode="python"))
    base=inputs.snapshot
    if (base.athlete_id!=context.request.athlete_id or base.context_fingerprint!=context.fingerprint
        or workout.context_fingerprint!=context.fingerprint or base.workout_fingerprint!=workout.fingerprint
        or base.definition_fingerprint!=definition_fingerprint(workout)):
        raise TimingInputError("TIMING_INPUT_BINDING_MISMATCH")
    nodes={}
    def collect(group,parent=()):
        for i,node in enumerate(group):
            path=parent+(i,);nodes[path]=node
            if len(nodes)>MAX_TIMING_EVENTS or len(path)>32:raise TimingInputError("TIMING_INPUT_STRUCTURE_LIMIT")
            if node.kind=="repeat":collect(node.steps,path)
    collect(workout.definition.steps)
    diagnostics=[]
    exercises={x.node_path:x for x in base.exercises}
    def node_source(path,field):
        return TimingProvenance(source="explicit_prescription",source_id=f"{workout.fingerprint}/nodes/{path}/{field}",version="workout-schema-1")
    for x in sorted(inputs.executions,key=lambda x:x.node_path):
        node=nodes.get(x.node_path)
        if node is None or node.kind!="step" or node.phase!="strength":raise TimingInputError("EXECUTION_INPUT_NODE_MISMATCH")
        if x.node_path in exercises:raise TimingInputError("DUPLICATE_EXECUTION_INPUT_SOURCE")
        key=f"nodes/{x.node_path}"
        work=TimingComponent();internal=None;resolved=True;sides_factor=1;one_side_work=None
        sources=[x.scope_provenance] if x.scope_provenance else []
        if x.mode=="repetitions":
            if x.repetitions is not None:
                lo,hi=x.repetitions.minimum,x.repetitions.maximum;sources.append(x.repetitions.provenance)
                if node.reps is not None and (lo!=node.reps or hi!=node.reps):raise TimingInputError("REPETITION_PRESCRIPTION_CONFLICT")
            elif node.reps is not None:lo=hi=node.reps;sources.append(node_source(x.node_path,"reps"))
            else:lo=hi=None;diagnostics.append("REPETITION_COUNT_UNKNOWN")
            if x.rep_scope=="total":
                resolved=x.rep_time_scope=="counted_cycle" and (node.unilateral is not True or x.side_execution in {"successive","simultaneous"})
                if x.side_count is not None:raise TimingInputError("TOTAL_REPETITIONS_MUST_NOT_MULTIPLY_SIDES")
            elif x.rep_scope=="per_side":
                if node.unilateral is False:raise TimingInputError("UNILATERAL_INPUT_CONFLICT")
                resolved=node.unilateral is True and x.side_count is not None
                if x.side_execution=="successive" and x.rep_time_scope=="single_side":sides_factor=x.side_count or 1
                elif x.side_execution=="simultaneous" and x.rep_time_scope=="simultaneous_cycle":sides_factor=1
                else:resolved=False
            else:resolved=False
            per_rep=x.tempo.compile(key+"/tempo") if x.tempo else x.seconds_per_rep
            if resolved and lo is not None:
                one_side_work=scaled(per_rep,lo,hi,key+"/one_side_execution",sources)
                work=scaled(per_rep,lo*sides_factor,hi*sides_factor,key+"/repetition_execution",sources)
        elif x.mode in {"timed","isometric"}:
            if x.timed_scope=="all_sides_included":
                if x.side_count is not None:raise TimingInputError("TIMED_ALL_SIDES_MUST_NOT_MULTIPLY")
                work=scaled(x.per_set,1,1,key+"/explicit_complete_set",sources)
                if node.unilateral is True and x.side_execution not in {"successive","simultaneous"}:resolved=False
            elif x.timed_scope=="per_side" and node.unilateral is True and x.side_count and x.side_execution=="successive":
                sides_factor=x.side_count;one_side_work=scaled(x.per_set,1,1,key+"/one_side_timed",sources);work=scaled(x.per_set,sides_factor,sides_factor,key+"/timed_sides",sources)
            else:resolved=False
        else:resolved=False
        if not resolved:
            diagnostics.append("EXECUTION_SEMANTICS_UNKNOWN")
            if node.unilateral is not False:
                exercises[x.node_path]=ExerciseTiming(node_path=x.node_path)
                continue
            # Bilateral complete-set counts are known independently of work
            # time; preserve explicitly scoped rests without guessing work.
            work=TimingComponent()
        # Side gaps are separate from WORK, and occur only between declared
        # successive side groups. The compiled set already includes all sides.
        requires_side_gap=node.unilateral is True and x.side_execution=="successive"
        unknown_layout=requires_side_gap and x.side_sequence=="unknown"
        all_sets=requires_side_gap and x.side_sequence=="all_sets_per_side"
        if all_sets and (x.side_count is None or one_side_work is None):
            unknown_layout=True
            all_sets=False
        if unknown_layout:
            internal=TimingComponent()
            diagnostics.append("SIDE_SET_ORDER_UNKNOWN")
        elif requires_side_gap and not all_sets:
            grouped_count=x.side_count if (x.rep_scope=="per_side" or x.timed_scope=="per_side") else None
            count=grouped_count-1 if grouped_count is not None else x.side_gap_occurrences
            if grouped_count is not None and x.side_gap_occurrences is not None and x.side_gap_occurrences!=count:
                raise TimingInputError("SIDE_GAP_OCCURRENCE_CONFLICT")
            gap=x.side_gap.compile(key+"/side_gap") if x.side_gap else TimingComponent()
            internal=TimingComponent(state="not_applicable",provenance=derived(key+"/no_side_change","one_declared_side_group",sources)) if count==0 else scaled(gap,count,count,key+"/side_gap_occurrences",sources) if count is not None else TimingComponent()
            if count is None:diagnostics.append("SIDE_GAP_OCCURRENCES_UNKNOWN")
        elif not requires_side_gap and (x.side_gap is not None or x.side_gap_occurrences is not None):
            gap=x.side_gap.compile(key+"/side_gap") if x.side_gap else TimingComponent()
            if x.side_gap_occurrences is not None or (gap.seconds and gap.seconds.maximum):
                raise TimingInputError("SIDE_GAP_NOT_APPLICABLE_TO_DECLARED_EXECUTION")
        rest=x.between_sets.timing
        if x.between_sets.from_prescription:
            rest=TimingComponent() if node.rest_seconds is None else TimingComponent(state="specified",
                seconds=SecondsInterval(minimum=node.rest_seconds,maximum=node.rest_seconds),
                provenance=derived(key+"/rest","explicit_rest_seconds_with_declared_between_sets_scope",
                    (node_source(x.node_path,"rest_seconds"),x.between_sets.scope_provenance)))
        if unknown_layout:rest=TimingComponent()
        if all_sets:
            count=x.side_count-1
            if x.side_gap_occurrences is not None and x.side_gap_occurrences!=count:raise TimingInputError("SIDE_GAP_OCCURRENCE_CONFLICT")
            gap=x.side_gap.compile(key+"/side_gap") if x.side_gap else TimingComponent()
            total=node.sets*x.side_count
            if total>MAX_TIMING_EVENTS:raise TimingInputError("TIMING_OCCURRENCE_LIMIT_EXCEEDED")
            side_indices=tuple(range(node.sets,total,node.sets))
            rest_indices=tuple(i for i in range(1,total) if i not in side_indices)
            pauses=tuple(p for p in (
                PauseTiming(after_sets=side_indices,timing=gap) if side_indices else None,
                PauseTiming(after_sets=rest_indices,timing=rest) if rest_indices else None) if p is not None)
            exercises[x.node_path]=ExerciseTiming(node_path=x.node_path,execution_per_set=one_side_work,sets_scope="per_side",
                side_count=x.side_count,pauses=pauses)
        else:
            pauses=(PauseTiming(after_sets=tuple(range(1,node.sets)),timing=rest),) if node.sets>1 else ()
            exercises[x.node_path]=ExerciseTiming(node_path=x.node_path,execution_per_set=work,sets_scope="all_sides_included",
                internal_per_set=internal,pauses=pauses)

    transitions={(x.after_node_path,x.before_node_path):x for x in base.transitions}
    for x in inputs.boundaries:
        key=(x.after_node_path,x.before_node_path)
        if key in transitions:raise TimingInputError("DUPLICATE_BOUNDARY_INPUT_SOURCE")
        transitions[key]=TransitionTiming(after_node_path=key[0],before_node_path=key[1],timing=x.gap.compile(f"boundary/{key}"))
    repeats={x.node_path:x for x in base.repeats}
    for x in inputs.repeats:
        key=x.declaration.node_path
        if key in repeats:raise TimingInputError("DUPLICATE_REPEAT_INPUT_SOURCE")
        if key not in nodes or nodes[key].kind!="repeat":raise TimingInputError("REPEAT_INPUT_NODE_MISMATCH")
        if x.between_rounds is not None and x.declaration.between_rounds.state!="unknown":raise TimingInputError("DUPLICATE_ROUND_GAP_SOURCE")
        repeats[key]=x.declaration.model_copy(update={"between_rounds":x.between_rounds.compile(f"round_gap/{key}")}) if x.between_rounds else x.declaration
    for path,node in nodes.items():
        if node.kind=="repeat" and path not in repeats:repeats[path]=RepeatTiming(node_path=path)
    edges={x.node_path:x for x in base.edge_nodes}
    for x in inputs.edge_nodes:
        if x.node_path in edges:raise TimingInputError("DUPLICATE_EDGE_INPUT_SOURCE")
        edges[x.node_path]=EdgeNodeTiming(node_path=x.node_path,timing=x.gap.compile(f"edge/{x.node_path}"))
    updates={"schema_version":2,"policy_version":base.policy_version+"/independent-inputs-4b2","exercises":tuple(exercises.values()),"transitions":tuple(transitions.values()),"repeats":tuple(repeats.values()),"edge_nodes":tuple(edges.values())}
    for name in ("warmup","cooldown"):
        gap=getattr(inputs,name)
        if gap is not None:
            if getattr(base,name).state!="unknown":raise TimingInputError("DUPLICATE_SESSION_EDGE_INPUT_SOURCE")
            updates[name]=gap.compile(name)
    snapshot=StrengthTimingSnapshot.model_validate(base.model_copy(update=updates).model_dump(mode="python"))
    return TimingInputCompilation(inputs=inputs,snapshot=snapshot,diagnostics=tuple(sorted(set(diagnostics))))


def estimate_strength_timing_inputs(context,workout,inputs):
    from pydantic import ValidationError
    try:
        compiled=compile_strength_timing_inputs(context,workout,inputs)
    except (TimingInputError,ValidationError) as error:
        code=str(error) if isinstance(error,TimingInputError) else "INVALID_STRENGTH_TIMING_INPUT_CONTRACT"
        return StrengthTimingEstimate(athlete_id=context.request.athlete_id,workout_fingerprint=workout.fingerprint,
            timing_snapshot_fingerprint=None,coverage="unavailable",duration_seconds=None,
            known_subtotal_seconds=SecondsInterval(minimum=0,maximum=0),known_components=(),
            missing_components=("valid_independent_inputs",),diagnostics=(code,))
    result=estimate_strength_timing(context,workout,compiled.snapshot)
    return result.model_copy(update={"diagnostics":tuple(sorted(set(result.diagnostics+compiled.diagnostics)))})


def build_strength_timing_inputs_shadow(context,artifact,inputs=()):
    if artifact.athlete_id!=context.request.athlete_id or artifact.context_fingerprint!=context.fingerprint:
        raise TimingInputError("TIMING_INPUT_ARTIFACT_CONTEXT_MISMATCH")
    groups={};diagnostics=[]
    for value in inputs:groups.setdefault(value.snapshot.workout_fingerprint,[]).append(value)
    workouts=tuple(s.workout for s in artifact.sessions if s.prescription.discipline=="strength")
    if set(groups)-{w.fingerprint for w in workouts}:diagnostics.append("ORPHAN_STRENGTH_TIMING_INPUT")
    results=[]
    for w in workouts:
        values=groups.get(w.fingerprint,())
        if len(values)>1:
            e=estimate_strength_timing(context,w)
            results.append(e.model_copy(update={"diagnostics":("DUPLICATE_STRENGTH_TIMING_INPUT",)}))
        else:results.append(estimate_strength_timing_inputs(context,w,values[0]) if values else estimate_strength_timing(context,w))
    return StrengthTimingShadowReport(athlete_id=context.request.athlete_id,artifact_fingerprint=artifact.fingerprint,
        estimates=tuple(results),diagnostics=tuple(diagnostics))
