"""Observe existing strength content without deriving time from allocated time.

No independent repetition tempo, rest scope or transition policy exists in the
current domain. Missing estimates are unknown, never zero or invented constants.
This sidecar is not a prescription, artifact field, or acceptance input.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.domains.planning.contracts import FrozenModel, context_fingerprint
from app.domains.planning.weekly_intent import IntentReason, reason
from app.domains.planning.workout_builder import _progression_level
from app.domains.planning.workout_labels import STRENGTH_VARIANTS


class StrengthExerciseIntent(FrozenModel):
    order: int
    title: str | None
    movement_pattern: str | None
    sets: int | None
    reps: int | None
    rest_seconds: int | None
    unilateral: bool | None
    target_rpe: tuple[Decimal, Decimal] | None
    repeat_multiplier: int = 1
    allocated_seconds: int | None
    duration_source: str = "LEGACY_TOTAL_DIVIDED_AMONG_EXERCISES_NOT_EXECUTION_TIME"


class StrengthStructure(FrozenModel):
    exercises: tuple[StrengthExerciseIntent, ...]
    exercise_count: int
    nominal_sets: int | None
    nominal_repetitions: int | None
    repetitions_scope: str = "RECORDED_REPS_NO_PER_SIDE_MULTIPLIER_ASSUMED"
    variant_index: int | None
    fingerprint: str


class StrengthSessionIntent(FrozenModel):
    athlete_id: UUID
    week_start: date
    scheduled_date: date
    content_anchor_date: date
    occurrence: int
    role: str
    phase: str
    structure: StrengthStructure
    previous_structure: StrengthStructure | None
    proposed_structure: StrengthStructure
    final_structure: StrengthStructure
    structure_cap: int | None = None
    structure_floor: int | None = None
    structure_bounds_reason: str = "NO_STRENGTH_PROGRESSION_CAP_FLOOR_POLICY"
    progression_level: int
    progression_source: str = "workout_builder._progression_level/_strength_steps"
    progression_reason: str
    warmup_intent: str | None = None
    cooldown_intent: str | None = None
    estimated_working_seconds: int | None = None
    estimated_rest_seconds: int | None = None
    estimated_transition_seconds: int | None = None
    structured_estimated_duration_minutes: Decimal | None = None
    legacy_duration_minutes: int | None
    legacy_duration_basis: str
    selected_duration_minutes: int | None
    strength_duration_source: str = "legacy_historical"
    confidence: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    content_source: str = "EXACT_LEGACY_WORKOUT_SNAPSHOT"
    variance_minutes: Decimal | None = None
    fallback_reason: str
    missing_data: tuple[str, ...]
    provenance: tuple[IntentReason, ...]


class StrengthWeekShadow(FrozenModel):
    week_start: date
    phase: str
    sessions: tuple[StrengthSessionIntent, ...]
    strength_minutes_target: int
    placed_strength_minutes: int
    unplaced_strength_sessions: int
    strength_target_source: str
    structured_strength_minutes_target: Decimal | None = None
    strength_duration_source: str = "legacy_historical"
    same_structure_within_week: bool | None


class StructuredStrengthShadowReport(FrozenModel):
    algorithm_version: str = "0.8G.2E.1-strength-intent-shadow-4b"
    mode: Literal["SHADOW_NO_PRESCRIPTION_OR_ARTIFACT_EFFECT"] = "SHADOW_NO_PRESCRIPTION_OR_ARTIFACT_EFFECT"
    athlete_id: UUID
    context_fingerprint: str
    artifact_fingerprint: str
    weeks: tuple[StrengthWeekShadow, ...]


def _leaves(nodes, multiplier=1):
    for node in nodes:
        if node.kind == "repeat":
            yield from _leaves(node.steps or (), multiplier * node.repetitions)
        else:
            yield node, multiplier


def _structure(definition):
    exercises = tuple(StrengthExerciseIntent(
        order=i + 1, title=n.title, movement_pattern=n.movement_pattern, sets=n.sets,
        reps=n.reps, rest_seconds=n.rest_seconds, unilateral=n.unilateral,
        target_rpe=(Decimal(str(n.target.minimum)), Decimal(str(n.target.maximum)))
            if n.target is not None and n.target.metric == "rpe" and n.target.mode == "absolute_range"
            and n.target.minimum is not None and n.target.maximum is not None else None,
        repeat_multiplier=m,
        allocated_seconds=n.duration.seconds if n.duration is not None and n.duration.mode == "time" else None,
    ) for i, (n, m) in enumerate((x for x in _leaves(definition.steps) if x[0].phase == "strength") if definition else ()))
    catalog = tuple((x.title, x.movement_pattern, x.unilateral) for x in exercises)
    variant = next((i for i, values in enumerate(STRENGTH_VARIANTS) if catalog and tuple(values[:len(catalog)]) == catalog), None)
    # Identity describes content only, not the historical time split.
    payload = tuple(x.model_dump(mode="json", exclude={"allocated_seconds", "duration_source"}) for x in exercises)
    return StrengthStructure(exercises=exercises, exercise_count=len(exercises), variant_index=variant,
        nominal_sets=sum(x.sets * x.repeat_multiplier for x in exercises) if exercises and all(x.sets is not None for x in exercises) else None,
        nominal_repetitions=sum(x.sets * x.reps * x.repeat_multiplier for x in exercises)
            if exercises and all(x.sets is not None and x.reps is not None for x in exercises) else None,
        fingerprint=context_fingerprint(payload))


def build_strength_shadow(context, artifact, session_config):
    """Final-pass observational projection, including NULL, with no mutation."""
    from app.domains.planning.session_planning import _historical_sport
    if artifact.athlete_id != context.request.athlete_id or artifact.context_fingerprint != context.fingerprint:
        raise ValueError("STRENGTH_SHADOW_CONTEXT_MISMATCH")
    history = _historical_sport(context, "strength")
    by_week = defaultdict(list)
    for item in artifact.sessions:
        if item.prescription.discipline == "strength":
            by_week[next(w.week_start for w in artifact.session_plan.weeks
                         if w.week_start <= item.prescription.date <= w.week_end)].append(item)
    weeks = []
    previous = {}
    structural = {w.intent.week_start: w for w in artifact.structural_planning.weeks} if artifact.structural_planning else {}
    for week, budget in zip(artifact.session_plan.weeks, artifact.weekly_budget_plan.budgets, strict=True):
        sessions = []
        for occurrence, item in enumerate(sorted(by_week[week.week_start], key=lambda x: (x.prescription.date, x.prescription.session_type.value)), 1):
            p = item.prescription
            original = p.placement.context.get("original_date")
            anchor = date.fromisoformat(original) if p.placement.code == "WEEKLY_STRUCTURAL_DISTRIBUTION" and isinstance(original, str) and p.placement.context.get("distributed_date") == p.date.isoformat() else p.date
            structure = _structure(item.workout.definition)
            prior = previous.get(occurrence)
            missing = ("INDEPENDENT_EXECUTION_TIME_OR_REPETITION_TEMPO", "REST_SCOPE_AND_INCLUSION_SEMANTICS",
                       "TRANSITION_TIME_POLICY", "WARMUP_COOLDOWN_INCLUSION_POLICY", "UNILATERAL_REPS_TIMING_SCOPE")
            if not structure.exercises:
                missing = ("STRENGTH_EXERCISE_STRUCTURE",) + missing
            elif any(x.reps is None for x in structure.exercises):
                missing = ("REPETITIONS_OR_EXPLICIT_HOLD_TIME",) + missing
            same = prior is not None and prior.fingerprint == structure.fingerprint
            sessions.append(StrengthSessionIntent(
                athlete_id=context.request.athlete_id, week_start=week.week_start, scheduled_date=p.date,
                content_anchor_date=anchor, occurrence=occurrence, role=p.session_type.value, phase=p.phase.value,
                structure=structure, previous_structure=prior, proposed_structure=structure, final_structure=structure,
                progression_level=_progression_level(context, p.model_copy(update={"date": anchor})),
                progression_reason="FIRST_OBSERVED_STRUCTURE" if prior is None else "UNCHANGED_BY_EXISTING_RULE" if same else "EXISTING_PHASE_LEVEL_OR_VARIANT_CHANGE",
                legacy_duration_minutes=p.target_duration_minutes, selected_duration_minutes=p.target_duration_minutes,
                legacy_duration_basis="HISTORICAL_28D_MEAN_BOUNDED_BY_DEFAULT_AND_FLOOR"
                    if history and history.activity_count and history.duration_seconds else "CONFIG_DEFAULT_WITHOUT_USABLE_HISTORY",
                fallback_reason="INSUFFICIENT_INDEPENDENT_TIMING_POLICY" if structure.exercises else "STRENGTH_STRUCTURE_UNAVAILABLE",
                content_source="EXACT_LEGACY_WORKOUT_SNAPSHOT" if structure.exercises else "WORKOUT_STRUCTURE_UNAVAILABLE",
                missing_data=missing,
                provenance=(
                    reason("EXISTING_STRENGTH_STRUCTURE", "workout_builder._strength_steps", phase=p.phase.value,
                           content_anchor_date=str(anchor), variant=structure.variant_index),
                    reason("ORDINAL_IS_NOT_A_NEW_A_B_WORKOUT_ROLE", "strength_intent.build_strength_shadow", occurrence=occurrence),
                    reason("LEGACY_STRENGTH_DURATION_INPUT", "session_planning._duration", window_days=28,
                           activity_count=history.activity_count if history else None, duration_seconds=history.duration_seconds if history else None,
                           historical_mean_rounded=round(history.duration_seconds / 60 / history.activity_count)
                               if history and history.activity_count and history.duration_seconds else None,
                           default_minutes=session_config.default_strength_minutes, floor_minutes=session_config.minimum_session_minutes,
                           selected_minutes=p.target_duration_minutes),
                    reason("ALLOCATED_NODE_TIMES_ARE_NOT_AN_INDEPENDENT_ESTIMATE", "workout_builder._strength_steps"),
                    reason("SCHEMA_BOUNDS_NOT_PROGRESSION_RULES", "models.WorkoutNode",
                           sets_min=1, sets_max=10, reps_min=1, reps_max=100, rest_min=0, rest_max=600),
                )))
        previous = {s.occurrence: s.structure for s in sessions}
        result = structural.get(week.week_start)
        placed_minutes = sum(s.legacy_duration_minutes or 0 for s in sessions)
        weeks.append(StrengthWeekShadow(week_start=week.week_start, phase=budget.dominant_phase.value,
            sessions=tuple(sessions), strength_minutes_target=sum(s.target_duration_minutes or 0 for s in result.intent.session_intents
                if s.sport == "strength") if result else placed_minutes,
            placed_strength_minutes=placed_minutes,
            unplaced_strength_sessions=sum(s.session.sport == "strength" for s in result.unplaced) if result else 0,
            strength_target_source="WEEKLY_PLANNING_INTENT_LEGACY_COMPONENT" if result else "NULL_LEGACY_PLACED_OBSERVATION",
            same_structure_within_week=len({s.structure.fingerprint for s in sessions}) == 1
                if len(sessions) >= 2 and all(s.structure.exercises for s in sessions) else None))
    return StructuredStrengthShadowReport(athlete_id=context.request.athlete_id, context_fingerprint=context.fingerprint,
                                          artifact_fingerprint=artifact.fingerprint, weeks=tuple(weeks))
