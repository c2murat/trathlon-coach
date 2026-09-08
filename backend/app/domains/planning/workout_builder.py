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
from app.domains.planning.workout_labels import STRENGTH_VARIANTS, SWIM_DRILLS, WORKOUT_ROLE_LABELS
from app.domains.planning.adaptive_targets import adapt_target
from app.domains.planning.planning_adaptation import apply_planning_adaptation


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
    TARGET_ADAPTED_FROM_CAPABILITY = "TARGET_ADAPTED_FROM_CAPABILITY"
    TARGET_ADAPTED_FROM_EXECUTION_PROPOSAL = "TARGET_ADAPTED_FROM_EXECUTION_PROPOSAL"


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
    run_pace_easy: tuple[Decimal, Decimal] = (Decimal("1.15"), Decimal("1.30"))
    run_pace_aerobic: tuple[Decimal, Decimal] = (Decimal("1.12"), Decimal("1.25"))
    run_pace_warmup: tuple[Decimal, Decimal] = (Decimal("1.20"), Decimal("1.35"))
    run_pace_recovery: tuple[Decimal, Decimal] = (Decimal("1.30"), Decimal("1.40"))
    run_pace_cooldown: tuple[Decimal, Decimal] = (Decimal("1.22"), Decimal("1.40"))
    run_pace_tempo: tuple[Decimal, Decimal] = (Decimal("1.03"), Decimal("1.08"))
    run_pace_threshold: tuple[Decimal, Decimal] = (Decimal("0.97"), Decimal("1.03"))
    run_pace_interval: tuple[Decimal, Decimal] = (Decimal("0.90"), Decimal("0.96"))
    bike_power_easy: tuple[Decimal, Decimal] = (Decimal("0.50"), Decimal("0.65"))
    bike_power_warmup: tuple[Decimal, Decimal] = (Decimal("0.45"), Decimal("0.60"))
    bike_power_recovery: tuple[Decimal, Decimal] = (Decimal("0.45"), Decimal("0.55"))
    bike_power_cooldown: tuple[Decimal, Decimal] = (Decimal("0.45"), Decimal("0.55"))
    bike_power_endurance: tuple[Decimal, Decimal] = (Decimal("0.60"), Decimal("0.72"))
    bike_power_aerobic: tuple[Decimal, Decimal] = (Decimal("0.60"), Decimal("0.70"))
    bike_power_tempo: tuple[Decimal, Decimal] = (Decimal("0.76"), Decimal("0.88"))
    bike_power_sweet_spot: tuple[Decimal, Decimal] = (Decimal("0.88"), Decimal("0.94"))
    bike_power_threshold: tuple[Decimal, Decimal] = (Decimal("0.95"), Decimal("1.05"))
    bike_power_interval: tuple[Decimal, Decimal] = (Decimal("1.05"), Decimal("1.20"))
    swim_css_easy: tuple[Decimal, Decimal] = (Decimal("1.10"), Decimal("1.25"))
    swim_css_warmup: tuple[Decimal, Decimal] = (Decimal("1.18"), Decimal("1.30"))
    swim_css_drill: tuple[Decimal, Decimal] = (Decimal("1.20"), Decimal("1.35"))
    swim_css_recovery: tuple[Decimal, Decimal] = (Decimal("1.25"), Decimal("1.40"))
    swim_css_cooldown: tuple[Decimal, Decimal] = (Decimal("1.22"), Decimal("1.35"))
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
            "run_pace_easy", "run_pace_aerobic", "run_pace_warmup", "run_pace_recovery", "run_pace_cooldown", "run_pace_tempo", "run_pace_threshold", "run_pace_interval",
            "bike_power_easy", "bike_power_warmup", "bike_power_recovery", "bike_power_cooldown", "bike_power_endurance", "bike_power_aerobic", "bike_power_tempo",
            "bike_power_sweet_spot", "bike_power_threshold", "bike_power_interval", "swim_css_easy", "swim_css_warmup", "swim_css_drill", "swim_css_recovery", "swim_css_cooldown",
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


