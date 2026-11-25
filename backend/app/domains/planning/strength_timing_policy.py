"""Versioned temporal prescription and post-estimate comparison, shadow only.

The sole generic prescription is a scope rule for existing bilateral inter-set
rests. No new numeric duration, tempo, rest, overhead or athlete observation is
created. Specific temporal prescriptions retain ownership of their components.
"""
from datetime import date
from typing import Literal

from pydantic import Field

from app.domains.planning.contracts import FrozenModel
from app.domains.planning.season_structure import SeasonPhase
from app.domains.planning.workout_labels import STRENGTH_VARIANTS
from app.domains.planning.strength_timing import (
    Text, TimingProvenance, SecondsInterval, StrengthTimingEstimate,
    empty_timing_snapshot, estimate_strength_timing,
)
from app.domains.planning.strength_timing_inputs import (
    StrengthTimingInputs, ExerciseExecutionInput, SetRestInput,
    compile_strength_timing_inputs, estimate_strength_timing_inputs,
)


VERSION = "0.8G.2E.1-strength-temporal-prescription-4b3"
SUPPORTED_OBJECTIVES = frozenset(("triathlon", "duathlon", "aquathlon", "running", "cycling", "swimming"))
SUPPORTED_PATTERNS = frozenset(pattern for variant in STRENGTH_VARIANTS for _, pattern, _ in variant)


class StrengthPolicyScope(FrozenModel):
    # Intentionally cannot carry legacy minutes, load, budget or availability.
    role: str
    phase: str
    objectives: tuple[str, ...]


class StrengthPolicySelection(FrozenModel):
    version: str = VERSION
    applicable: bool
    policy_id: str | None
    scope: StrengthPolicyScope
    reason: str
    justification: str = "Existing GENERAL_STRENGTH profiles prescribe rest_seconds; scope policy uses it only between complete bilateral sets, never after the final set."
    source_references: tuple[str, ...] = (
        "session_planning.SessionType.GENERAL_STRENGTH",
        "workout_builder._strength_steps.phase_profiles",
        "models.WorkoutNode.sets/rest_seconds/unilateral",
    )


class StrengthParameterDecision(FrozenModel):
    node_path: tuple[int, ...]
    component: str = "inter_set_rest"
    action: str
    parameter_seconds: int | None = None
    source_kind: Literal["explicit_prescription", "deterministic_derivation", "temporal_prescription_policy",
        "observed_or_measured", "mixed_specific_sources", "unknown"]
    reason: str


class StrengthTemporalPrescription(FrozenModel):
    selection: StrengthPolicySelection
    inputs: StrengthTimingInputs
    decisions: tuple[StrengthParameterDecision, ...]


def strength_policy_scope(context, prescription):
    related = set(prescription.related_goal_ids)
    categories = tuple(sorted({g.category.strip().lower() for g in context.goals
        if g.status == "active" and (not related or g.competition_goal_id in related)}))
    return StrengthPolicyScope(role=prescription.session_type.value, phase=prescription.phase.value, objectives=categories)


def select_strength_temporal_policy(scope):
    if scope.role != "GENERAL_STRENGTH":
        reason = "UNSUPPORTED_STRENGTH_ROLE"
    elif scope.phase not in {p.value for p in SeasonPhase}:
        reason = "UNSUPPORTED_PHASE"
    elif not scope.objectives:
        reason = "SPORT_OBJECTIVE_UNKNOWN"
    elif any(x not in SUPPORTED_OBJECTIVES for x in scope.objectives):
        reason = "UNSUPPORTED_SPORT_OBJECTIVE"
    else:
        return StrengthPolicySelection(applicable=True,
            policy_id="general-strength/" + "+".join(sorted(set(scope.objectives))) + "/bilateral-inter-set-rest",
            scope=scope, reason="EXISTING_GENERAL_STRENGTH_WITH_SUPPORTED_ENDURANCE_OBJECTIVE")
    return StrengthPolicySelection(applicable=False, policy_id=None, scope=scope, reason=reason)


