from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from enum import Enum
from math import isfinite
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domains.planning.contracts import FrozenModel, PlanningContext, canonical_json, context_fingerprint
from app.domains.planning.models import (
    StructuredWorkoutDefinition, WorkoutDuration, WorkoutNode, WorkoutTarget,
)
from app.domains.planning.session_planning import SessionPrescription, SessionType


STRUCTURED_WORKOUT_SCHEMA_VERSION = 1


class WorkoutWarningCode(str, Enum):
    PERFORMANCE_REFERENCE_UNAVAILABLE = "PERFORMANCE_REFERENCE_UNAVAILABLE"
    WORKOUT_TARGET_FALLBACK_TO_RPE = "WORKOUT_TARGET_FALLBACK_TO_RPE"
    WORKOUT_DURATION_ADAPTED = "WORKOUT_DURATION_ADAPTED"
    WORKOUT_TEMPLATE_MINIMUM_CONSTRAINT = "WORKOUT_TEMPLATE_MINIMUM_CONSTRAINT"
    STRUCTURED_WORKOUT_NOT_APPLICABLE = "STRUCTURED_WORKOUT_NOT_APPLICABLE"


class WorkoutDecisionCode(str, Enum):
    TARGET_FROM_FTP = "TARGET_FROM_FTP"
    TARGET_FROM_THRESHOLD_PACE = "TARGET_FROM_THRESHOLD_PACE"
    TARGET_FROM_CSS = "TARGET_FROM_CSS"
    TARGET_FROM_THRESHOLD_HR = "TARGET_FROM_THRESHOLD_HR"
    TARGET_FROM_RPE_FALLBACK = "TARGET_FROM_RPE_FALLBACK"
    TARGET_FROM_RPE_CONFIG = "TARGET_FROM_RPE_CONFIG"
    CONTINUOUS_TEMPLATE = "CONTINUOUS_TEMPLATE"
    QUALITY_TEMPLATE = "QUALITY_TEMPLATE"
    REPEAT_COUNT_REDUCED_FOR_DURATION = "REPEAT_COUNT_REDUCED_FOR_DURATION"
    RESIDUAL_ASSIGNED_TO_COOLDOWN = "RESIDUAL_ASSIGNED_TO_COOLDOWN"
    COMPETITION_REQUIRES_NO_WORKOUT = "COMPETITION_REQUIRES_NO_WORKOUT"


class WorkoutWarning(FrozenModel):
    code: WorkoutWarningCode
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class WorkoutDecision(FrozenModel):
    code: WorkoutDecisionCode
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class WorkoutTargetProvenance(FrozenModel):
    metric: Literal["power", "heart_rate", "pace", "swim_pace", "rpe"]
    source_kind: Literal["FTP", "threshold_hr", "threshold_pace", "CSS", "RPE_CONFIG"]
    reference_value: Decimal | int | None = None
    reference_unit: str | None = None
    reference_id: UUID | None = None
    profile_version_id: UUID | None = None
    derivation_rule: str
    config_version: str