def _family(session_type: SessionType) -> Literal["recovery", "easy", "aerobic", "tempo", "threshold", "interval", "strength"]:
    name = session_type.value
    if session_type is SessionType.GENERAL_STRENGTH:
        return "strength"
    if name.endswith("RECOVERY"):
        return "recovery"
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


def _target(context: PlanningContext, session: SessionPrescription, config: WorkoutBuilderConfig, family_override=None):
    family = family_override or _family(session.session_type)
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
    rpe_family = (
        "strength" if family == "strength" else
        "easy" if family == "recovery" else
        "aerobic" if family == "endurance" else
        "tempo" if family == "sweet_spot" else family
    )
    bounds = getattr(config, f"rpe_{rpe_family}")
    target = WorkoutTarget(metric="rpe", mode="absolute_range", minimum=_target_float(bounds[0], config), maximum=_target_float(bounds[1], config))
    provenance = WorkoutTargetProvenance(metric="rpe", source_kind="RPE_CONFIG", derivation_rule=f"rpe_{bounds[0]}_{bounds[1]}", config_version=config.version)
    warnings = () if family == "strength" else (
        WorkoutWarning(code=WorkoutWarningCode.PERFORMANCE_REFERENCE_UNAVAILABLE, context={"discipline": session.discipline}),
        WorkoutWarning(code=WorkoutWarningCode.WORKOUT_TARGET_FALLBACK_TO_RPE, context={"discipline": session.discipline}),
    )
    decision = WorkoutDecisionCode.TARGET_FROM_RPE_CONFIG if family == "strength" else WorkoutDecisionCode.TARGET_FROM_RPE_FALLBACK
    return target, provenance, decision, warnings


def _step(phase: str, seconds: int, target: WorkoutTarget, instructions: str | None = None, title: str | None = None) -> WorkoutNode:
    return WorkoutNode(kind="step", phase=phase, title=title or WORKOUT_ROLE_LABELS[phase], duration=WorkoutDuration(mode="time", seconds=seconds), target=target, instructions=instructions)


def _distance_step(phase, meters, estimated_seconds, target, instructions=None, title=None):
    return WorkoutNode(kind="step", phase=phase, title=title or WORKOUT_ROLE_LABELS[phase], duration=WorkoutDuration(
        mode="distance", meters=meters, estimated_seconds=estimated_seconds,
    ), target=target, instructions=instructions)


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


