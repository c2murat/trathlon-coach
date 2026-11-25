"""Independent strength timing, exclusively observational.

Work covers execution only. Inter-set pauses occupy explicit after-set slots.
Each exercise boundary covers the WHOLE gap, including final rest and setup.
Warmup/cooldown cover the whole prefix/tail. These scopes are disjoint by
construction; a final-set pause cannot also be added to an exercise boundary.
No durations are inferred from legacy allocated time, RPE, or training history.
"""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from app.domains.planning.contracts import FrozenModel, context_fingerprint
from app.domains.planning.workout_builder import structured_workout_payload


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, strict=True)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
Index = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, ge=1)]
NodePath = tuple[Index, ...]
# Computational bound, not a physiological cap or planner restriction.
MAX_TIMING_EVENTS = 10000


class SecondsInterval(FrozenModel):
    minimum: int = Field(strict=True, ge=0)
    maximum: int = Field(strict=True, ge=0)
    unit: Literal["seconds"] = "seconds"

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum > self.maximum:
            raise ValueError("TIMING_RANGE_REVERSED")
        return self


class TimingProvenance(FrozenModel):
    source: Literal["explicit_prescription", "measured_segment", "reviewed_timing_policy", "configurable_prescription", "derived_prescription"]
    source_id: Text
    version: Text
    derivation: Text | None = None
    inputs: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def derivation_evidence(self):
        if self.source == "derived_prescription":
            if not self.derivation or not self.inputs:
                raise ValueError("DERIVATION_REQUIRES_INDEPENDENT_INPUT_REFERENCES")
        elif self.derivation is not None or self.inputs:
            raise ValueError("ONLY_DERIVED_PROVENANCE_HAS_DERIVATION_INPUTS")
        return self


class TimingComponent(FrozenModel):
    state: Literal["unknown", "specified", "not_prescribed", "not_applicable", "partial"] = "unknown"
    seconds: SecondsInterval | None = None
    provenance: TimingProvenance | None = None
    missing: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def evidence(self):
        if self.state in {"specified", "partial"} and (self.seconds is None or self.provenance is None):
            raise ValueError("SPECIFIED_TIMING_REQUIRES_INTERVAL_AND_PROVENANCE")
        if self.state in {"not_prescribed", "not_applicable"} and (self.seconds is not None or self.provenance is None):
            raise ValueError("ABSENCE_REQUIRES_PROVENANCE_WITHOUT_INTERVAL")
        if self.state == "unknown" and (self.seconds is not None or self.provenance is not None):
            raise ValueError("UNKNOWN_TIMING_CANNOT_HIDE_EVIDENCE")
        if (self.state == "partial") != bool(self.missing):
            raise ValueError("ONLY_PARTIAL_TIMING_HAS_MISSING_COMPONENTS")
        return self


