from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from statistics import median
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domains.planning.contracts import (
    FrozenModel, PlanningContext, PlanningWarning, SportTrainingSnapshot,
    TrainingWindowSnapshot, context_fingerprint,
)
from app.domains.planning.season_structure import SeasonPhase, SeasonStructure


WEEKLY_BUDGET_SCHEMA_VERSION = 1
_CENT = Decimal("0.01")


def _decimal(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value))


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


class BudgetConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class LoadBaseline(FrozenModel):
    weekly_load: Decimal | None = Field(default=None, ge=0)
    weekly_training_minutes: Decimal | None = Field(default=None, ge=0)
    robust_load_per_minute: Decimal | None = Field(default=None, ge=0)
    load_samples: tuple[Decimal, ...] = ()
    load_per_minute_samples: tuple[Decimal, ...] = ()
    confidence: BudgetConfidence
    source_window_days: tuple[int, ...] = ()
    known_zero: bool = False
    rationale_code: str


class BudgetAdjustment(FrozenModel):
    code: Literal[
        "BASELINE", "PROGRESSION", "DELOAD", "TAPER", "RECOVERY",
        "COMPETITION", "AVAILABILITY_CAP", "STATUS_MODERATION",
        "LOW_CONFIDENCE", "PARTIAL_WEEK",
    ]
    factor: Decimal | None = Field(default=None, ge=0)
    source_goal_ids: tuple[UUID, ...] = ()
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class BudgetDecision(FrozenModel):
    code: str
    value: str | int | bool | None = None
    rationale_code: str


class DisciplineBudget(FrozenModel):
    discipline: Literal["running", "cycling", "swimming", "strength"]
    target_share: Decimal | None = Field(default=None, ge=0, le=1)
    target_load: Decimal | None = Field(default=None, ge=0)
    available_minutes: int | None = Field(default=None, ge=0)
    rationale_code: str


class PhaseExposure(FrozenModel):
    phase: SeasonPhase
    days: int = Field(ge=1, le=7)
    share: Decimal = Field(ge=0, le=1)


class WeeklyTrainingBudget(FrozenModel):
    iso_year: int
    iso_week: int
    week_start: date
    week_end: date
    available_days_in_horizon: int = Field(ge=1, le=7)
    dominant_phase: SeasonPhase
    phase_exposure: tuple[PhaseExposure, ...]
    competition_goal_ids: tuple[UUID, ...] = ()
    competition_reserved_capacity: bool = False
    total_available_minutes: int = Field(ge=0)
    available_days: int = Field(ge=0, le=7)
    unavailable_days: int = Field(ge=0, le=7)
    max_sessions: int = Field(ge=0)
    baseline_load: Decimal | None = Field(default=None, ge=0)
    target_load: Decimal | None = Field(default=None, ge=0)
    load_floor: Decimal | None = Field(default=None, ge=0)
    load_ceiling: Decimal | None = Field(default=None, ge=0)
    maximum_feasible_load: Decimal | None = Field(default=None, ge=0)
    confidence: BudgetConfidence
    disciplines: tuple[DisciplineBudget, ...]
    adjustments: tuple[BudgetAdjustment, ...]
    decisions: tuple[BudgetDecision, ...]

    @model_validator(mode="after")
    def validate_range(self):
        values = (self.load_floor, self.target_load, self.load_ceiling)
        if any(value is None for value in values) and not all(value is None for value in values):
            raise ValueError("load range must be wholly known or unknown")
        if self.target_load is not None and not (self.load_floor <= self.target_load <= self.load_ceiling):
            raise ValueError("load floor, target and ceiling are inconsistent")
        return self