def _progression_level(context: PlanningContext, session: SessionPrescription) -> int:
    # Relative planning age makes progression stable without tying it only to the
    # calendar week number. Recovery/taper deliberately collapse the progression.
    if session.phase.value in {"RECOVERY", "TAPER"}:
        return 0
    weeks = max(0, (session.date - context.request.planning_date).days // 7)
    return weeks % 3


def _target_for(context, session, config, family):
    return _target(context, session, config, family_override=family)[0]


def _target_for_step(context, session, config, role, family, *, effort_seconds=None, effort_meters=None, repeat_count=1):
    """Resolve a provider-neutral executable target from sport + type + role."""
    base = _target_for(context, session, config, family)
    prefix = {"running": "run_pace", "cycling": "bike_power", "swimming": "swim_css"}.get(session.discipline)
    role_family = role if role in {"warmup", "recovery", "cooldown", "drill"} else family
    if prefix is None or not hasattr(config, f"{prefix}_{role_family}"):
        return base
    bounds = getattr(config, f"{prefix}_{role_family}")
    if base.mode == "percent_reference" and base.reference:
        if base.reference_value and base.reference_unit:
            resolved = _resolved_target(base.metric, base.reference, bounds, base.reference_value, base.reference_unit, config)
            resolved = adapt_target(
                target=resolved, snapshot=context.adaptive_capability, session=session, family=family,
                effort_seconds=effort_seconds, effort_meters=effort_meters, repeat_count=repeat_count,
            ) if role == "work" else resolved
            if role == "work":
                target_kind = {"running": "RUN_PACE", "cycling": "POWER", "swimming": "SWIM_PACE"}[session.discipline]
                resolved, _ = apply_planning_adaptation(
                    target=resolved, context=context, sport=session.discipline,
                    session_type=session.session_type.value, target_kind=target_kind,
                )
            return resolved
        return WorkoutTarget(
            metric=base.metric, mode="percent_reference", reference=base.reference,
            minimum=_target_float(bounds[0], config), maximum=_target_float(bounds[1], config),
        )
    if base.metric == "rpe":
        rpe_family = "easy" if role_family in {"warmup", "recovery", "cooldown", "drill"} else family
        rpe_bounds = getattr(config, f"rpe_{rpe_family}", config.rpe_easy)
        return WorkoutTarget(metric="rpe", mode="absolute_range", minimum=_target_float(rpe_bounds[0], config), maximum=_target_float(rpe_bounds[1], config))
    return base


def _time_endurance_steps(context, session, config, total, progression):
    warmup_target = _target_for_step(context, session, config, "warmup", "easy")
    cooldown_target = _target_for_step(context, session, config, "cooldown", "easy")
    recovery_target = _target_for_step(context, session, config, "recovery", "easy")
    work_family = "endurance" if session.session_type in {SessionType.BIKE_ENDURANCE, SessionType.BIKE_LONG} else "aerobic" if session.session_type is SessionType.RUN_LONG else "recovery" if session.session_type.name.endswith("RECOVERY") else "easy"
    aerobic = _target_for_step(context, session, config, "work", work_family)
    warmup = min(900, max(300, total // 8)); cooldown = min(600, max(300, total // 12))
    middle = total - warmup - cooldown
    if session.phase.value == "TAPER" and session.discipline in {"running", "cycling"}:
        if session.discipline == "cycling":
            repeats, work, recovery, activation_family = 3, 60, 180, "threshold"
        else:
            repeats, work, recovery, activation_family = 4, 20, 100, "interval"
        activation_total = repeats * (work + recovery)
        steady = middle - activation_total
        if steady > 0:
            return (
                _step("warmup", warmup, warmup_target),
                _step("work", steady, aerobic, title="Trabajo aeróbico suave"),
                WorkoutNode(kind="repeat", repetitions=repeats, steps=[
                    _step("work", work, _target_for_step(context, session, config, "work", activation_family), title="Activación corta"),
                    _step("recovery", recovery, recovery_target, title="Recuperación completa"),
                ]),
                _step("cooldown", cooldown, cooldown_target),
            )
    quality_family = (
        "sweet_spot" if session.discipline == "cycling" else "tempo"
    ) if session.phase.value in {"BUILD", "SPECIFIC"} else None
    quality = quality_family and session.session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG} and total >= 4500
    if not quality:
        return (_step("warmup", warmup, warmup_target), _step("work", middle, aerobic), _step("cooldown", cooldown, cooldown_target))
    work = (600, 720, 900)[progression]
    recovery = 300; repeats = 2 if progression < 2 else 3
    required = repeats * (work + recovery)
    if required > middle * 45 // 100:
        repeats = 2; work = max(300, middle // 8)
    endurance = middle - repeats * (work + recovery)
    blocks = [_step("warmup", warmup, warmup_target)]
    if endurance > 0: blocks.append(_step("work", endurance, aerobic, "Resistencia aeróbica"))
    blocks.append(WorkoutNode(kind="repeat", repetitions=repeats, steps=[
        _step("work", work, _target_for_step(context, session, config, "work", quality_family), title="Sweet spot" if quality_family == "sweet_spot" else "Bloque tempo"),
        _step("recovery", recovery, recovery_target, "Recuperación activa"),
    ]))
    blocks.append(_step("cooldown", cooldown, cooldown_target))
    return tuple(blocks)


def _quality_catalog_steps(context, session, config, total, progression):
    family = _family(session.session_type)
    patterns = {
        "tempo": ((2, 600, 180), (3, 480, 150), (2, 900, 240)),
        "threshold": ((4, 300, 120), (3, 480, 150), (2, 600, 180)),
        "interval": ((8, 120, 60), (6, 180, 75), (5, 240, 90)),
    }
    if session.discipline == "cycling":
        patterns = {
            **patterns,
            "threshold": ((4, 300, 180), (3, 480, 240), (2, 900, 300)),
            "interval": ((5, 180, 180), (6, 180, 180), (5, 240, 240)),
        }
    repeats, work, recovery = patterns[family][progression]
    warmup = min(900, max(300, total // 5)); cooldown = min(600, max(300, total // 8))
    while repeats > 2 and warmup + cooldown + repeats * (work + recovery) > total:
        repeats -= 1
    cycle = repeats * (work + recovery)
    if warmup + cooldown + cycle > total:
        return _quality_steps(total, _target_for(context, session, config, family), session, config)[0]
    cooldown += total - warmup - cooldown - cycle
    warmup_target = _target_for_step(context, session, config, "warmup", "easy")
    recovery_target = _target_for_step(context, session, config, "recovery", "easy")
    cooldown_target = _target_for_step(context, session, config, "cooldown", "easy")
    label = "Fartlek rápido" if session.session_type is SessionType.RUN_INTERVAL else "Trabajo de calidad"
    return (
        _step("warmup", warmup, warmup_target),
        WorkoutNode(kind="repeat", repetitions=repeats, steps=[
            _step("work", work, _target_for_step(context, session, config, "work", family, effort_seconds=work, repeat_count=repeats), label),
            _step("recovery", recovery, recovery_target, "Recuperación activa"),
        ]),
        _step("cooldown", cooldown, cooldown_target),
    )


def _swim_steps(context, session, config, total, progression):
    family = _family(session.session_type)
    css = context.performance.swimming_css_seconds_per_100m
    pace = Decimal(str(css)) if _positive(css) else Decimal("125")
    main_target = _target_for_step(context, session, config, "work", family)
    warmup_target = _target_for_step(context, session, config, "warmup", "easy")
    drill_target = _target_for_step(context, session, config, "drill", "easy")
    recovery_target = _target_for_step(context, session, config, "recovery", "easy")
    cooldown_target = _target_for_step(context, session, config, "cooldown", "easy")
    easy = _target_for_step(context, session, config, "work", "easy")
    warm_m = (200, 300, 400)[progression] if total >= 2400 else 200
    cool_m = 200
    warm_s = int(Decimal(warm_m) * pace * Decimal("1.20") / 100)
    cool_s = int(Decimal(cool_m) * pace * Decimal("1.20") / 100)
    remaining = max(300, total - warm_s - cool_s)
    if session.session_type is SessionType.SWIM_TECHNIQUE:
        reps, meters, recovery = (4 + progression, 50, 20)
        work_s = max(20, int(Decimal(meters) * pace * Decimal("1.20") / 100))
        repeat_total = reps * (work_s + recovery)
        residual = max(1, remaining - repeat_total)
        drill_title, drill_note = SWIM_DRILLS[progression]
        return (
            _distance_step("warmup", warm_m, warm_s, warmup_target),
            WorkoutNode(kind="repeat", repetitions=reps, steps=[
                _distance_step("drill", meters, work_s, drill_target, drill_note, drill_title),
                _step("recovery", recovery, recovery_target),
            ]),
            _step("work", residual, easy, "Nado aeróbico relajado"),
            _distance_step("cooldown", cool_m, cool_s, cooldown_target),
        )
    if session.session_type is SessionType.SWIM_AEROBIC and session.phase.value == "SPECIFIC":
        threshold_target = _target_for_step(context, session, config, "work", "threshold", effort_meters=100, repeat_count=4)
        meters = 100
        work_s = max(20, int(Decimal(meters) * pace * Decimal(str(threshold_target.minimum or 1)) / 100))
        recovery = 30
        repeats = max(2, min(4, remaining // (work_s + recovery)))
        residual = remaining - repeats * (work_s + recovery)
        return (
            _distance_step("warmup", warm_m, warm_s, warmup_target),
            WorkoutNode(kind="repeat", repetitions=repeats, steps=[
                _distance_step("work", meters, work_s, threshold_target, "Mantén un ritmo controlado próximo al CSS.", "Series a ritmo CSS"),
                _step("recovery", recovery, recovery_target),
            ]),
            _step("work", residual, main_target, "Nado aeróbico estable"),
            _distance_step("cooldown", cool_m, cool_s, cooldown_target),
        )
    meters = {"easy": 200, "aerobic": (200, 300, 400)[progression], "threshold": (100, 200, 300)[progression], "interval": (50, 100, 200)[progression]}.get(family, 200)
    recovery = 20 if family in {"easy", "aerobic"} else 30
    multiplier = Decimal(str(main_target.minimum or 1)) if main_target.mode == "percent_reference" else Decimal("1.15")
    work_s = max(20, int(Decimal(meters) * pace * multiplier / 100))
    reps = max(2, min(10, remaining // (work_s + recovery)))
    residual = remaining - reps * (work_s + recovery)
    if residual < 1:
        reps = max(2, reps - 1); residual = remaining - reps * (work_s + recovery)
    main_target = _target_for_step(context, session, config, "work", family, effort_meters=meters, repeat_count=reps)
    return (
        _distance_step("warmup", warm_m, warm_s, warmup_target),
        WorkoutNode(kind="repeat", repetitions=reps, steps=[
            _distance_step("work", meters, work_s, main_target, "Serie principal"),
            _step("recovery", recovery, recovery_target),
        ]),
        _step("work", residual, easy, "Nado aeróbico de ajuste"),
        _distance_step("cooldown", cool_m, cool_s, cooldown_target),
    )


def _strength_steps(context, session, config, total, progression):
    variant = ((session.date - context.request.planning_date).days // 7) % 2
    phase_profiles = {
        "RECOVERY": (2, 10, 4, (Decimal("4"), Decimal("6")), 60),
        "TAPER": (2, 6, 3, (Decimal("4"), Decimal("6")), 60),
        "SPECIFIC": (3, 8, 5, config.rpe_strength, 90),
    }
    sets, reps, exercise_count, rpe_bounds, rest = phase_profiles.get(
        session.phase.value, (3, 10 if progression == 0 else 8, 6, config.rpe_strength, 90)
    )
    exercises = STRENGTH_VARIANTS[variant][:exercise_count]
    target = WorkoutTarget(
        metric="rpe", mode="absolute_range",
        minimum=_target_float(rpe_bounds[0], config), maximum=_target_float(rpe_bounds[1], config),
    )
    base, residual = divmod(total, len(exercises))
    result = []
    for index, (title, pattern, unilateral) in enumerate(exercises):
        seconds = base + (1 if index < residual else 0)
        result.append(WorkoutNode(
            kind="step", phase="strength", duration=WorkoutDuration(mode="time", seconds=seconds),
            target=target, title=title, movement_pattern=pattern, sets=sets, reps=reps,
            rest_seconds=rest, unilateral=unilateral,
            instructions="Mantén una técnica limpia y deja las repeticiones indicadas en reserva.",
        ))
    return tuple(result)


def workout_duration_seconds(definition: StructuredWorkoutDefinition) -> int | None:
    def node_seconds(node: WorkoutNode) -> int | None:
        if node.kind == "step":
            if not node.duration: return None
            return node.duration.seconds if node.duration.mode == "time" else node.duration.estimated_seconds if node.duration.mode == "distance" else None
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
    def visit(nodes):
        for node in nodes:
            if node.kind == "repeat":
                if not node.steps or node.repetitions is None:
                    issues.append(StructuredWorkoutValidationIssue(code="INVALID_REPEAT_STEP"))
                yield from visit(node.steps or ())
            else:
                if node.duration is None or node.target is None or node.phase is None or not (node.title or "").strip():
                    issues.append(StructuredWorkoutValidationIssue(code="NON_PORTABLE_WORKOUT_STEP"))
                yield node
    leaves = list(visit(draft.definition.steps))
    def quality_target(node):
        if not node.target or node.target.mode != "percent_reference": return False
        minimum = node.target.minimum or 0
        return (node.target.metric == "power" and minimum >= .76) or (node.target.metric in {"pace", "swim_pace"} and minimum <= 1.03)
    quality = sum((node.duration.seconds or node.duration.estimated_seconds or 0) for node in leaves if node.phase == "work" and quality_target(node))
    if session.intensity.value == "EASY" and actual and quality > actual // 2:
        issues.append(StructuredWorkoutValidationIssue(code="EASY_WORKOUT_QUALITY_DENSITY_EXCEEDED"))
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
    progression = _progression_level(context, session)
    if session.discipline == "swimming":
        steps = _swim_steps(context, session, config, total, progression)
        template_warnings = (); template_decisions = (WorkoutDecision(code=WorkoutDecisionCode.QUALITY_TEMPLATE if family in {"threshold", "interval"} else WorkoutDecisionCode.CONTINUOUS_TEMPLATE, context={"progression_level": progression}),)
    elif session.discipline == "strength":
        steps = _strength_steps(context, session, config, total, progression)
        template_warnings = (); template_decisions = (WorkoutDecision(code=WorkoutDecisionCode.CONTINUOUS_TEMPLATE, context={"progression_level": progression}),)
    elif family in {"tempo", "threshold", "interval"}:
        steps = _quality_catalog_steps(context, session, config, total, progression)
        template_warnings = (); template_decisions = (WorkoutDecision(code=WorkoutDecisionCode.QUALITY_TEMPLATE, context={"progression_level": progression}),)
    else:
        steps = _time_endurance_steps(context, session, config, total, progression)
        template_warnings = ()
        template_decisions = (WorkoutDecision(code=WorkoutDecisionCode.CONTINUOUS_TEMPLATE, context={"progression_level": progression}),)
    definition = StructuredWorkoutDefinition(
        schema_version=1, sport=session.discipline,
        title=session.session_type.value, purpose=session.purpose.value,
        steps=list(steps),
    )
    def adapted_targets(nodes):
        for node in nodes:
            if node.kind == "repeat":
                yield from adapted_targets(node.steps or ())
            elif node.target and node.target.adaptation:
                yield node.target.adaptation
    adaptations = tuple(adapted_targets(definition.steps))
    adaptive_decisions = tuple(WorkoutDecision(
        code=WorkoutDecisionCode.TARGET_ADAPTED_FROM_CAPABILITY,
        context={"algorithm_version": item.algorithm_version, "capability_dimension": item.capability_dimension, "confidence": item.confidence},
    ) for item in adaptations[:1])
    def proposal_adaptations(nodes):
        for node in nodes:
            if node.kind == "repeat":
                yield from proposal_adaptations(node.steps or ())
            elif node.target and node.target.planning_adaptation:
                yield node.target.planning_adaptation
    proposal_rows = tuple(proposal_adaptations(definition.steps))
    proposal_decisions = tuple(WorkoutDecision(
        code=WorkoutDecisionCode.TARGET_ADAPTED_FROM_EXECUTION_PROPOSAL,
        context={
            "proposal_version": item.proposal_version,
            "proposal_kind": item.proposal_kind,
            "direction": item.direction,
            "confidence": item.confidence,
            "before": f"{item.before_minimum:g}-{item.before_maximum:g}",
            "after": f"{item.after_minimum:g}-{item.after_maximum:g}",
        },
    ) for item in proposal_rows[:1])
    draft = StructuredWorkoutDraft(
        buildable=True, sport=session.discipline, session_type=session.session_type,
        definition=definition, target_provenance=provenance,
        warnings=tuple((*target_warnings, *template_warnings)),
        decisions=(WorkoutDecision(code=target_decision), *adaptive_decisions, *proposal_decisions, *template_decisions),
        configuration_version=config.version, algorithm_version=config.algorithm_version,
        context_fingerprint=context.fingerprint, fingerprint=fingerprint,
    )
    issues = validate_structured_workout_draft(draft, session)
    if issues:
        raise StructuredWorkoutBuilderError(issues)
    return draft