class StructuredWorkoutDraft(FrozenModel):
    buildable: bool
    schema_version: int = STRUCTURED_WORKOUT_SCHEMA_VERSION
    sport: Literal["running", "cycling", "swimming", "strength"] | None = None
    session_type: SessionType
    definition: StructuredWorkoutDefinition | None = None
    target_provenance: WorkoutTargetProvenance | None = None
    warnings: tuple[WorkoutWarning, ...] = ()
    decisions: tuple[WorkoutDecision, ...] = ()
    configuration_version: str
    algorithm_version: str
    context_fingerprint: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class WorkoutBuilderConfig(FrozenModel):
    version: str = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)
    warmup_ratio: Decimal = Field(default=Decimal("0.20"), ge=0, le=Decimal("0.40"))
    cooldown_ratio: Decimal = Field(default=Decimal("0.10"), ge=0, le=Decimal("0.30"))
    minimum_warmup_seconds: int = Field(default=300, ge=60)
    minimum_cooldown_seconds: int = Field(default=300, ge=60)
    minimum_work_seconds: int = Field(default=180, ge=30)
    recovery_seconds: int = Field(default=60, ge=15)
    threshold_repeats: int = Field(default=3, ge=2, le=12)
    interval_repeats: int = Field(default=5, ge=2, le=20)
    minimum_interval_repeats: int = Field(default=2, ge=2, le=10)
    rounding_seconds: int = Field(default=5, ge=1, le=60)
    target_precision_places: int = Field(default=3, ge=1, le=6)
    run_pace_easy: tuple[Decimal, Decimal] = (Decimal("1.15"), Decimal("1.35"))
    run_pace_tempo: tuple[Decimal, Decimal] = (Decimal("0.98"), Decimal("1.08"))
    run_pace_threshold: tuple[Decimal, Decimal] = (Decimal("0.97"), Decimal("1.03"))
    run_pace_interval: tuple[Decimal, Decimal] = (Decimal("0.85"), Decimal("0.95"))
    bike_power_easy: tuple[Decimal, Decimal] = (Decimal("0.50"), Decimal("0.65"))
    bike_power_endurance: tuple[Decimal, Decimal] = (Decimal("0.60"), Decimal("0.75"))
    bike_power_tempo: tuple[Decimal, Decimal] = (Decimal("0.76"), Decimal("0.88"))
    bike_power_threshold: tuple[Decimal, Decimal] = (Decimal("0.92"), Decimal("1.05"))
    bike_power_interval: tuple[Decimal, Decimal] = (Decimal("1.05"), Decimal("1.20"))
    swim_css_easy: tuple[Decimal, Decimal] = (Decimal("1.10"), Decimal("1.25"))
    swim_css_aerobic: tuple[Decimal, Decimal] = (Decimal("1.05"), Decimal("1.15"))
    swim_css_threshold: tuple[Decimal, Decimal] = (Decimal("0.97"), Decimal("1.03"))
    swim_css_interval: tuple[Decimal, Decimal] = (Decimal("0.85"), Decimal("0.95"))
    heart_rate_easy: tuple[Decimal, Decimal] = (Decimal("0.70"), Decimal("0.85"))
    heart_rate_tempo: tuple[Decimal, Decimal] = (Decimal("0.85"), Decimal("0.95"))
    heart_rate_threshold: tuple[Decimal, Decimal] = (Decimal("0.95"), Decimal("1.02"))
    heart_rate_interval: tuple[Decimal, Decimal] = (Decimal("0.98"), Decimal("1.05"))
    rpe_easy: tuple[Decimal, Decimal] = (Decimal("2"), Decimal("4"))
    rpe_aerobic: tuple[Decimal, Decimal] = (Decimal("3"), Decimal("5"))
    rpe_tempo: tuple[Decimal, Decimal] = (Decimal("5"), Decimal("7"))
    rpe_threshold: tuple[Decimal, Decimal] = (Decimal("7"), Decimal("8"))
    rpe_interval: tuple[Decimal, Decimal] = (Decimal("8"), Decimal("9"))
    rpe_strength: tuple[Decimal, Decimal] = (Decimal("5"), Decimal("7"))

    @model_validator(mode="after")
    def validate_target_ranges(self):
        range_fields = (
            "run_pace_easy", "run_pace_tempo", "run_pace_threshold", "run_pace_interval",
            "bike_power_easy", "bike_power_endurance", "bike_power_tempo",
            "bike_power_threshold", "bike_power_interval", "swim_css_easy",
            "swim_css_aerobic", "swim_css_threshold", "swim_css_interval",
            "heart_rate_easy", "heart_rate_tempo", "heart_rate_threshold",
            "heart_rate_interval", "rpe_easy", "rpe_aerobic", "rpe_tempo",
            "rpe_threshold", "rpe_interval", "rpe_strength",
        )
        for name in range_fields:
            minimum, maximum = getattr(self, name)
            if not minimum.is_finite() or not maximum.is_finite() or minimum <= 0 or minimum > maximum:
                raise ValueError(f"invalid target range: {name}")
            if name.startswith("rpe_") and maximum > 10:
                raise ValueError(f"RPE range exceeds scale: {name}")
        if self.minimum_interval_repeats > self.interval_repeats:
            raise ValueError("minimum interval repeats exceed configured repeats")
        return self