class WeeklyBudgetConfig(FrozenModel):
    version: str = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)
    minimum_baseline_samples: int = Field(default=2, ge=1, le=4)
    high_confidence_samples: int = Field(default=4, ge=2, le=4)
    high_confidence_training_days: int = Field(default=12, ge=1)
    medium_confidence_training_days: int = Field(default=5, ge=1)
    minimum_load_per_minute_samples: int = Field(default=2, ge=1, le=4)
    preferred_weekly_progression: Decimal = Field(default=Decimal("0.03"), ge=0, le=Decimal("0.20"))
    maximum_weekly_increase: Decimal = Field(default=Decimal("0.05"), ge=0, le=Decimal("0.25"))
    maximum_weekly_decrease: Decimal = Field(default=Decimal("0.20"), ge=0, le=Decimal("0.50"))
    maximum_total_progression: Decimal = Field(default=Decimal("0.20"), ge=0, le=Decimal("1.00"))
    deload_every_nth_loading_week: int = Field(default=4, ge=2, le=12)
    deload_factor: Decimal = Field(default=Decimal("0.80"), gt=0, le=1)
    taper_factor_a: Decimal = Field(default=Decimal("0.70"), gt=0, le=1)
    taper_factor_b: Decimal = Field(default=Decimal("0.82"), gt=0, le=1)
    taper_factor_c: Decimal = Field(default=Decimal("1.00"), gt=0, le=1)
    recovery_factor_a: Decimal = Field(default=Decimal("0.55"), gt=0, le=1)
    recovery_factor_b: Decimal = Field(default=Decimal("0.70"), gt=0, le=1)
    recovery_factor_c: Decimal = Field(default=Decimal("0.85"), gt=0, le=1)
    competition_training_factor: Decimal = Field(default=Decimal("0.65"), gt=0, le=1)
    maintenance_factor: Decimal = Field(default=Decimal("0.92"), gt=0, le=1)
    preparation_factor: Decimal = Field(default=Decimal("0.90"), gt=0, le=1)
    floor_width_high: Decimal = Field(default=Decimal("0.08"), ge=0, lt=1)
    floor_width_medium: Decimal = Field(default=Decimal("0.15"), ge=0, lt=1)
    floor_width_low: Decimal = Field(default=Decimal("0.25"), ge=0, lt=1)
    ceiling_width_high: Decimal = Field(default=Decimal("0.08"), ge=0)
    ceiling_width_medium: Decimal = Field(default=Decimal("0.15"), ge=0)
    ceiling_width_low: Decimal = Field(default=Decimal("0.25"), ge=0)
    availability_tolerance: Decimal = Field(default=Decimal("1.15"), ge=1)
    status_form_floor: Decimal = Decimal("-10")
    status_fatigue_to_fitness_ratio: Decimal = Field(default=Decimal("1.20"), ge=1)
    status_moderation_factor: Decimal = Field(default=Decimal("0.90"), gt=0, le=1)
    goal_allocation_weight: Decimal = Field(default=Decimal("0.75"), ge=0, le=1)
    maximum_strength_share: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)


class WeeklyBudgetPlan(FrozenModel):
    schema_version: int = WEEKLY_BUDGET_SCHEMA_VERSION
    planning_start: date
    planning_end: date
    timezone_name: str
    baseline: LoadBaseline
    budgets: tuple[WeeklyTrainingBudget, ...]
    context_warnings: tuple[PlanningWarning, ...]
    season_warnings: tuple[PlanningWarning, ...]
    warnings: tuple[PlanningWarning, ...]
    decisions: tuple[BudgetDecision, ...]
    algorithm_version: str
    configuration_version: str
    context_fingerprint: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class WeeklyBudgetError(ValueError):
    pass


def _window(context: PlanningContext, days: int) -> TrainingWindowSnapshot | None:
    return next((item for item in context.training.windows if item.days == days), None)


def _band_samples(context: PlanningContext, field: str) -> tuple[tuple[Decimal, ...], tuple[int, ...]]:
    windows = {days: _window(context, days) for days in (7, 28, 42, 90)}
    bands = ((7, 0, 1), (28, 7, 3), (42, 28, 2), (90, 42, Decimal(48) / 7))
    samples = []
    sources = []
    for upper, lower, weeks in bands:
        current = windows[upper]
        previous = windows.get(lower)
        if current is None:
            continue
        value = getattr(current, field)
        previous_value = getattr(previous, field) if previous is not None else 0
        if value is None or previous_value is None:
            continue
        difference = _decimal(value) - _decimal(previous_value)
        if difference < 0:
            continue
        samples.append(_round(difference / _decimal(weeks)))
        sources.append(upper)
    return tuple(samples), tuple(sources)