def prescribe_strength_temporal_inputs(context, prescription, workout, specific: StrengthTimingInputs | None = None):
    """Specific sources win. Fill only an unowned, supported rest component.

    This routine never reads target_duration_minutes, target_load, budgets or
    athlete availability. Binding hashes identify data; they are not time inputs.
    """
    selection = select_strength_temporal_policy(strength_policy_scope(context, prescription))
    inputs = StrengthTimingInputs.model_validate(specific.model_dump(mode="python")) if specific else StrengthTimingInputs(
        snapshot=empty_timing_snapshot(context, workout))
    # Reject invalid specific data before considering a generic fallback.
    compiled_specific = compile_strength_timing_inputs(context, workout, inputs)
    if specific is not None:
        checked = estimate_strength_timing(context, workout, compiled_specific.snapshot)
        nonfatal = {"NO_INDEPENDENT_TIMING_DATA", "AMBIGUOUS_REPEAT_ORDER", "UNSUPPORTED_SIMULTANEOUS_BLOCK"}
        errors = tuple(d for d in checked.diagnostics if d not in nonfatal)
        if errors:
            raise ValueError("INVALID_SPECIFIC_TIMING_SOURCE:" + ",".join(errors))
    existing = {x.node_path: x for x in inputs.executions}
    snapshot_owned = {x.node_path for x in inputs.snapshot.exercises}
    decisions = []
    policy_source = TimingProvenance(source="configurable_prescription",
        source_id=selection.policy_id or "no-applicable-strength-temporal-policy", version=VERSION)

    def kind(provenance):
        if provenance is None:
            return "unknown"
        return {"explicit_prescription": "explicit_prescription", "measured_segment": "observed_or_measured",
            "derived_prescription": "deterministic_derivation", "configurable_prescription": "temporal_prescription_policy",
            "reviewed_timing_policy": "temporal_prescription_policy"}[provenance.source]

    def visit(nodes, parent=()):
        for i, node in enumerate(nodes):
            path = parent + (i,)
            if node.kind == "repeat":
                visit(node.steps, path)
                continue
            if node.phase != "strength":
                continue
            prior = existing.get(path)
            if path in snapshot_owned:
                entry = next(x for x in inputs.snapshot.exercises if x.node_path == path)
                parts = (entry.execution_per_set,) + tuple(p.timing for p in entry.pauses)
                if entry.internal_per_set is not None:
                    parts += (entry.internal_per_set,)
                kinds = {kind(c.provenance) for c in parts
                    if c.state != "unknown"}
                decisions.append(StrengthParameterDecision(node_path=path, action="specific_snapshot_preserved",
                    source_kind=next(iter(kinds)) if len(kinds) == 1 else "mixed_specific_sources" if kinds else "unknown",
                    reason="SNAPSHOT_PATH_OWNS_COMPONENTS_NO_SILENT_MERGE"))
                continue
            if prior and (prior.between_sets.from_prescription or prior.between_sets.timing.state != "unknown"):
                decisions.append(StrengthParameterDecision(node_path=path, action="specific_rest_preserved",
                    source_kind="deterministic_derivation" if prior.between_sets.from_prescription else kind(prior.between_sets.timing.provenance),
                    reason="SPECIFIC_VALID_SOURCE_PRECEDES_GENERIC_POLICY"))
                continue
            if not selection.applicable:
                reason = selection.reason
            elif node.movement_pattern not in SUPPORTED_PATTERNS:
                reason = "EXERCISE_PATTERN_NOT_IN_CURRENT_CATALOG"
            elif node.unilateral is not False:
                reason = "UNILATERAL_COMPLETE_SET_SCOPE_NOT_ASSUMED_BY_GENERIC_POLICY"
            elif node.sets <= 1:
                decisions.append(StrengthParameterDecision(node_path=path, action="not_applicable",
                    source_kind="temporal_prescription_policy", reason="NO_BETWEEN_SET_OCCURRENCE"))
                continue
            elif node.rest_seconds is None:
                reason = "PRESCRIBED_REST_UNAVAILABLE"
            else:
                rest = SetRestInput(from_prescription=True, scope_provenance=policy_source)
                existing[path] = prior.model_copy(update={"between_sets": rest}) if prior else ExerciseExecutionInput(
                    node_path=path, between_sets=rest)
                decisions.append(StrengthParameterDecision(node_path=path, action="rest_scope_prescribed",
                    parameter_seconds=node.rest_seconds, source_kind="temporal_prescription_policy",
                    reason="USE_EXISTING_REST_BETWEEN_COMPLETE_BILATERAL_SETS_ONLY"))
                continue
            decisions.append(StrengthParameterDecision(node_path=path, action="withheld", source_kind="unknown", reason=reason))
    if workout.definition is not None:
        visit(workout.definition.steps)
    updated = StrengthTimingInputs.model_validate(inputs.model_copy(update={
        "executions": tuple(existing[k] for k in sorted(existing))}).model_dump(mode="python"))
    return StrengthTemporalPrescription(selection=selection, inputs=updated, decisions=tuple(decisions))


class StrengthLegacyComparison(FrozenModel):
    legacy_seconds: int | None = Field(default=None, ge=0)
    status: Literal["LEGACY_BELOW_INTERVAL", "LEGACY_WITHIN_INTERVAL", "LEGACY_ABOVE_INTERVAL",
        "LEGACY_BELOW_KNOWN_MINIMUM", "INDETERMINATE_PARTIAL", "UNAVAILABLE", "LEGACY_UNKNOWN"]
    signed_distance_to_interval_seconds: int | None = None
    known_minimum_shortfall_seconds: int | None = None
    reason: str