class StructuredWorkoutValidationIssue(FrozenModel):
    code: str
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class StructuredWorkoutBuilderError(ValueError):
    def __init__(self, issues: tuple[StructuredWorkoutValidationIssue, ...]):
        self.issues = issues
        super().__init__(", ".join(item.code for item in issues))


def _reference_id(context: PlanningContext, sport: str, metric_types: set[str]) -> UUID | None:
    item = next((ref for ref in context.performance.references if ref.sport == sport and ref.metric_type in metric_types), None)
    return item.reference_id if item else None


def _family(session_type: SessionType) -> Literal["easy", "aerobic", "tempo", "threshold", "interval", "strength"]:
    name = session_type.value
    if session_type is SessionType.GENERAL_STRENGTH:
        return "strength"
    if name.endswith("INTERVAL"):
        return "interval"
    if name.endswith("THRESHOLD"):
        return "threshold"
    if name.endswith("TEMPO"):
        return "tempo"
    if name.endswith(("ENDURANCE", "LONG")) or name == "SWIM_AEROBIC":
        return "aerobic"
    return "easy"


def _range(config: WorkoutBuilderConfig, prefix: str, family: str) -> tuple[Decimal, Decimal]:
    mapped = "aerobic" if family == "strength" else family
    return getattr(config, f"{prefix}_{mapped}", getattr(config, f"{prefix}_easy"))


def _positive(value) -> bool:
    if value is None:
        return False
    decimal = Decimal(str(value))
    return decimal.is_finite() and decimal > 0


def _target_float(value: Decimal, config: WorkoutBuilderConfig) -> float:
    quantum = Decimal(1).scaleb(-config.target_precision_places)
    normalized = value.quantize(quantum, rounding=ROUND_HALF_UP)
    result = float(normalized)
    if not normalized.is_finite() or normalized <= 0 or not isfinite(result):
        raise ValueError("workout target must be finite and positive")
    return result


def _resolved_target(metric, reference, bounds, reference_value, unit, config):
    reference_decimal = Decimal(str(reference_value))
    resolved = tuple(
        reference_decimal * bound for bound in bounds
    )
    # Athlete-facing power and pace values are snapshotted at their executable
    # precision: whole watts or whole seconds per distance, using HALF_UP in both
    # backend and serialized artifacts.
    rounded = tuple(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP) for value in resolved)
    return WorkoutTarget(
        metric=metric, mode="percent_reference", reference=reference,
        minimum=_target_float(bounds[0], config), maximum=_target_float(bounds[1], config),
        reference_value=float(reference_decimal), reference_unit=unit,
        resolved_minimum=float(rounded[0]), resolved_maximum=float(rounded[1]), resolved_unit=unit,
    )