def _load_per_minute_samples(context: PlanningContext) -> tuple[Decimal, ...]:
    loads, sources = _band_samples(context, "total_training_load")
    durations, duration_sources = _band_samples(context, "total_duration_seconds")
    samples = []
    for load, duration, source, duration_source in zip(loads, durations, sources, duration_sources):
        window = _window(context, source)
        if (
            source == duration_source and duration > 0 and window is not None
            and window.load_coverage == "complete" and window.load_quality in {"high", "medium"}
        ):
            samples.append(_round(load / (duration / 60)))
    return tuple(samples)


def _baseline(context: PlanningContext, config: WeeklyBudgetConfig) -> LoadBaseline:
    loads, sources = _band_samples(context, "total_training_load")
    minutes, _ = _band_samples(context, "total_duration_seconds")
    minutes = tuple(_round(item / 60) for item in minutes)
    ratios = _load_per_minute_samples(context)
    window90 = _window(context, 90)
    training_days = window90.training_days if window90 else 0
    good_coverage = bool(window90 and window90.load_coverage == "complete" and window90.load_quality in {"high", "medium"})
    if len(loads) >= config.high_confidence_samples and training_days >= config.high_confidence_training_days and good_coverage:
        confidence = BudgetConfidence.HIGH
    elif len(loads) >= config.minimum_baseline_samples and training_days >= config.medium_confidence_training_days:
        confidence = BudgetConfidence.MEDIUM
    else:
        confidence = BudgetConfidence.LOW
    usable = len(loads) >= config.minimum_baseline_samples
    weekly_load = _round(_decimal(median(loads))) if usable else None
    weekly_minutes = _round(_decimal(median(minutes))) if len(minutes) >= config.minimum_baseline_samples else None
    ratio = _round(_decimal(median(ratios))) if len(ratios) >= config.minimum_load_per_minute_samples else None
    return LoadBaseline(
        weekly_load=weekly_load,
        weekly_training_minutes=weekly_minutes,
        robust_load_per_minute=ratio,
        load_samples=loads,
        load_per_minute_samples=ratios,
        confidence=confidence,
        source_window_days=sources,
        known_zero=weekly_load == 0 if weekly_load is not None else False,
        rationale_code="ROBUST_NON_OVERLAPPING_WINDOW_BANDS" if usable else "INSUFFICIENT_LOAD_HISTORY",
    )


def _week_ranges(start: date, end: date):
    cursor = start
    while cursor <= end:
        iso = cursor.isocalendar()
        sunday = cursor + timedelta(days=6 - cursor.weekday())
        right = min(sunday, end)
        yield iso.year, iso.week, cursor, right
        cursor = right + timedelta(days=1)


def _block_for_day(season: SeasonStructure, day: date):
    return next((block for block in season.blocks if block.start_date <= day <= block.end_date), None)


def _availability(context: PlanningContext, left: date, right: date):
    slots = {item.weekday: item for item in context.preferences.availability_slots}
    total = days = sessions = 0
    count = (right - left).days + 1
    for offset in range(count):
        slot = slots.get((left + timedelta(days=offset)).weekday())
        if slot is not None and slot.available_minutes > 0 and slot.max_sessions > 0:
            total += slot.available_minutes
            days += 1
            sessions += slot.max_sessions
    sessions = min(sessions, context.preferences.max_sessions_per_week)
    return total, days, count - days, sessions


def _exposure(season: SeasonStructure, left: date, right: date):
    counts: dict[SeasonPhase, int] = {}
    count = (right - left).days + 1
    for offset in range(count):
        block = _block_for_day(season, left + timedelta(days=offset))
        if block is None:
            raise WeeklyBudgetError("week falls outside SeasonStructure")
        counts[block.phase] = counts.get(block.phase, 0) + 1
    order = {phase: index for index, phase in enumerate(SeasonPhase)}
    values = tuple(PhaseExposure(phase=phase, days=days, share=_round(_decimal(days) / count)) for phase, days in sorted(counts.items(), key=lambda item: order[item[0]]))
    dominant = max(values, key=lambda item: (item.days, -order[item.phase])).phase
    return values, dominant