class PauseTiming(FrozenModel):
    after_sets: tuple[Positive, ...] = Field(min_length=1)
    timing: TimingComponent
    scope: Literal["between_execution_sets_only"] = "between_execution_sets_only"

    @field_validator("after_sets")
    @classmethod
    def occurrences(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("DUPLICATE_PAUSE_OCCURRENCE")
        return tuple(sorted(values))


class ExerciseTiming(FrozenModel):
    node_path: NodePath = Field(min_length=1)
    execution_per_set: TimingComponent = Field(default_factory=TimingComponent)
    execution_scope: Literal["work_only_excluding_rest_and_setup"] = "work_only_excluding_rest_and_setup"
    # all_sides_included: node.sets complete sets; per_side: node.sets per
    # explicitly declared side. No multiplication is inferred from unilateral.
    sets_scope: Literal["unknown", "all_sides_included", "per_side"] = "unknown"
    side_count: Positive | None = None
    pauses: tuple[PauseTiming, ...] = ()
    internal_per_set: TimingComponent | None = None

    @model_validator(mode="after")
    def scopes(self):
        if (self.sets_scope == "per_side") != (self.side_count is not None):
            raise ValueError("SIDE_COUNT_REQUIRES_EXPLICIT_PER_SIDE_SCOPE")
        if self.sets_scope == "unknown" and self.pauses:
            raise ValueError("PAUSES_REQUIRE_RESOLVED_SET_SCOPE")
        work = self.execution_per_set
        if work.state in {"not_prescribed", "not_applicable"} or (work.state == "specified" and work.seconds.minimum == 0):
            raise ValueError("EXECUTION_SET_REQUIRES_POSITIVE_WORK_TIME")
        occurrences = [i for pause in self.pauses for i in pause.after_sets]
        if len(occurrences) != len(set(occurrences)):
            raise ValueError("OVERLAPPING_PAUSE_GROUPS")
        return self

    @field_validator("pauses")
    @classmethod
    def canonical_pauses(cls, values):
        return tuple(sorted(values, key=lambda p: p.after_sets))


class TransitionTiming(FrozenModel):
    after_node_path: NodePath = Field(min_length=1)
    before_node_path: NodePath = Field(min_length=1)
    timing: TimingComponent
    scope: Literal["whole_gap_including_final_rest_and_setup"] = "whole_gap_including_final_rest_and_setup"


class RepeatTiming(FrozenModel):
    node_path: NodePath = Field(min_length=1)
    sequence: Literal["unknown", "sequential", "simultaneous"] = "unknown"
    role: Literal["sequence", "circuit", "superset", "unknown"] = "unknown"
    between_rounds: TimingComponent = Field(default_factory=TimingComponent)
    provenance: TimingProvenance | None = None

    @model_validator(mode="after")
    def declared_order(self):
        if self.sequence != "unknown" and self.provenance is None:
            raise ValueError("REPEAT_ORDER_REQUIRES_PROVENANCE")
        return self


class EdgeNodeTiming(FrozenModel):
    node_path: NodePath = Field(min_length=1)
    timing: TimingComponent


class StrengthTimingSnapshot(FrozenModel):
    schema_version: Literal[1, 2] = 1
    policy_version: Text
    athlete_id: UUID
    context_fingerprint: Digest
    workout_fingerprint: Digest
    definition_fingerprint: Digest
    exercises: tuple[ExerciseTiming, ...] = ()
    transitions: tuple[TransitionTiming, ...] = ()
    repeats: tuple[RepeatTiming, ...] = ()
    edge_nodes: tuple[EdgeNodeTiming, ...] = ()
    warmup: TimingComponent = Field(default_factory=TimingComponent)
    cooldown: TimingComponent = Field(default_factory=TimingComponent)
    edge_scope: Literal["whole_prefix_and_tail_including_setup_and_final_rest"] = "whole_prefix_and_tail_including_setup_and_final_rest"

    @field_validator("exercises")
    @classmethod
    def exercise_paths(cls, values):
        paths = [v.node_path for v in values]
        if len(paths) != len(set(paths)):
            raise ValueError("DUPLICATE_TIMING_NODE_PATH")
        return tuple(sorted(values, key=lambda v: v.node_path))

    @field_validator("transitions")
    @classmethod
    def transition_paths(cls, values):
        paths = [(v.after_node_path, v.before_node_path) for v in values]
        if len(paths) != len(set(paths)):
            raise ValueError("DUPLICATE_EXERCISE_BOUNDARY")
        return tuple(sorted(values, key=lambda v: (v.after_node_path, v.before_node_path)))

    @field_validator("repeats", "edge_nodes")
    @classmethod
    def other_paths(cls, values):
        paths = [v.node_path for v in values]
        if len(paths) != len(set(paths)):
            raise ValueError("DUPLICATE_TIMING_NODE_PATH")
        return tuple(sorted(values, key=lambda v: v.node_path))


class KnownTimingComponent(FrozenModel):
    component_id: str
    seconds: SecondsInterval
    occurrences: int
    provenance: TimingProvenance


class StrengthTimingEstimate(FrozenModel):
    algorithm_version: str = "0.8G.2E.1-strength-timing-shadow-4b2"
    mode: Literal["SHADOW_NO_PLANNING_EFFECT"] = "SHADOW_NO_PLANNING_EFFECT"
    athlete_id: UUID
    workout_fingerprint: str
    timing_snapshot_fingerprint: str | None
    coverage: Literal["complete", "partial", "unavailable"]
    duration_seconds: SecondsInterval | None
    known_subtotal_seconds: SecondsInterval
    known_components: tuple[KnownTimingComponent, ...]
    missing_components: tuple[str, ...]
    diagnostics: tuple[str, ...]
    # Contract validation and complete coverage do not establish predictive
    # accuracy. No empirical calibration protocol is implemented in this block.
    validation_state: Literal["not_evaluated"] = "not_evaluated"


def definition_fingerprint(workout):
    return context_fingerprint(structured_workout_payload(workout.definition)) if workout.definition is not None else None


def empty_timing_snapshot(context, workout):
    """Bind identities only. Never fill a single temporal component."""
    if workout.context_fingerprint != context.fingerprint or workout.definition is None:
        raise ValueError("TIMING_REFERENCE_CONTEXT_OR_DEFINITION_MISMATCH")
    return StrengthTimingSnapshot(policy_version="strength-timing-shadow-1", athlete_id=context.request.athlete_id,
        context_fingerprint=context.fingerprint, workout_fingerprint=workout.fingerprint,
        definition_fingerprint=definition_fingerprint(workout))


def estimate_strength_timing(context, workout, snapshot: StrengthTimingSnapshot | None = None):
    """Read only sets/side declarations and independently supplied time ranges.

    Full definition hashing (including allocated seconds) verifies binding only;
    that hash and legacy node durations never participate in timing arithmetic.
    """
    known = []
    missing = []
    diagnostics = []

    def result(error=None):
        if error is not None:
            # No partial values survive an invalid identity/path/occurrence.
            return StrengthTimingEstimate(athlete_id=context.request.athlete_id, workout_fingerprint=workout.fingerprint,
                timing_snapshot_fingerprint=None, coverage="unavailable", duration_seconds=None,
                known_subtotal_seconds=SecondsInterval(minimum=0, maximum=0), known_components=(),
                missing_components=("valid_timing_reference_or_structure",), diagnostics=(error,))
        subtotal = SecondsInterval(minimum=sum(k.seconds.minimum for k in known), maximum=sum(k.seconds.maximum for k in known))
        coverage = "complete" if not missing else "partial" if known else "unavailable"
        return StrengthTimingEstimate(athlete_id=context.request.athlete_id, workout_fingerprint=workout.fingerprint,
            timing_snapshot_fingerprint=context_fingerprint(snapshot) if snapshot else None,
            coverage=coverage, duration_seconds=subtotal if coverage == "complete" else None,
            known_subtotal_seconds=subtotal, known_components=tuple(known), missing_components=tuple(missing),
            diagnostics=tuple(diagnostics) + (("NO_INDEPENDENT_TIMING_DATA",) if not known else ()))

    if workout.context_fingerprint != context.fingerprint:
        return result("WORKOUT_CONTEXT_MISMATCH")
    if snapshot is not None:
        try:
            # FrozenModel.model_copy can bypass construction validators. Keep
            # this calculation boundary defensive and canonical, too.
            snapshot = StrengthTimingSnapshot.model_validate(snapshot.model_dump(mode="python"))
        except ValidationError:
            return result("INVALID_TIMING_SNAPSHOT_CONTRACT")
    if snapshot is not None and (snapshot.athlete_id != context.request.athlete_id or snapshot.context_fingerprint != context.fingerprint
        or snapshot.workout_fingerprint != workout.fingerprint or snapshot.definition_fingerprint != definition_fingerprint(workout)):
        return result("TIMING_SNAPSHOT_BINDING_MISMATCH")
    if not workout.buildable or workout.definition is None:
        return result("WORKOUT_STRUCTURE_UNAVAILABLE")
    nodes = workout.definition.steps
    if workout.definition.sport != "strength":
        return result("NOT_A_STRENGTH_WORKOUT")
    # Keep the 4B.1 fail-closed behavior unless repeat semantics were supplied.
    has_repeat = any(n.kind == "repeat" for n in nodes)
    if has_repeat and (snapshot is None or not snapshot.repeats):
        return result("UNSUPPORTED_REPEAT_STRUCTURE")
    warm = [(i,) for i, n in enumerate(nodes) if n.kind == "step" and n.phase == "warmup"]
    cool = [(i,) for i, n in enumerate(nodes) if n.kind == "step" and n.phase == "cooldown"]
    if len(warm) > 1 or len(cool) > 1 or (warm and warm[0] != (0,)) or (cool and cool[0] != (len(nodes)-1,)):
        return result("UNSUPPORTED_EDGE_NODE_POSITION")
    edge_paths = set(warm + cool)
    tree = {}
    repeat_paths = set()
    expected_boundaries = set()
    structure_error = None

    def collect(group, parent=()):
        nonlocal structure_error
        paths = [parent + (i,) for i, n in enumerate(group) if parent + (i,) not in edge_paths]
        expected_boundaries.update(zip(paths, paths[1:]))
        for path in paths:
            node = group[path[-1]]
            tree[path] = node
            if len(tree) > MAX_TIMING_EVENTS or len(path) > 32:
                structure_error = "TIMING_OCCURRENCE_LIMIT_EXCEEDED"
                return
            if node.kind == "repeat":
                repeat_paths.add(path)
                collect(node.steps, path)
            elif node.phase != "strength":
                structure_error = "UNSUPPORTED_FLAT_NODE_PHASE"
    collect(nodes)
    if structure_error:
        return result(structure_error)
    if not tree:
        return result("NO_STRENGTH_EXECUTION_NODES")
    exercises = {e.node_path: e for e in snapshot.exercises} if snapshot else {}
    boundaries = {(t.after_node_path, t.before_node_path): t for t in snapshot.transitions} if snapshot else {}
    repeats = {r.node_path: r for r in snapshot.repeats} if snapshot else {}
    edges = {e.node_path: e.timing for e in snapshot.edge_nodes} if snapshot else {}
    leaves = {p for p, n in tree.items() if n.kind == "step"}
    if set(exercises) - leaves or set(boundaries) - expected_boundaries or set(repeats) - repeat_paths or set(edges) - edge_paths:
        return result("TIMING_NODE_PATH_OR_BOUNDARY_MISMATCH")

    def add(key, component, occurrences=1):
        if component is None or component.state == "unknown":
            missing.append(key)
            return
        interval = component.seconds if component.state in {"specified", "partial"} else SecondsInterval(minimum=0, maximum=0)
        known.append(KnownTimingComponent(component_id=key,
            seconds=SecondsInterval(minimum=interval.minimum * occurrences, maximum=interval.maximum * occurrences),
            occurrences=occurrences, provenance=component.provenance))
        if component.state == "partial":
            missing.extend(f"{key}.{part}" for part in component.missing)

    def edge_component(paths, global_component):
        actual = edges.get(paths[0]) if paths else None
        if actual is not None and actual.state != "unknown" and global_component is not None and global_component.state != "unknown":
            return None, "DUPLICATE_EDGE_TIMING_SOURCE"
        chosen = actual if actual is not None and actual.state != "unknown" else global_component
        if paths and chosen is not None and chosen.state in {"not_prescribed", "not_applicable"}:
            return None, "EDGE_NODE_ABSENCE_CONFLICT"
        return chosen, None

    prefix, error = edge_component(warm, snapshot.warmup if snapshot else None)
    if error:
        return result(error)
    tail, error = edge_component(cool, snapshot.cooldown if snapshot else None)
    if error:
        return result(error)
    add("warmup_whole_prefix", prefix)
    event_count = 0
    runtime_error = None

    def label(path):
        return "steps[" + "][".join(map(str, path)) + "]"

    def visit_group(group, parent=(), multiplier=1):
        nonlocal event_count, runtime_error
        paths = [parent+(i,) for i, n in enumerate(group) if parent+(i,) not in edge_paths]
        for path in paths:
            node = tree[path]
            key = label(path)
            if node.kind == "repeat":
                declaration = repeats.get(path)
                if declaration is None or declaration.sequence != "sequential":
                    missing.append(key + ".repeat_execution_semantics")
                    diagnostics.append("UNSUPPORTED_SIMULTANEOUS_BLOCK" if declaration and declaration.sequence == "simultaneous" else "AMBIGUOUS_REPEAT_ORDER")
                    continue
                rounds = node.repetitions
                if multiplier * rounds > MAX_TIMING_EVENTS:
                    runtime_error = "TIMING_OCCURRENCE_LIMIT_EXCEEDED"
                    return
                visit_group(node.steps, path, multiplier * rounds)
                if runtime_error:
                    return
                add(key + ".between_rounds", declaration.between_rounds, multiplier * (rounds-1))
                continue
            timing = exercises.get(path)
            if timing is None or timing.sets_scope == "unknown":
                missing.extend((key + ".execution_scope", key + ".execution", key + ".rest_occurrences"))
                continue
            if timing.sets_scope == "per_side" and node.unilateral is not True:
                runtime_error = "UNILATERAL_SCOPE_CONFLICT"
                return
            sets = node.sets * (timing.side_count if timing.sets_scope == "per_side" else 1)
            event_count += sets * multiplier
            if event_count > MAX_TIMING_EVENTS:
                runtime_error = "TIMING_OCCURRENCE_LIMIT_EXCEEDED"
                return
            pauses = {i: p.timing for p in timing.pauses for i in p.after_sets}
            if any(i >= sets for i in pauses):
                runtime_error = "INVALID_PAUSE_OCCURRENCE_FINAL_SET_OR_OUT_OF_RANGE"
                return
            add(key + ".execution", timing.execution_per_set, sets * multiplier)
            if timing.internal_per_set is not None:
                add(key + ".internal_per_set", timing.internal_per_set, sets * multiplier)
            for i in range(1, sets):
                add(f"{key}.pause_after_set[{i}]", pauses.get(i), multiplier)
        for left, right in zip(paths, paths[1:]):
            boundary = boundaries.get((left, right))
            add(f"gap:{label(left)}->{label(right)}", boundary.timing if boundary else None, multiplier)
    visit_group(nodes)
    if runtime_error:
        return result(runtime_error)
    add("cooldown_whole_tail", tail)

    return result()


class StrengthTimingShadowReport(FrozenModel):
    mode: Literal["SHADOW_NO_PLANNING_EFFECT"] = "SHADOW_NO_PLANNING_EFFECT"
    athlete_id: UUID
    artifact_fingerprint: str
    estimates: tuple[StrengthTimingEstimate, ...]
    diagnostics: tuple[str, ...] = ()


def build_strength_timing_shadow(context, artifact, snapshots: tuple[StrengthTimingSnapshot, ...] = ()):
    if artifact.athlete_id != context.request.athlete_id or artifact.context_fingerprint != context.fingerprint:
        raise ValueError("STRENGTH_TIMING_ARTIFACT_CONTEXT_MISMATCH")
    workouts = tuple(s.workout for s in artifact.sessions if s.prescription.discipline == "strength")
    by_key = {}
    invalid = set()
    diagnostics = []
    for snapshot in snapshots:
        key = snapshot.workout_fingerprint
        if key in by_key:
            invalid.add(key)
            diagnostics.append("DUPLICATE_WORKOUT_TIMING_SNAPSHOT")
        by_key[key] = snapshot
    if set(by_key) - {w.fingerprint for w in workouts}:
        diagnostics.append("ORPHAN_WORKOUT_TIMING_SNAPSHOT")
    estimates = tuple(estimate_strength_timing(context, w, by_key.get(w.fingerprint)) for w in workouts)
    # Duplicate evidence is never resolved by silently choosing one input.
    estimates = tuple(e.model_copy(update={"coverage": "unavailable", "duration_seconds": None,
        "timing_snapshot_fingerprint": None,
        "known_subtotal_seconds": SecondsInterval(minimum=0, maximum=0), "known_components": (),
        "missing_components": ("unique_timing_snapshot",), "diagnostics": ("DUPLICATE_WORKOUT_TIMING_SNAPSHOT",)})
        if e.workout_fingerprint in invalid else e for e in estimates)
    return StrengthTimingShadowReport(athlete_id=context.request.athlete_id, artifact_fingerprint=artifact.fingerprint,
        estimates=estimates, diagnostics=tuple(sorted(set(diagnostics))))