def _target(context: PlanningContext, session: SessionPrescription, config: WorkoutBuilderConfig):
    family = _family(session.session_type)
    performance = context.performance
    decision: WorkoutDecisionCode
    provenance: WorkoutTargetProvenance
    if session.discipline == "running" and _positive(performance.running_threshold_pace_seconds_per_km):
        bounds = _range(config, "run_pace", family)
        target = _resolved_target("pace", "threshold_pace", bounds, performance.running_threshold_pace_seconds_per_km, "seconds_per_km", config)
        decision = WorkoutDecisionCode.TARGET_FROM_THRESHOLD_PACE
        provenance = WorkoutTargetProvenance(metric="pace", source_kind="threshold_pace", reference_value=performance.running_threshold_pace_seconds_per_km, reference_unit="seconds_per_km", reference_id=_reference_id(context, "running", {"threshold_pace", "pace"}), profile_version_id=performance.profile_version_id, derivation_rule=f"threshold_pace_x_{bounds[0]}_{bounds[1]}", config_version=config.version)
        return target, provenance, decision, ()
    if session.discipline == "cycling" and _positive(performance.cycling_ftp_watts):
        bounds = _range(config, "bike_power", family)
        target = _resolved_target("power", "FTP", bounds, performance.cycling_ftp_watts, "watts", config)
        decision = WorkoutDecisionCode.TARGET_FROM_FTP
        provenance = WorkoutTargetProvenance(metric="power", source_kind="FTP", reference_value=performance.cycling_ftp_watts, reference_unit="watts", reference_id=_reference_id(context, "cycling", {"ftp", "FTP"}), profile_version_id=performance.profile_version_id, derivation_rule=f"ftp_x_{bounds[0]}_{bounds[1]}", config_version=config.version)
        return target, provenance, decision, ()
    if session.discipline == "swimming" and _positive(performance.swimming_css_seconds_per_100m):
        bounds = _range(config, "swim_css", family)
        target = _resolved_target("swim_pace", "CSS", bounds, performance.swimming_css_seconds_per_100m, "seconds_per_100m", config)
        decision = WorkoutDecisionCode.TARGET_FROM_CSS
        provenance = WorkoutTargetProvenance(metric="swim_pace", source_kind="CSS", reference_value=performance.swimming_css_seconds_per_100m, reference_unit="seconds_per_100m", reference_id=_reference_id(context, "swimming", {"css", "CSS"}), profile_version_id=performance.profile_version_id, derivation_rule=f"css_x_{bounds[0]}_{bounds[1]}", config_version=config.version)
        return target, provenance, decision, ()
    threshold_hr = performance.running_threshold_heart_rate_bpm if session.discipline == "running" else performance.cycling_threshold_heart_rate_bpm if session.discipline == "cycling" else None
    if _positive(threshold_hr):
        bounds = _range(config, "heart_rate", family)
        target = WorkoutTarget(metric="heart_rate", mode="percent_reference", reference="threshold_hr", minimum=_target_float(bounds[0], config), maximum=_target_float(bounds[1], config))
        decision = WorkoutDecisionCode.TARGET_FROM_THRESHOLD_HR
        provenance = WorkoutTargetProvenance(metric="heart_rate", source_kind="threshold_hr", reference_value=threshold_hr, reference_unit="bpm", reference_id=_reference_id(context, session.discipline, {"threshold_hr"}), profile_version_id=performance.profile_version_id, derivation_rule=f"threshold_hr_x_{bounds[0]}_{bounds[1]}", config_version=config.version)
        return target, provenance, decision, ()
    rpe_family = "strength" if family == "strength" else family
    bounds = getattr(config, f"rpe_{rpe_family}")
    target = WorkoutTarget(metric="rpe", mode="absolute_range", minimum=_target_float(bounds[0], config), maximum=_target_float(bounds[1], config))
    provenance = WorkoutTargetProvenance(metric="rpe", source_kind="RPE_CONFIG", derivation_rule=f"rpe_{bounds[0]}_{bounds[1]}", config_version=config.version)
    warnings = () if family == "strength" else (
        WorkoutWarning(code=WorkoutWarningCode.PERFORMANCE_REFERENCE_UNAVAILABLE, context={"discipline": session.discipline}),
        WorkoutWarning(code=WorkoutWarningCode.WORKOUT_TARGET_FALLBACK_TO_RPE, context={"discipline": session.discipline}),
    )
    decision = WorkoutDecisionCode.TARGET_FROM_RPE_CONFIG if family == "strength" else WorkoutDecisionCode.TARGET_FROM_RPE_FALLBACK
    return target, provenance, decision, warnings


def _step(phase: str, seconds: int, target: WorkoutTarget, instructions: str | None = None) -> WorkoutNode:
    return WorkoutNode(kind="step", phase=phase, duration=WorkoutDuration(mode="time", seconds=seconds), target=target, instructions=instructions)


def _none_target() -> WorkoutTarget:
    return WorkoutTarget(metric="none", mode="none")


def _rounded(value: Decimal, quantum: int) -> int:
    units = (value / Decimal(quantum)).to_integral_value(rounding=ROUND_FLOOR)
    return max(quantum, int(units) * quantum)