def _phase_factor(exposure, left, right, season, config):
    factors = {
        SeasonPhase.PREPARATION: config.preparation_factor,
        SeasonPhase.BASE: Decimal("1"), SeasonPhase.BUILD: Decimal("1"),
        SeasonPhase.SPECIFIC: Decimal("1"), SeasonPhase.MAINTENANCE: config.maintenance_factor,
    }
    total = Decimal(0)
    goal_ids: set[UUID] = set()
    codes: set[str] = set()
    count = (right - left).days + 1
    markers = {item.goal_id: item for item in season.competition_markers}
    for offset in range(count):
        block = _block_for_day(season, left + timedelta(days=offset))
        factor = factors.get(block.phase, Decimal("1"))
        if block.phase in {SeasonPhase.TAPER, SeasonPhase.RECOVERY}:
            candidates = [markers[item] for item in block.target_goal_ids if item in markers]
            priority = min((item.priority for item in candidates), default="C", key=lambda item: {"A": 0, "B": 1, "C": 2}[item])
            prefix = "taper" if block.phase is SeasonPhase.TAPER else "recovery"
            factor = getattr(config, f"{prefix}_factor_{priority.lower()}")
            goal_ids.update(block.target_goal_ids)
            codes.add(block.phase.value)
        elif block.phase is SeasonPhase.COMPETITION:
            factor = config.competition_training_factor
            goal_ids.update(block.target_goal_ids)
            codes.add("COMPETITION")
        total += factor
    return _round(total / count), tuple(sorted(goal_ids, key=str)), codes


def _sport(window: TrainingWindowSnapshot | None, discipline: str) -> SportTrainingSnapshot | None:
    return next((item for item in window.sports if item.sport == discipline), None) if window else None


def _residual_round(values: tuple[Decimal, ...], total: Decimal) -> tuple[Decimal, ...]:
    if not values:
        return ()
    rounded = tuple(_round(value) for value in values[:-1])
    return (*rounded, _round(total - sum(rounded, Decimal(0))))


def _discipline_budgets(context, season, left, target, config):
    active = _block_for_day(season, left)
    goal_by_id = {item.competition_goal_id: item for item in context.goals}
    goals = [goal_by_id[item] for item in active.target_goal_ids if item in goal_by_id]
    if not goals:
        goals = list(context.goals)
    counts = {discipline: Decimal(0) for discipline in ("running", "cycling", "swimming")}
    mapped = {"run": "running", "bike": "cycling", "swim": "swimming"}
    for goal in goals:
        for segment in goal.segments:
            counts[mapped[segment.sport]] += 1
    if not any(counts.values()):
        for discipline in getattr(active, "disciplines", ()):
            counts[discipline] += 1
    total_goal = sum(counts.values(), Decimal(0))
    goal_shares = {key: value / total_goal if total_goal else Decimal(0) for key, value in counts.items()}
    history = _window(context, 42)
    history_loads = {key: (_sport(history, key).training_load or Decimal(0)) if _sport(history, key) else Decimal(0) for key in counts}
    history_total = sum(history_loads.values(), Decimal(0))
    history_weight = Decimal(1) - config.goal_allocation_weight if history_total else Decimal(0)
    shares = {key: goal_shares[key] * (Decimal(1) - history_weight) + (history_loads[key] / history_total if history_total else Decimal(0)) * history_weight for key in counts}
    strength = _sport(history, "strength")
    strength_share = None
    if (
        context.preferences.strength_sessions_per_week > 0 and strength
        and strength.training_load is not None and strength.training_load > 0
        and strength.loaded_activity_count > 0 and history and history.total_training_load
    ):
        strength_share = min(config.maximum_strength_share, strength.training_load / history.total_training_load)
        shares = {key: value * (Decimal(1) - strength_share) for key, value in shares.items()}
    allocations = [
        (key, value, "GOAL_SEGMENTS_WITH_HISTORY_BLEND" if history_total else "GOAL_SEGMENTS")
        for key, value in shares.items() if value > 0
    ]
    if strength_share is not None:
        allocations.append(("strength", strength_share, "HISTORICAL_STRENGTH_SHARE"))
    rounded_shares = _residual_round(tuple(item[1] for item in allocations), Decimal("1.00"))
    rounded_loads = (
        _residual_round(tuple(target * item[1] for item in allocations), target)
        if target is not None else (None,) * len(allocations)
    )
    result = [DisciplineBudget(
        discipline=discipline, target_share=share, target_load=load,
        available_minutes=None, rationale_code=rationale,
    ) for (discipline, _, rationale), share, load in zip(allocations, rounded_shares, rounded_loads)]
    if context.preferences.strength_sessions_per_week > 0:
        if strength_share is None:
            result.append(DisciplineBudget(
                discipline="strength", target_share=None, target_load=None,
                available_minutes=None, rationale_code="STRENGTH_RESERVATION_LOAD_UNKNOWN",
            ))
    return tuple(result), strength_share is None and context.preferences.strength_sessions_per_week > 0