def compare_strength_legacy(estimate, legacy_seconds):
    """Legacy is accessed only here, AFTER independent temporal estimation."""
    if legacy_seconds is None:
        return StrengthLegacyComparison(status="LEGACY_UNKNOWN", reason="LEGACY_DURATION_NOT_AVAILABLE")
    if estimate.coverage == "complete":
        interval = estimate.duration_seconds
        if legacy_seconds < interval.minimum:
            status, distance = "LEGACY_BELOW_INTERVAL", legacy_seconds - interval.minimum
        elif legacy_seconds > interval.maximum:
            status, distance = "LEGACY_ABOVE_INTERVAL", legacy_seconds - interval.maximum
        else:
            status, distance = "LEGACY_WITHIN_INTERVAL", 0
        return StrengthLegacyComparison(legacy_seconds=legacy_seconds, status=status,
            signed_distance_to_interval_seconds=distance, reason="DIAGNOSTIC_DISTANCE_TO_COMPLETE_INTERVAL_NO_ADJUSTMENT")
    if estimate.coverage == "partial":
        minimum = estimate.known_subtotal_seconds.minimum
        if legacy_seconds < minimum:
            return StrengthLegacyComparison(legacy_seconds=legacy_seconds, status="LEGACY_BELOW_KNOWN_MINIMUM",
                known_minimum_shortfall_seconds=minimum - legacy_seconds,
                reason="KNOWN_DISJOINT_COMPONENTS_ALREADY_EXCEED_LEGACY_TOTAL_UNKNOWN")
        return StrengthLegacyComparison(legacy_seconds=legacy_seconds, status="INDETERMINATE_PARTIAL",
            reason="PARTIAL_SUBTOTAL_DOES_NOT_PROVE_TOTAL_FITS_LEGACY_OR_AVAILABILITY")
    return StrengthLegacyComparison(legacy_seconds=legacy_seconds, status="UNAVAILABLE", reason="NO_USABLE_INDEPENDENT_TIMING")


class StrengthTemporalEvaluation(FrozenModel):
    scheduled_date: date
    phase: str
    policy: StrengthPolicySelection
    parameter_decisions: tuple[StrengthParameterDecision, ...]
    estimate: StrengthTimingEstimate
    comparison: StrengthLegacyComparison
    not_applicable_components: tuple[str, ...]
    diagnostics: tuple[str, ...]


class StrengthTemporalPolicyReport(FrozenModel):
    version: str = VERSION
    mode: Literal["SHADOW_NO_PRESCRIPTION_OR_ARTIFACT_EFFECT"] = "SHADOW_NO_PRESCRIPTION_OR_ARTIFACT_EFFECT"
    artifact_fingerprint: str
    evaluations: tuple[StrengthTemporalEvaluation, ...]


def build_strength_temporal_policy_shadow(context, artifact, specific_inputs: tuple[StrengthTimingInputs, ...] = ()):
    if artifact.athlete_id != context.request.athlete_id or artifact.context_fingerprint != context.fingerprint:
        raise ValueError("STRENGTH_TEMPORAL_POLICY_CONTEXT_MISMATCH")
    groups = {}
    for item in specific_inputs:
        groups.setdefault(item.snapshot.workout_fingerprint, []).append(item)
    workouts = {s.workout.fingerprint for s in artifact.sessions if s.prescription.discipline == "strength"}
    if set(groups) - workouts:
        raise ValueError("ORPHAN_SPECIFIC_STRENGTH_TEMPORAL_INPUT")
    results = []
    for item in artifact.sessions:
        p, w = item.prescription, item.workout
        if p.discipline != "strength":
            continue
        values = groups.get(w.fingerprint, ())
        diagnostics = []
        if len(values) > 1:
            raise ValueError("DUPLICATE_SPECIFIC_STRENGTH_TEMPORAL_INPUT")
        prescribed = prescribe_strength_temporal_inputs(context, p, w, values[0] if values else None)
        estimate = estimate_strength_timing_inputs(context, w, prescribed.inputs)
        if estimate.diagnostics:
            diagnostics.extend(estimate.diagnostics)
        not_applicable = tuple(f"{d.node_path}.inter_set_rest" for d in prescribed.decisions if d.action == "not_applicable")
        # This is the only use of effective duration; it cannot feed selection.
        legacy_seconds = p.target_duration_minutes * 60 if p.target_duration_minutes is not None else None
        results.append(StrengthTemporalEvaluation(scheduled_date=p.date, phase=p.phase.value,
            policy=prescribed.selection, parameter_decisions=prescribed.decisions, estimate=estimate,
            comparison=compare_strength_legacy(estimate, legacy_seconds), not_applicable_components=not_applicable,
            diagnostics=tuple(sorted(set(diagnostics)))))
    return StrengthTemporalPolicyReport(artifact_fingerprint=artifact.fingerprint, evaluations=tuple(results))