def _quality_steps(total: int, target: WorkoutTarget, session: SessionPrescription, config: WorkoutBuilderConfig):
    family = _family(session.session_type)
    warmup = max(config.minimum_warmup_seconds, _rounded(Decimal(total) * config.warmup_ratio, config.rounding_seconds))
    cooldown = max(config.minimum_cooldown_seconds, _rounded(Decimal(total) * config.cooldown_ratio, config.rounding_seconds))
    decisions = [WorkoutDecision(code=WorkoutDecisionCode.QUALITY_TEMPLATE)]
    warnings = []
    desired = config.interval_repeats if family == "interval" else config.threshold_repeats
    minimum_repeats = config.minimum_interval_repeats if family == "interval" else 2
    maximum = (total - warmup - cooldown) // (config.minimum_work_seconds + config.recovery_seconds)
    repeats = min(desired, maximum)
    if repeats < minimum_repeats:
        warmup = min(config.minimum_warmup_seconds, max(60, total // 4))
        cooldown = min(config.minimum_cooldown_seconds, max(60, total // 4))
        work = total - warmup - cooldown
        if work <= 0:
            return (_step("work", total, target),), (
                WorkoutWarning(code=WorkoutWarningCode.WORKOUT_TEMPLATE_MINIMUM_CONSTRAINT),
            ), (
                WorkoutDecision(code=WorkoutDecisionCode.CONTINUOUS_TEMPLATE, context={"reason": "SHORT_QUALITY_SESSION"}),
            )
        warnings.append(WorkoutWarning(code=WorkoutWarningCode.WORKOUT_TEMPLATE_MINIMUM_CONSTRAINT))
        decisions.append(WorkoutDecision(code=WorkoutDecisionCode.REPEAT_COUNT_REDUCED_FOR_DURATION, context={"repetitions": 1}))
        return (
            _step("warmup", warmup, _none_target()),
            _step("work", work, target),
            _step("cooldown", cooldown, _none_target()),
        ), tuple(warnings), tuple(decisions)
    if repeats < desired:
        warnings.append(WorkoutWarning(code=WorkoutWarningCode.WORKOUT_DURATION_ADAPTED))
        decisions.append(WorkoutDecision(code=WorkoutDecisionCode.REPEAT_COUNT_REDUCED_FOR_DURATION, context={"repetitions": repeats}))
    cycle_budget = total - warmup - cooldown
    work = cycle_budget // repeats - config.recovery_seconds
    residual = cycle_budget - repeats * (work + config.recovery_seconds)
    cooldown += residual
    if residual:
        decisions.append(WorkoutDecision(code=WorkoutDecisionCode.RESIDUAL_ASSIGNED_TO_COOLDOWN, context={"seconds": residual}))
    repeat = WorkoutNode(kind="repeat", repetitions=repeats, steps=[
        _step("work", work, target),
        _step("recovery", config.recovery_seconds, _none_target()),
    ])
    return (
        _step("warmup", warmup, _none_target()), repeat,
        _step("cooldown", cooldown, _none_target()),
    ), tuple(warnings), tuple(decisions)


def workout_duration_seconds(definition: StructuredWorkoutDefinition) -> int | None:
    def node_seconds(node: WorkoutNode) -> int | None:
        if node.kind == "step":
            return node.duration.seconds if node.duration and node.duration.mode == "time" else None
        values = [node_seconds(item) for item in node.steps or ()]
        return node.repetitions * sum(values) if all(value is not None for value in values) else None
    values = [node_seconds(item) for item in definition.steps]
    return sum(values) if all(value is not None for value in values) else None


def structured_workout_payload(definition: StructuredWorkoutDefinition) -> dict:
    payload = definition.model_dump(mode="json", exclude_none=True)
    return StructuredWorkoutDefinition.model_validate(payload).model_dump(mode="json", exclude_none=True)


def structured_workout_canonical_json(definition: StructuredWorkoutDefinition) -> str:
    return canonical_json(structured_workout_payload(definition))


def validate_structured_workout_draft(draft: StructuredWorkoutDraft, session: SessionPrescription):
    issues = []
    if session.session_type is SessionType.COMPETITION:
        if draft.buildable or draft.definition is not None:
            issues.append(StructuredWorkoutValidationIssue(code="COMPETITION_WORKOUT_FORBIDDEN"))
        return tuple(issues)
    if not draft.buildable or draft.definition is None:
        issues.append(StructuredWorkoutValidationIssue(code="WORKOUT_DEFINITION_REQUIRED"))
        return tuple(issues)
    if draft.definition.sport != session.discipline:
        issues.append(StructuredWorkoutValidationIssue(code="WORKOUT_SPORT_MISMATCH"))
    expected = session.target_duration_minutes * 60 if session.target_duration_minutes is not None else None
    actual = workout_duration_seconds(draft.definition)
    if expected is None or actual != expected:
        issues.append(StructuredWorkoutValidationIssue(code="WORKOUT_DURATION_MISMATCH", context={"expected": expected, "actual": actual}))
    if not draft.definition.steps:
        issues.append(StructuredWorkoutValidationIssue(code="WORKOUT_STEPS_REQUIRED"))
    if draft.target_provenance and draft.target_provenance.source_kind != "RPE_CONFIG" and (draft.target_provenance.reference_value is None or draft.target_provenance.reference_value <= 0):
        issues.append(StructuredWorkoutValidationIssue(code="INVALID_PERFORMANCE_REFERENCE"))
    return tuple(issues)


def build_structured_workout(context: PlanningContext, session: SessionPrescription, config: WorkoutBuilderConfig) -> StructuredWorkoutDraft:
    fingerprint = context_fingerprint({
        "context_fingerprint": context.fingerprint,
        "session_prescription": session,
        "config": config,
        "structured_workout_schema_version": STRUCTURED_WORKOUT_SCHEMA_VERSION,
    })
    if session.session_type is SessionType.COMPETITION:
        return StructuredWorkoutDraft(
            buildable=False, session_type=session.session_type,
            warnings=(WorkoutWarning(code=WorkoutWarningCode.STRUCTURED_WORKOUT_NOT_APPLICABLE),),
            decisions=(WorkoutDecision(code=WorkoutDecisionCode.COMPETITION_REQUIRES_NO_WORKOUT),),
            configuration_version=config.version, algorithm_version=config.algorithm_version,
            context_fingerprint=context.fingerprint, fingerprint=fingerprint,
        )
    if session.target_duration_minutes is None:
        raise StructuredWorkoutBuilderError((StructuredWorkoutValidationIssue(code="TARGET_DURATION_REQUIRED"),))
    target, provenance, target_decision, target_warnings = _target(context, session, config)
    total = session.target_duration_minutes * 60
    family = _family(session.session_type)
    if family in {"tempo", "threshold", "interval"}:
        steps, template_warnings, template_decisions = _quality_steps(total, target, session, config)
    else:
        instructions = "technique" if session.session_type is SessionType.SWIM_TECHNIQUE else "general strength" if session.session_type is SessionType.GENERAL_STRENGTH else None
        steps = (_step("work", total, target, instructions),)
        template_warnings = ()
        template_decisions = (WorkoutDecision(code=WorkoutDecisionCode.CONTINUOUS_TEMPLATE),)
    definition = StructuredWorkoutDefinition(schema_version=1, sport=session.discipline, steps=list(steps))
    draft = StructuredWorkoutDraft(
        buildable=True, sport=session.discipline, session_type=session.session_type,
        definition=definition, target_provenance=provenance,
        warnings=tuple((*target_warnings, *template_warnings)),
        decisions=(WorkoutDecision(code=target_decision), *template_decisions),
        configuration_version=config.version, algorithm_version=config.algorithm_version,
        context_fingerprint=context.fingerprint, fingerprint=fingerprint,
    )
    issues = validate_structured_workout_draft(draft, session)
    if issues:
        raise StructuredWorkoutBuilderError(issues)
    return draft