def build_weekly_budget_plan(context: PlanningContext, season: SeasonStructure, config: WeeklyBudgetConfig) -> WeeklyBudgetPlan:
    if season.planning_start_date != context.request.start_date or season.planning_end_date < season.planning_start_date:
        raise WeeklyBudgetError("PlanningContext and SeasonStructure are incompatible")
    baseline = _baseline(context, config)
    warnings = []
    existing = {item.code for item in context.warnings} | {item.code for item in season.warnings}
    if baseline.weekly_load is None:
        warnings.append(PlanningWarning(code="WEEKLY_LOAD_BASELINE_UNAVAILABLE"))
        if "NO_TRAINING_HISTORY" not in existing:
            warnings.append(PlanningWarning(code="INSUFFICIENT_LOAD_HISTORY"))
    elif baseline.confidence is BudgetConfidence.LOW:
        warnings.append(PlanningWarning(code="INSUFFICIENT_LOAD_HISTORY"))
    window90 = _window(context, 90)
    if window90 and window90.load_coverage not in {None, "complete"} and "TRAINING_LOAD_INCOMPLETE" not in existing:
        warnings.append(PlanningWarning(code="LOW_LOAD_COVERAGE"))
    if baseline.robust_load_per_minute is None:
        warnings.append(PlanningWarning(code="AVAILABILITY_CAP_UNKNOWN"))
    if context.training_status is None and "TRAINING_STATUS_UNAVAILABLE" not in existing:
        warnings.append(PlanningWarning(code="TRAINING_STATUS_UNAVAILABLE"))

    budgets = []
    previous_loading_target = None
    loading_week = 0
    strength_warning = False
    for iso_year, iso_week, left, right in _week_ranges(season.planning_start_date, season.planning_end_date):
        exposure, dominant = _exposure(season, left, right)
        minutes, available_days, unavailable_days, max_sessions = _availability(context, left, right)
        phase_factor, source_goals, structural_codes = _phase_factor(exposure, left, right, season, config)
        competition_ids = tuple(marker.goal_id for marker in season.competition_markers if left <= marker.date <= right)
        adjustments = [BudgetAdjustment(code="BASELINE", factor=Decimal("1"))]
        target = None
        maximum = _round(_decimal(minutes) * baseline.robust_load_per_minute * config.availability_tolerance) if baseline.robust_load_per_minute is not None else None
        structural = bool(structural_codes & {"TAPER", "RECOVERY", "COMPETITION"})
        if baseline.weekly_load is not None:
            if not structural:
                loading_week += 1
            progression = min(config.maximum_total_progression, config.preferred_weekly_progression * max(0, loading_week - 1))
            target = baseline.weekly_load * (Decimal(1) + progression)
            if progression:
                adjustments.append(BudgetAdjustment(code="PROGRESSION", factor=_round(Decimal(1) + progression)))
            partial_factor = _decimal((right - left).days + 1) / 7
            if partial_factor < 1:
                target *= partial_factor
                adjustments.append(BudgetAdjustment(code="PARTIAL_WEEK", factor=_round(partial_factor)))
            if phase_factor != 1:
                target *= phase_factor
            for code in sorted(structural_codes):
                adjustments.append(BudgetAdjustment(code=code, factor=phase_factor, source_goal_ids=source_goals))
            deload = not structural and loading_week % config.deload_every_nth_loading_week == 0
            if deload:
                target *= config.deload_factor
                adjustments.append(BudgetAdjustment(code="DELOAD", factor=config.deload_factor))
            status = context.training_status
            if not budgets and status is not None and not status.is_warmup and status.form < config.status_form_floor and status.fitness > 0 and status.fatigue / status.fitness >= config.status_fatigue_to_fitness_ratio:
                target *= config.status_moderation_factor
                adjustments.append(BudgetAdjustment(code="STATUS_MODERATION", factor=config.status_moderation_factor))
            if previous_loading_target is not None and not structural and not deload and partial_factor == 1:
                upper = previous_loading_target * (Decimal(1) + config.maximum_weekly_increase)
                lower = previous_loading_target * (Decimal(1) - config.maximum_weekly_decrease)
                target = min(target, upper)
                target = max(target, lower)
            if maximum is not None and target > maximum:
                target = maximum
                adjustments.append(BudgetAdjustment(code="AVAILABILITY_CAP", factor=None, context={"available_minutes": minutes}))
            target = _round(max(target, Decimal(0)))
            if not structural and not deload and partial_factor == 1:
                previous_loading_target = target
        if baseline.confidence is BudgetConfidence.LOW:
            adjustments.append(BudgetAdjustment(code="LOW_CONFIDENCE"))
        width_floor = getattr(config, f"floor_width_{baseline.confidence.value.lower()}")
        width_ceiling = getattr(config, f"ceiling_width_{baseline.confidence.value.lower()}")
        floor = _round(target * (Decimal(1) - width_floor)) if target is not None else None
        ceiling = _round(target * (Decimal(1) + width_ceiling)) if target is not None else None
        if maximum is not None and ceiling is not None:
            ceiling = max(target, min(ceiling, maximum))
        disciplines, missing_strength = _discipline_budgets(context, season, left, target, config)
        strength_warning = strength_warning or missing_strength
        decisions = (
            BudgetDecision(code="WEEK_BOUNDARY", value=f"{left.isoformat()}/{right.isoformat()}", rationale_code="LOCAL_ISO_WEEK_CLIPPED_TO_HORIZON"),
            BudgetDecision(code="COMPETITION_CAPACITY", value=bool(competition_ids), rationale_code="COMPETITION_LOAD_NOT_ESTIMATED"),
        )
        budgets.append(WeeklyTrainingBudget(
            iso_year=iso_year, iso_week=iso_week, week_start=left, week_end=right,
            available_days_in_horizon=(right - left).days + 1,
            dominant_phase=dominant, phase_exposure=exposure,
            competition_goal_ids=competition_ids,
            competition_reserved_capacity=bool(competition_ids),
            total_available_minutes=minutes, available_days=available_days,
            unavailable_days=unavailable_days, max_sessions=max_sessions,
            baseline_load=baseline.weekly_load, target_load=target,
            load_floor=floor, load_ceiling=ceiling, maximum_feasible_load=maximum,
            confidence=baseline.confidence, disciplines=disciplines,
            adjustments=tuple(adjustments), decisions=decisions,
        ))
    if strength_warning:
        warnings.append(PlanningWarning(code="STRENGTH_LOAD_BASELINE_UNAVAILABLE"))
    warnings = tuple(sorted({item.code: item for item in warnings}.values(), key=lambda item: item.code))
    decisions = (
        BudgetDecision(code="BASELINE_METHOD", value=baseline.rationale_code, rationale_code="MEDIAN_OF_NON_OVERLAPPING_WINDOW_BANDS"),
        BudgetDecision(code="LOAD_UNIT", value="load_points", rationale_code="EXISTING_COMBINED_TRAINING_LOAD_UNIT"),
    )
    fingerprint_payload = {
        "context_fingerprint": context.fingerprint,
        "season_structure": season,
        "config": config,
    }
    return WeeklyBudgetPlan(
        planning_start=season.planning_start_date, planning_end=season.planning_end_date,
        timezone_name=context.training.timezone_name, baseline=baseline,
        budgets=tuple(budgets), context_warnings=context.warnings,
        season_warnings=season.warnings, warnings=warnings, decisions=decisions,
        algorithm_version=config.algorithm_version, configuration_version=config.version,
        context_fingerprint=context.fingerprint,
        fingerprint=context_fingerprint(fingerprint_payload),
    )
