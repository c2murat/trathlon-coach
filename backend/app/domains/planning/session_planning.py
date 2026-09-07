from __future__ import annotations

import datetime as dt
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from math import ceil
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.domains.planning.contracts import FrozenModel, PlanningContext, PlanningWarning, context_fingerprint
from app.domains.planning.quality_exposure import QUALITY_SELECTION_VERSION
from app.domains.planning.season_structure import SeasonPhase, SeasonStructure
from app.domains.planning.weekly_budget import DisciplineBudget, WeeklyBudgetPlan, WeeklyTrainingBudget


SESSION_PLAN_SCHEMA_VERSION = 1
_CENT = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


class SessionType(str, Enum):
    RUN_EASY = "RUN_EASY"; RUN_LONG = "RUN_LONG"; RUN_TEMPO = "RUN_TEMPO"
    RUN_THRESHOLD = "RUN_THRESHOLD"; RUN_INTERVAL = "RUN_INTERVAL"; RUN_RECOVERY = "RUN_RECOVERY"
    BIKE_EASY = "BIKE_EASY"; BIKE_ENDURANCE = "BIKE_ENDURANCE"; BIKE_LONG = "BIKE_LONG"
    BIKE_TEMPO = "BIKE_TEMPO"; BIKE_THRESHOLD = "BIKE_THRESHOLD"; BIKE_INTERVAL = "BIKE_INTERVAL"; BIKE_RECOVERY = "BIKE_RECOVERY"
    SWIM_TECHNIQUE = "SWIM_TECHNIQUE"; SWIM_EASY = "SWIM_EASY"; SWIM_AEROBIC = "SWIM_AEROBIC"
    SWIM_THRESHOLD = "SWIM_THRESHOLD"; SWIM_INTERVAL = "SWIM_INTERVAL"; SWIM_ENDURANCE = "SWIM_ENDURANCE"
    GENERAL_STRENGTH = "GENERAL_STRENGTH"
    COMPETITION = "COMPETITION"


class SessionPurpose(str, Enum):
    AEROBIC_BASE = "AEROBIC_BASE"; ENDURANCE = "ENDURANCE"; LONG_ENDURANCE = "LONG_ENDURANCE"
    TECHNIQUE = "TECHNIQUE"; TEMPO_DEVELOPMENT = "TEMPO_DEVELOPMENT"
    THRESHOLD_DEVELOPMENT = "THRESHOLD_DEVELOPMENT"; HIGH_INTENSITY = "HIGH_INTENSITY"
    RECOVERY = "RECOVERY"; GENERAL_STRENGTH = "GENERAL_STRENGTH"; COMPETITION = "COMPETITION"


class IntensityClass(str, Enum):
    EASY = "EASY"; MODERATE = "MODERATE"; HARD = "HARD"; EVENT = "EVENT"


class SessionPriority(str, Enum):
    REQUIRED = "REQUIRED"; KEY = "KEY"; SUPPORT = "SUPPORT"; OPTIONAL = "OPTIONAL"


class SessionPlacementDecision(FrozenModel):
    code: str
    score: int | None = None
    preferred_date_used: bool = False
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class SessionPrescription(FrozenModel):
    date: date
    discipline: Literal["running", "cycling", "swimming", "strength", "competition"]
    session_type: SessionType
    purpose: SessionPurpose
    intensity: IntensityClass
    priority: SessionPriority
    key_session: bool = False
    optional: bool = False
    flexible: bool = True
    target_duration_minutes: int | None = Field(default=None, ge=1)
    target_load: Decimal | None = Field(default=None, ge=0)
    load_floor: Decimal | None = Field(default=None, ge=0)
    load_ceiling: Decimal | None = Field(default=None, ge=0)
    discipline_target_share: Decimal | None = Field(default=None, ge=0, le=1)
    iso_year: int
    iso_week: int
    weekly_budget_start: date
    weekly_budget_end: date
    related_goal_ids: tuple[UUID, ...] = ()
    phase: SeasonPhase
    placement: SessionPlacementDecision
    rule_version: str

    @model_validator(mode="after")
    def validate_load_range(self):
        values = (self.load_floor, self.target_load, self.load_ceiling)
        if any(item is None for item in values) and not all(item is None for item in values):
            raise ValueError("session load range must be wholly known or unknown")
        if self.target_load is not None and not (self.load_floor <= self.target_load <= self.load_ceiling):
            raise ValueError("session load range is inconsistent")
        if self.session_type is SessionType.COMPETITION and (self.target_load is not None or self.target_duration_minutes is not None):
            raise ValueError("competition load and duration are not estimated in 0.8F.5A")
        return self


class WeeklySessionPlan(FrozenModel):
    iso_year: int
    iso_week: int
    week_start: date
    week_end: date
    sessions: tuple[SessionPrescription, ...]
    rest_dates: tuple[date, ...]
    unavailable_dates: tuple[date, ...]
    budget_target_load: Decimal | None = Field(default=None, ge=0)
    planned_load: Decimal | None = Field(default=None, ge=0)
    load_delta: Decimal | None = None
    warnings: tuple[PlanningWarning, ...] = ()
    quality_selection_trace: tuple["QualitySelectionDecision", ...] = ()


class QualitySelectionDecision(FrozenModel):
    candidate_discipline: str
    candidate_session_type: SessionType
    historical_exposure: Decimal = Field(ge=0)
    planned_exposure: Decimal = Field(ge=0)
    stimulus_need: Decimal = Field(ge=0)
    quality_debt: int = Field(ge=0)
    phase_relevance: int = Field(ge=0)
    goal_relevance: Decimal = Field(ge=0)
    discipline_need: Decimal = Field(ge=0)
    target_share: Decimal = Field(ge=0)
    selected: bool
    reason: str
    algorithm_version: str
    base_session_type: SessionType | None = None
    quality_capable: bool = True
    quality_candidate_type: SessionType | None = None
    cold_start: bool = False
    opportunity_lost: bool = False
    quality_debt_before: int = Field(default=0, ge=0)
    quality_debt_after: int = Field(default=0, ge=0)


class SessionPlan(FrozenModel):
    schema_version: int = SESSION_PLAN_SCHEMA_VERSION
    planning_start: date
    planning_end: date
    timezone_name: str
    weeks: tuple[WeeklySessionPlan, ...]
    warnings: tuple[PlanningWarning, ...]
    algorithm_version: str
    configuration_version: str
    context_fingerprint: str
    weekly_budget_fingerprint: str
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class SessionPlanningConfig(FrozenModel):
    version: str = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)
    maximum_frequency_increase_per_discipline: int = Field(default=1, ge=0, le=3)
    max_key_sessions_per_week: int = Field(default=2, ge=0, le=4)
    max_quality_sessions_per_week: int = Field(default=1, ge=0, le=2)
    minimum_gap_between_key_sessions_days: int = Field(default=2, ge=0, le=6)
    allow_double_sessions: bool = False
    load_tolerance: Decimal = Field(default=Decimal("0.15"), ge=0, le=Decimal("0.50"))
    long_duration_growth_limit: Decimal = Field(default=Decimal("0.10"), ge=0, le=Decimal("0.50"))
    default_run_minutes: int = Field(default=45, ge=15)
    default_bike_minutes: int = Field(default=60, ge=15)
    default_swim_minutes: int = Field(default=45, ge=15)
    default_strength_minutes: int = Field(default=40, ge=15)
    default_long_run_minutes: int = Field(default=75, ge=30)
    default_long_bike_minutes: int = Field(default=120, ge=45)
    minimum_session_minutes: int = Field(default=20, ge=10)
    preferred_day_score: int = 100
    rest_day_penalty: int = 40
    key_spacing_score: int = 30
    discipline_minimum_share_for_second_session: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    underrepresentation_tolerance: Decimal = Field(default=Decimal("0.15"), ge=0, le=Decimal("0.50"))
    long_bike_progression_minutes: int = Field(default=15, ge=0, le=30)
    long_run_progression_minutes: int = Field(default=10, ge=0, le=20)
    taper_long_duration_factor: Decimal = Field(default=Decimal("0.65"), gt=0, le=1)
    deload_long_duration_factor: Decimal = Field(default=Decimal("0.85"), gt=0, le=1)
    long_bike_objective_fraction: Decimal = Field(default=Decimal("0.95"), gt=0, le=1)
    long_run_objective_fraction: Decimal = Field(default=Decimal("0.90"), gt=0, le=1)
    long_bike_safety_cap_minutes: int = Field(default=180, ge=60)
    long_run_safety_cap_minutes: int = Field(default=120, ge=45)
    swim_progression_minutes: int = Field(default=5, ge=0, le=15)
    # Floor for the objective-derived reference before phase/type factors; it
    # is deliberately not a final-session minimum.
    swim_objective_baseline_floor_minutes: int = Field(default=25, ge=15, le=60)
    swim_safety_cap_minutes: int = Field(default=90, ge=30, le=180)
    swim_objective_overhead_factor: Decimal = Field(default=Decimal("1.35"), ge=1, le=Decimal("2.00"))
    swim_recovery_factor: Decimal = Field(default=Decimal("0.65"), gt=0, le=1)
    swim_maintenance_factor: Decimal = Field(default=Decimal("0.80"), gt=0, le=1)
    swim_build_factor: Decimal = Field(default=Decimal("0.90"), gt=0, le=Decimal("1.25"))
    swim_specific_factor: Decimal = Field(default=Decimal("1.00"), gt=0, le=Decimal("1.50"))
    swim_taper_factor: Decimal = Field(default=Decimal("0.60"), gt=0, le=1)
    swim_technique_factor: Decimal = Field(default=Decimal("0.90"), gt=0, le=1)
    swim_easy_factor: Decimal = Field(default=Decimal("0.80"), gt=0, le=1)
    swim_aerobic_factor: Decimal = Field(default=Decimal("1.00"), gt=0, le=Decimal("1.25"))
    swim_threshold_factor: Decimal = Field(default=Decimal("1.05"), gt=0, le=Decimal("1.25"))
    swim_interval_factor: Decimal = Field(default=Decimal("1.00"), gt=0, le=Decimal("1.25"))
    minimum_same_long_spacing_days: int = Field(default=5, ge=3, le=7)


class SessionPlanValidationIssue(FrozenModel):
    code: str
    date: dt.date | None = None
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class SessionPlanValidationError(ValueError):
    def __init__(self, issues: tuple[SessionPlanValidationIssue, ...]):
        self.issues = issues
        super().__init__(", ".join(item.code for item in issues))


class _Need:
    __slots__ = ("discipline", "session_type", "purpose", "intensity", "priority", "key", "optional", "duration", "share", "load", "goals", "phase")

    def __init__(self, discipline, session_type, purpose, intensity, priority, key, optional, duration, share, load, goals, phase):
        self.discipline = discipline; self.session_type = session_type; self.purpose = purpose
        self.intensity = intensity; self.priority = priority; self.key = key; self.optional = optional
        self.duration = duration; self.share = share; self.load = load; self.goals = goals; self.phase = phase


def _window(context, days):
    return next((item for item in context.training.windows if item.days == days), None)


def _historical_sport(context, discipline):
    window = _window(context, 28)
    return next((item for item in window.sports if item.sport == discipline), None) if window else None


def _frequency(context, budget: WeeklyTrainingBudget, config: SessionPlanningConfig):
    active = [item for item in budget.disciplines if item.discipline != "strength" and (item.target_share or 0) > 0]
    requested_strength = context.preferences.strength_sessions_per_week if any(item.discipline == "strength" for item in budget.disciplines) else 0
    counts = {item.discipline: 1 for item in active}
    counts["strength"] = requested_strength
    competition_sessions = len(budget.competition_goal_ids)
    capacity = min(
        budget.max_sessions,
        max(0, context.preferences.max_sessions_per_week - competition_sessions),
    )
    # If every day in the horizon is trainable, reserve one complete recovery day.
    # Existing unavailable days already provide that recovery opportunity.
    if budget.available_days_in_horizon >= 6 and budget.available_days == budget.available_days_in_horizon:
        capacity = min(capacity, max(0, budget.available_days_in_horizon - 1 - competition_sessions))
    if len(active) == 1 and budget.dominant_phase not in {SeasonPhase.TAPER, SeasonPhase.RECOVERY}:
        counts[active[0].discipline] = min(3, capacity)
    if budget.dominant_phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC}:
        for item in sorted(active, key=lambda value: (-(value.target_share or 0), value.discipline)):
            if (item.target_share or 0) < config.discipline_minimum_share_for_second_session:
                continue
            if sum(counts.values()) >= capacity:
                break
            counts[item.discipline] += 1
    if budget.dominant_phase is SeasonPhase.TAPER:
        counts["strength"] = min(counts["strength"], 1)
        nearby_primary = any(
            goal.priority == "A" and budget.week_start <= goal.event_date <= budget.week_end + timedelta(days=7)
            for goal in context.goals
        )
        if not nearby_primary and len(active) == 1 and sum(counts.values()) < capacity:
            counts[active[0].discipline] += 1
    while sum(counts.values()) > capacity:
        candidates = [key for key in counts if counts[key] > (1 if key != "strength" else 0)]
        if not candidates:
            break
        key = max(candidates, key=lambda value: (counts[value], value))
        counts[key] -= 1
    if sum(counts.values()) > capacity:
        for key in sorted(counts, key=lambda value: (value == "strength", value), reverse=True):
            while counts[key] and sum(counts.values()) > capacity:
                counts[key] -= 1
    return counts


QUALITY_FAMILIES = {
    "running": (SessionType.RUN_TEMPO, SessionType.RUN_THRESHOLD, SessionType.RUN_INTERVAL),
    "cycling": (SessionType.BIKE_TEMPO, SessionType.BIKE_THRESHOLD, SessionType.BIKE_INTERVAL),
    "swimming": (SessionType.SWIM_THRESHOLD, SessionType.SWIM_INTERVAL),
}
QUALITY_CAPABLE_BASE_TYPES = {
    "running": {SessionType.RUN_EASY},
    "cycling": {SessionType.BIKE_ENDURANCE},
    "swimming": {SessionType.SWIM_AEROBIC},
}


def _quality_candidate(discipline, progression, quality_exposure):
    rotations = {
        "running": QUALITY_FAMILIES["running"],
        "cycling": QUALITY_FAMILIES["cycling"],
        "swimming": QUALITY_FAMILIES["swimming"],
    }
    rotation = rotations[discipline]
    offset = progression % len(rotation)
    ordered = rotation[offset:] + rotation[:offset]
    return min(ordered, key=lambda item: quality_exposure.get(item, 0))


def _stimulus_need(family, candidate, quality_exposure):
    exposures = tuple(Decimal(quality_exposure.get(item, 0)) for item in family)
    target = max((Decimal("1"), *exposures))
    return max(Decimal(0), target - Decimal(quality_exposure.get(candidate, 0)))


def _type_sequence(discipline, phase, count, progression=0, quality_exposure=None):
    recovery = phase is SeasonPhase.RECOVERY
    taper = phase is SeasonPhase.TAPER
    if discipline == "running":
        if taper:
            return [SessionType.RUN_EASY, *([SessionType.RUN_RECOVERY] * count)][:count]
        if phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC} and quality_exposure is not None:
            quality = _quality_candidate(discipline, progression, quality_exposure)
        else:
            quality = (
                (SessionType.RUN_TEMPO, SessionType.RUN_THRESHOLD, SessionType.RUN_THRESHOLD)[progression]
                if phase is SeasonPhase.BUILD else
                (SessionType.RUN_THRESHOLD, SessionType.RUN_INTERVAL, SessionType.RUN_THRESHOLD)[progression]
                if phase is SeasonPhase.SPECIFIC else SessionType.RUN_TEMPO
            )
        return ([SessionType.RUN_RECOVERY] * count if recovery else [SessionType.RUN_LONG, quality, *([SessionType.RUN_EASY] * count)])[:count]
    if discipline == "cycling":
        if taper:
            return [SessionType.BIKE_ENDURANCE, *([SessionType.BIKE_RECOVERY] * count)][:count]
        if phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC} and quality_exposure is not None:
            quality = _quality_candidate(discipline, progression, quality_exposure)
        else:
            quality = (
                (SessionType.BIKE_TEMPO, SessionType.BIKE_THRESHOLD, SessionType.BIKE_TEMPO)[progression]
                if phase is SeasonPhase.BUILD else
                (SessionType.BIKE_THRESHOLD, SessionType.BIKE_TEMPO, SessionType.BIKE_INTERVAL)[progression]
                if phase is SeasonPhase.SPECIFIC else SessionType.BIKE_TEMPO
            )
        return ([SessionType.BIKE_RECOVERY] * count if recovery else [SessionType.BIKE_LONG, quality, *([SessionType.BIKE_ENDURANCE] * count)])[:count]
    if discipline == "swimming":
        if taper:
            return [SessionType.SWIM_TECHNIQUE, *([SessionType.SWIM_EASY] * count)][:count]
        if recovery:
            return [SessionType.SWIM_EASY] * count
        rotation = (
            (SessionType.SWIM_AEROBIC, SessionType.SWIM_THRESHOLD, SessionType.SWIM_TECHNIQUE)
            if phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC} else
            (SessionType.SWIM_TECHNIQUE, SessionType.SWIM_AEROBIC, SessionType.SWIM_TECHNIQUE)
        )
        first = rotation[progression]
        if first is SessionType.SWIM_THRESHOLD and quality_exposure is not None:
            first = _quality_candidate(discipline, progression, quality_exposure)
        return [first, *([SessionType.SWIM_AEROBIC, SessionType.SWIM_TECHNIQUE] * count)][:count]
    return [SessionType.GENERAL_STRENGTH] * count


def _metadata(session_type):
    if session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG, SessionType.SWIM_ENDURANCE}:
        return SessionPurpose.LONG_ENDURANCE, IntensityClass.MODERATE, SessionPriority.KEY, True
    if session_type in {SessionType.RUN_THRESHOLD, SessionType.BIKE_THRESHOLD, SessionType.SWIM_THRESHOLD}:
        return SessionPurpose.THRESHOLD_DEVELOPMENT, IntensityClass.HARD, SessionPriority.KEY, True
    if session_type in {SessionType.RUN_INTERVAL, SessionType.BIKE_INTERVAL, SessionType.SWIM_INTERVAL}:
        return SessionPurpose.HIGH_INTENSITY, IntensityClass.HARD, SessionPriority.KEY, True
    if session_type in {SessionType.RUN_TEMPO, SessionType.BIKE_TEMPO}:
        return SessionPurpose.TEMPO_DEVELOPMENT, IntensityClass.MODERATE, SessionPriority.KEY, True
    if session_type in {SessionType.RUN_RECOVERY, SessionType.BIKE_RECOVERY, SessionType.SWIM_EASY}:
        return SessionPurpose.RECOVERY, IntensityClass.EASY, SessionPriority.SUPPORT, False
    if session_type is SessionType.SWIM_TECHNIQUE:
        return SessionPurpose.TECHNIQUE, IntensityClass.EASY, SessionPriority.SUPPORT, False
    if session_type is SessionType.GENERAL_STRENGTH:
        return SessionPurpose.GENERAL_STRENGTH, IntensityClass.MODERATE, SessionPriority.SUPPORT, False
    return SessionPurpose.AEROBIC_BASE, IntensityClass.EASY, SessionPriority.SUPPORT, False


def _objective_long_cap(context, discipline, week_start, config):
    sport = "bike" if discipline == "cycling" else "run"
    candidates = []
    for goal in context.goals:
        if goal.event_date < week_start:
            continue
        distance = sum(item.distance_m for item in goal.segments if item.sport == sport)
        if distance:
            priority = {"A": 3, "B": 2, "C": 1}[goal.priority]
            candidates.append((priority, -((goal.event_date - week_start).days), distance))
    distance = max(candidates)[2] if candidates else 0
    if not distance:
        return config.default_long_bike_minutes if discipline == "cycling" else config.default_long_run_minutes
    seconds_per_meter = Decimal("0.125") if discipline == "cycling" else Decimal("0.30")
    # Defaults are baselines/fallbacks. Objective relevance, documented safety
    # bounds and athlete availability form the actual progression ceiling.
    fraction = config.long_bike_objective_fraction if discipline == "cycling" else config.long_run_objective_fraction
    lower = 60 if discipline == "cycling" else 45
    upper = config.long_bike_safety_cap_minutes if discipline == "cycling" else config.long_run_safety_cap_minutes
    return max(lower, min(upper, int(Decimal(distance) * seconds_per_meter * fraction / Decimal(60))))


def _swim_objective_minutes(context, week_start, config):
    css = context.performance.swimming_css_seconds_per_100m
    if css is None or css <= 0:
        return None
    candidates = []
    for goal in context.goals:
        if goal.event_date < week_start:
            continue
        distance = sum(item.distance_m for item in goal.segments if item.sport == "swim")
        if distance:
            candidates.append(({"A": 3, "B": 2, "C": 1}[goal.priority], -((goal.event_date - week_start).days), distance))
    if not candidates:
        return None
    distance = max(candidates)[2]
    race_reference = Decimal(distance) * Decimal(str(css)) / Decimal(100 * 60)
    useful_session = ceil(race_reference * config.swim_objective_overhead_factor)
    return max(config.swim_objective_baseline_floor_minutes, min(config.swim_safety_cap_minutes, useful_session))


def _swim_duration(context, budget, session_type, config, previous_duration):
    history = _historical_sport(context, "swimming")
    historical_average = round(history.duration_seconds / 60 / history.activity_count) if history and history.activity_count and history.duration_seconds else None
    objective = _swim_objective_minutes(context, budget.week_start, config)
    baseline = historical_average or config.default_swim_minutes
    if objective is not None:
        baseline = min(baseline, objective)
    phase_factor = {
        SeasonPhase.RECOVERY: config.swim_recovery_factor,
        SeasonPhase.PREPARATION: config.swim_maintenance_factor,
        SeasonPhase.BASE: config.swim_maintenance_factor,
        SeasonPhase.MAINTENANCE: config.swim_maintenance_factor,
        SeasonPhase.BUILD: config.swim_build_factor,
        SeasonPhase.SPECIFIC: config.swim_specific_factor,
        SeasonPhase.TAPER: config.swim_taper_factor,
        SeasonPhase.COMPETITION: config.swim_taper_factor,
    }[budget.dominant_phase]
    type_factor = (
        config.swim_technique_factor if session_type is SessionType.SWIM_TECHNIQUE else
        config.swim_easy_factor if session_type is SessionType.SWIM_EASY else
        config.swim_threshold_factor if session_type is SessionType.SWIM_THRESHOLD else
        config.swim_interval_factor if session_type is SessionType.SWIM_INTERVAL else
        config.swim_aerobic_factor
    )
    objective_target = Decimal(objective or baseline) * phase_factor
    candidate = max(Decimal(baseline) * phase_factor, objective_target) * type_factor
    if budget.dominant_phase in {SeasonPhase.PREPARATION, SeasonPhase.BASE, SeasonPhase.MAINTENANCE, SeasonPhase.BUILD, SeasonPhase.SPECIFIC}:
        prior = previous_duration or baseline
        candidate = min(candidate, Decimal(prior + config.swim_progression_minutes))
    available = max((slot.available_minutes for _, slot in _slots(context, budget) if slot is not None), default=0)
    return max(config.minimum_session_minutes, min(config.swim_safety_cap_minutes, available, int(candidate.quantize(Decimal("1"), rounding=ROUND_HALF_UP))))


def _duration(context, budget, discipline, session_type, config, previous_long):
    defaults = {"running": config.default_run_minutes, "cycling": config.default_bike_minutes, "swimming": config.default_swim_minutes, "strength": config.default_strength_minutes}
    value = defaults[discipline]
    history = _historical_sport(context, discipline)
    if discipline == "swimming":
        return _swim_duration(context, budget, session_type, config, previous_long.get("swimming"))
    if session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG}:
        fallback = config.default_long_run_minutes if discipline == "running" else config.default_long_bike_minutes
        historical_minutes = Decimal(history.longest_duration_seconds) / Decimal(60) if history and history.longest_duration_seconds else None
        baseline = int(historical_minutes) if historical_minutes else fallback
        prior = previous_long.get(discipline, baseline)
        step = config.long_bike_progression_minutes if discipline == "cycling" else config.long_run_progression_minutes
        value = min(_objective_long_cap(context, discipline, budget.week_start, config), prior + step)
        if "DELOAD" in {item.code for item in budget.adjustments}:
            value = int(prior * config.deload_long_duration_factor)
        if budget.dominant_phase is SeasonPhase.TAPER:
            value = int(prior * config.taper_long_duration_factor)
        available = max((slot.available_minutes for _, slot in _slots(context, budget) if slot is not None), default=0)
        value = min(value, available)
    elif history and history.activity_count and history.duration_seconds:
        historical_average = round(history.duration_seconds / 60 / history.activity_count)
        value = max(config.minimum_session_minutes, min(value, historical_average))
    if session_type.name.endswith("RECOVERY"):
        value = max(config.minimum_session_minutes, int(value * 0.7))
    return value


def _needs(context, budget, config, previous_long, quality_exposure=None, quality_debt=None, trace_out=None, historical_exposure=None):
    quality_exposure = quality_exposure or {}
    quality_debt = quality_debt if quality_debt is not None else {}
    historical_exposure = historical_exposure or {}
    counts = _frequency(context, budget, config)
    discipline_map = {item.discipline: item for item in budget.disciplines}
    needs = []
    structural_long_count = sum(
        counts.get(discipline, 0) > 0
        for discipline in ("running", "cycling")
        if budget.dominant_phase not in {SeasonPhase.TAPER, SeasonPhase.RECOVERY}
    )
    week_ordinal = max(0, (budget.week_start - context.request.planning_date).days // 7)
    progression = week_ordinal % 3
    single_a_triathlon = (
        len(context.goals) == 1 and context.goals[0].priority == "A"
        and {item.sport for item in context.goals[0].segments} == {"swim", "bike", "run"}
    )
    sequences = {
        discipline: _type_sequence(
            discipline, budget.dominant_phase, counts.get(discipline, 0), progression,
            quality_exposure if context.quality_exposure is not None or single_a_triathlon else None,
        )
        for discipline in ("running", "cycling", "swimming", "strength")
    }
    opportunities = {}
    for discipline in ("running", "cycling", "swimming"):
        types = sequences[discipline]
        explicit = next(((index, item) for index, item in enumerate(types) if item in QUALITY_FAMILIES[discipline]), None)
        if explicit is not None:
            index, session_type = explicit
            opportunities[discipline] = (index, session_type, session_type)
            continue
        alternative = next(((index, item) for index, item in enumerate(types) if item in QUALITY_CAPABLE_BASE_TYPES[discipline]), None) if context.quality_exposure is not None and budget.dominant_phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC} else None
        if alternative is not None:
            index, base_type = alternative
            opportunities[discipline] = (
                index, base_type, _quality_candidate(discipline, progression, quality_exposure),
            )
    quality_candidates = list(opportunities)
    candidate_type = {discipline: item[2] for discipline, item in opportunities.items()}
    stimulus_need = {
        discipline: _stimulus_need(QUALITY_FAMILIES[discipline], session_type, quality_exposure)
        for discipline, session_type in candidate_type.items()
    }
    cold_start = {
        discipline: not any(Decimal(quality_exposure.get(item, 0)) > 0 for item in QUALITY_FAMILIES[discipline])
        for discipline in quality_candidates
    }
    comparable_need = max(stimulus_need.values(), default=Decimal("1"))
    for discipline in quality_candidates:
        if cold_start[discipline]:
            stimulus_need[discipline] = comparable_need
    maximum_discipline_exposure = max(
        (Decimal(quality_exposure.get(item, 0)) for item in quality_candidates), default=Decimal(0),
    )
    discipline_need = {
        discipline: maximum_discipline_exposure - Decimal(quality_exposure.get(discipline, 0))
        for discipline in quality_candidates
    }
    if context.quality_exposure is None:
        quality_candidates.sort(key=lambda discipline: (
            quality_exposure.get(discipline, 0),
            -(discipline_map.get(discipline).target_share or 0) if discipline_map.get(discipline) else 0,
            discipline,
        ))
    else:
        quality_candidates.sort(key=lambda discipline: (
            -stimulus_need[discipline],
            -quality_debt.get(discipline, 0),
            -discipline_need[discipline],
            -(discipline_map.get(discipline).target_share or 0) if discipline_map.get(discipline) else 0,
            discipline,
        ))
    selected_quality = quality_candidates[0] if quality_candidates else None
    debt_before = {discipline: quality_debt.get(discipline, 0) for discipline in quality_candidates}
    debt_after = {
        discipline: 0 if discipline == selected_quality else debt_before[discipline] + 1
        for discipline in quality_candidates
    }
    if trace_out is not None and context.quality_exposure is not None:
        for discipline in quality_candidates:
            allocation = discipline_map.get(discipline); session_type = candidate_type[discipline]
            _, base_type, _ = opportunities[discipline]
            exposure = Decimal(quality_exposure.get(session_type, 0)); discipline_exposure = Decimal(quality_exposure.get(discipline, 0))
            historical = Decimal(historical_exposure.get(session_type, 0))
            trace_out.append(QualitySelectionDecision(
                candidate_discipline=discipline, candidate_session_type=session_type,
                historical_exposure=historical, planned_exposure=max(Decimal(0), exposure - historical),
                stimulus_need=stimulus_need[discipline], quality_debt=quality_debt.get(discipline, 0),
                phase_relevance=1, goal_relevance=allocation.target_share or Decimal(0),
                discipline_need=discipline_need[discipline], target_share=allocation.target_share or Decimal(0),
                selected=discipline == selected_quality,
                reason="LOWEST_STIMULUS_EXPOSURE_THEN_DEBT_DISCIPLINE_SHARE" if discipline == selected_quality else "GLOBAL_QUALITY_SLOT_AWARDED_TO_OTHER_DISCIPLINE",
                algorithm_version=QUALITY_SELECTION_VERSION,
                base_session_type=base_type, quality_capable=True,
                quality_candidate_type=session_type,
                cold_start=cold_start[discipline],
                opportunity_lost=discipline != selected_quality,
                quality_debt_before=debt_before[discipline],
                quality_debt_after=debt_after[discipline],
            ))
    if context.quality_exposure is not None:
        quality_debt.update(debt_after)
    non_long_key_limit = min(
        config.max_quality_sessions_per_week,
        max(0, config.max_key_sessions_per_week - max(0, structural_long_count - 1)),
    )
    non_long_key_count = 0
    effective_sequences = {}
    promoted_bases = {}
    if selected_quality in opportunities:
        index, base_type, promoted_type = opportunities[selected_quality]
        if base_type != promoted_type:
            sequences[selected_quality][index] = promoted_type
            promoted_bases[(selected_quality, index)] = base_type
    for discipline in ("running", "cycling", "swimming", "strength"):
        effective = []
        for session_type in sequences[discipline]:
            key = _metadata(session_type)[3]
            structural_long = session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG}
            if key and not structural_long and (discipline != selected_quality or non_long_key_count >= non_long_key_limit):
                session_type = {"running": SessionType.RUN_EASY, "cycling": SessionType.BIKE_ENDURANCE, "swimming": SessionType.SWIM_AEROBIC}[discipline]
                key = False
            non_long_key_count += int(key and not structural_long)
            effective.append(session_type)
        effective_sequences[discipline] = effective
    for discipline in ("running", "cycling", "swimming", "strength"):
        types = effective_sequences[discipline]
        allocation = discipline_map.get(discipline)
        weights = [Decimal("1.35") if item.name.endswith("LONG") else Decimal("1.10") if item.name.endswith(("THRESHOLD", "TEMPO", "INTERVAL")) else Decimal("1") for item in types]
        load_total = allocation.target_load if allocation else None
        loads = []
        if load_total is not None and weights:
            total_weight = sum(weights, Decimal(0)); prior = Decimal(0)
            for index, weight in enumerate(weights):
                load = _round(load_total - prior) if index == len(weights) - 1 else _round(load_total * weight / total_weight)
                loads.append(load); prior += load
        else:
            loads = [None] * len(types)
        for index, session_type in enumerate(types):
            purpose, intensity, priority, key = _metadata(session_type)
            history = _historical_sport(context, discipline)
            historical_weekly = ceil(history.activity_count / 4) if history and history.activity_count else 0
            optional = discipline != "strength" and index >= max(1, historical_weekly)
            if optional and not key:
                priority = SessionPriority.OPTIONAL
            needs.append(_Need(
                discipline, session_type, purpose, intensity, priority, key,
                optional,
                _duration(context, budget, discipline, promoted_bases.get((discipline, index), session_type), config, previous_long),
                allocation.target_share if allocation else None, loads[index],
                tuple(item.competition_goal_id for item in context.goals), budget.dominant_phase,
            ))
    return needs


def _slots(context, budget):
    by_weekday = {item.weekday: item for item in context.preferences.availability_slots}
    return [(budget.week_start + timedelta(days=offset), by_weekday.get((budget.week_start + timedelta(days=offset)).weekday())) for offset in range(budget.available_days_in_horizon)]


def _place(context, budget, needs, occupied, config, previous_long_dates):
    sessions = []; warnings = []; used_minutes = {}; used_count = {}; key_dates = list(occupied)
    rank = {SessionPriority.REQUIRED: 0, SessionPriority.KEY: 1, SessionPriority.SUPPORT: 2, SessionPriority.OPTIONAL: 3}
    needs = sorted(needs, key=lambda item: (rank[item.priority], not item.session_type.name.endswith("LONG"), item.discipline, item.session_type.value))
    horizon_days = {day for day, _ in _slots(context, budget)}
    preferred_rest = {day for day in horizon_days if day.weekday() in context.preferences.preferred_rest_days}
    primary_dates = sorted(goal.event_date for goal in context.goals if goal.priority == "A")
    competition_dates = sorted(goal.event_date for goal in context.goals)
    pre_primary_rest = {event - timedelta(days=1) for event in primary_dates if event - timedelta(days=1) in horizon_days}
    reserved_rest = preferred_rest | pre_primary_rest
    for need in needs:
        candidates = []; fallback_candidates = []
        preferred = context.preferences.preferred_long_run_day if need.session_type is SessionType.RUN_LONG else context.preferences.preferred_long_bike_day if need.session_type is SessionType.BIKE_LONG else None
        for day, slot in _slots(context, budget):
            if day in occupied or slot is None or slot.available_minutes <= 0 or slot.max_sessions <= 0:
                continue
            max_count = min(slot.max_sessions, context.preferences.max_sessions_per_day)
            if not config.allow_double_sessions:
                max_count = min(max_count, 1)
            if used_count.get(day, 0) >= max_count or used_minutes.get(day, 0) + need.duration > slot.available_minutes:
                continue
            if need.discipline == "strength" and any(timedelta(0) < event - day <= timedelta(days=2) for event in competition_dates):
                continue
            prior_long = previous_long_dates.get(need.discipline) if need.session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG} else None
            if prior_long is not None and 0 < (day - prior_long).days < config.minimum_same_long_spacing_days:
                continue
            gap = min((abs((day - other).days) for other in key_dates), default=99)
            score = (config.preferred_day_score if preferred == day.weekday() else 0)
            score -= config.rest_day_penalty if day.weekday() in context.preferences.preferred_rest_days else 0
            score += config.key_spacing_score if need.key and gap >= config.minimum_gap_between_key_sessions_days else 0
            score += slot.available_minutes - used_minutes.get(day, 0) - need.duration
            candidate = (score, day, preferred == day.weekday(), gap)
            fallback_candidates.append(candidate)
            if day not in reserved_rest:
                candidates.append(candidate)
        if not candidates and fallback_candidates:
            candidates = fallback_candidates
        if not candidates:
            warnings.append(PlanningWarning(code="WEEKLY_SESSION_LIMIT_REACHED" if need.optional else "SESSION_PLACEMENT_CONSTRAINT", context={"discipline": need.discipline, "session_type": need.session_type.value}))
            continue
        score, day, preferred_used, gap = sorted(candidates, key=lambda item: (-item[0], item[1], need.session_type.value, need.discipline))[0]
        used_count[day] = used_count.get(day, 0) + 1; used_minutes[day] = used_minutes.get(day, 0) + need.duration
        if need.key:
            if gap < config.minimum_gap_between_key_sessions_days:
                warnings.append(PlanningWarning(code="KEY_SESSION_SPACING_CONSTRAINT", context={"date": day.isoformat()}))
            key_dates.append(day)
        width = config.load_tolerance
        sessions.append(SessionPrescription(
            date=day, discipline=need.discipline, session_type=need.session_type,
            purpose=need.purpose, intensity=need.intensity, priority=need.priority,
            key_session=need.key, optional=need.optional, flexible=True,
            target_duration_minutes=need.duration, target_load=need.load,
            load_floor=_round(need.load * (Decimal(1) - width)) if need.load is not None else None,
            load_ceiling=_round(need.load * (Decimal(1) + width)) if need.load is not None else None,
            discipline_target_share=need.share, iso_year=budget.iso_year, iso_week=budget.iso_week,
            weekly_budget_start=budget.week_start, weekly_budget_end=budget.week_end,
            related_goal_ids=need.goals, phase=need.phase,
            placement=SessionPlacementDecision(code="GREEDY_STABLE_SCORE", score=score, preferred_date_used=preferred_used),
            rule_version=config.version,
        ))
    return sessions, warnings


def _competition_sessions(context, season, budget, config):
    goals = {item.competition_goal_id: item for item in context.goals}
    sessions = []
    for marker in season.competition_markers:
        if budget.week_start <= marker.date <= budget.week_end:
            goal = goals[marker.goal_id]
            sessions.append(SessionPrescription(
                date=marker.date, discipline="competition", session_type=SessionType.COMPETITION,
                purpose=SessionPurpose.COMPETITION, intensity=IntensityClass.EVENT,
                priority=SessionPriority.REQUIRED, key_session=True, optional=False, flexible=False,
                target_duration_minutes=None, target_load=None, load_floor=None, load_ceiling=None,
                discipline_target_share=None, iso_year=budget.iso_year, iso_week=budget.iso_week,
                weekly_budget_start=budget.week_start, weekly_budget_end=budget.week_end,
                related_goal_ids=(goal.competition_goal_id,), phase=SeasonPhase.COMPETITION,
                placement=SessionPlacementDecision(code="COMPETITION_MARKER_DATE", preferred_date_used=True),
                rule_version=config.version,
            ))
    return sessions


def validate_session_plan(plan: SessionPlan, context: PlanningContext, season: SeasonStructure, budgets: WeeklyBudgetPlan, config: SessionPlanningConfig):
    issues = []
    if len(plan.weeks) != len(budgets.budgets):
        issues.append(SessionPlanValidationIssue(code="WEEK_COUNT_MISMATCH"))
    slots = {item.weekday: item for item in context.preferences.availability_slots}
    marker_dates = {item.goal_id: item.date for item in season.competition_markers}
    for week, budget in zip(plan.weeks, budgets.budgets):
        if (
            week.iso_year != budget.iso_year
            or week.iso_week != budget.iso_week
            or week.week_start != budget.week_start
            or week.week_end != budget.week_end
        ):
            issues.append(SessionPlanValidationIssue(code="WEEK_BUDGET_IDENTITY_MISMATCH", date=week.week_start))
        if week.budget_target_load != budget.target_load:
            issues.append(SessionPlanValidationIssue(code="WEEK_BUDGET_TARGET_MISMATCH", date=week.week_start))
        daily = {}
        for session in week.sessions:
            daily.setdefault(session.date, []).append(session)
            if not (plan.planning_start <= session.date <= plan.planning_end):
                issues.append(SessionPlanValidationIssue(code="SESSION_OUTSIDE_HORIZON", date=session.date))
            if session.session_type is SessionType.COMPETITION:
                if not session.related_goal_ids or marker_dates.get(session.related_goal_ids[0]) != session.date:
                    issues.append(SessionPlanValidationIssue(code="COMPETITION_DATE_INVALID", date=session.date))
            else:
                slot = slots.get(session.date.weekday())
                if slot is None or slot.available_minutes <= 0 or slot.max_sessions <= 0:
                    issues.append(SessionPlanValidationIssue(code="SESSION_ON_UNAVAILABLE_DAY", date=session.date))
        for day, sessions in daily.items():
            slot = slots.get(day.weekday())
            training_sessions = [item for item in sessions if item.session_type is not SessionType.COMPETITION]
            if slot is not None and sum(item.target_duration_minutes or 0 for item in training_sessions) > slot.available_minutes:
                issues.append(SessionPlanValidationIssue(code="DAILY_MINUTES_EXCEEDED", date=day))
            daily_limit = context.preferences.max_sessions_per_day
            if slot is not None:
                daily_limit = min(daily_limit, slot.max_sessions)
            if len(sessions) > daily_limit:
                issues.append(SessionPlanValidationIssue(code="DAILY_SESSION_LIMIT_EXCEEDED", date=day))
            if any(item.session_type is SessionType.COMPETITION for item in sessions) and len(sessions) > 1:
                issues.append(SessionPlanValidationIssue(code="COMPETITION_DAY_NOT_EXCLUSIVE", date=day))
        training_count = sum(item.session_type is not SessionType.COMPETITION for item in week.sessions)
        if training_count > budget.max_sessions or len(week.sessions) > context.preferences.max_sessions_per_week:
            issues.append(SessionPlanValidationIssue(code="WEEKLY_SESSION_LIMIT_EXCEEDED", date=week.week_start))
        quantified = [item.target_load for item in week.sessions if item.target_load is not None]
        expected_planned = _round(sum(quantified, Decimal(0))) if budget.target_load is not None else None
        expected_delta = _round(expected_planned - budget.target_load) if expected_planned is not None else None
        if week.planned_load != expected_planned:
            issues.append(SessionPlanValidationIssue(code="PLANNED_LOAD_MISMATCH", date=week.week_start))
        if week.load_delta != expected_delta:
            issues.append(SessionPlanValidationIssue(code="LOAD_DELTA_MISMATCH", date=week.week_start))
        if expected_planned is not None and budget.load_ceiling is not None and expected_planned > budget.load_ceiling:
            issues.append(SessionPlanValidationIssue(code="WEEKLY_LOAD_CEILING_EXCEEDED", date=week.week_start))
        outside_materialization = expected_delta is not None and (
            abs(expected_delta) > budget.target_load * config.load_tolerance
            or (budget.load_floor is not None and expected_planned < budget.load_floor)
            or (budget.load_ceiling is not None and expected_planned > budget.load_ceiling)
        )
        if outside_materialization and budget.available_days_in_horizon == 7:
            expected_warning = "WEEKLY_LOAD_BUDGET_UNDERSHOT" if expected_delta < 0 else "WEEKLY_LOAD_BUDGET_OVERSHOT"
            if expected_warning not in {item.code for item in week.warnings}:
                issues.append(SessionPlanValidationIssue(code="WEEKLY_LOAD_WARNING_MISSING", date=week.week_start))
    return tuple(issues)


def build_session_plan(context: PlanningContext, season: SeasonStructure, budgets: WeeklyBudgetPlan, config: SessionPlanningConfig) -> SessionPlan:
    if (
        budgets.context_fingerprint != context.fingerprint
        or budgets.planning_start != season.planning_start_date
        or budgets.planning_end != season.planning_end_date
        or len(budgets.budgets) == 0
    ):
        raise ValueError("session planning inputs are incompatible")
    stimulus_types = {
        ("running", "TEMPO"): SessionType.RUN_TEMPO, ("running", "THRESHOLD"): SessionType.RUN_THRESHOLD,
        ("running", "INTERVAL"): SessionType.RUN_INTERVAL, ("cycling", "TEMPO"): SessionType.BIKE_TEMPO,
        ("cycling", "SWEET_SPOT"): SessionType.BIKE_TEMPO, ("cycling", "THRESHOLD"): SessionType.BIKE_THRESHOLD,
        ("cycling", "INTERVAL"): SessionType.BIKE_INTERVAL, ("swimming", "TECHNIQUE"): SessionType.SWIM_TECHNIQUE,
        ("swimming", "AEROBIC"): SessionType.SWIM_AEROBIC, ("swimming", "THRESHOLD"): SessionType.SWIM_THRESHOLD,
        ("swimming", "INTERVAL"): SessionType.SWIM_INTERVAL,
    }
    historical_exposure = {}
    for signal in context.quality_exposure.signals if context.quality_exposure is not None else ():
        session_type = stimulus_types[(signal.discipline, signal.stimulus)]
        historical_exposure[session_type] = historical_exposure.get(session_type, Decimal(0)) + signal.weighted_exposure
        historical_exposure[signal.discipline] = historical_exposure.get(signal.discipline, Decimal(0)) + signal.weighted_exposure
    weeks = []; plan_warnings = []; previous_long = {}; previous_long_dates = {}
    quality_exposure = dict(historical_exposure); quality_debt = {}
    for budget in budgets.budgets:
        quality_trace = []
        competitions = _competition_sessions(context, season, budget, config)
        needs = _needs(
            context, budget, config, previous_long, quality_exposure, quality_debt,
            quality_trace, historical_exposure,
        )
        sessions, warnings = _place(context, budget, needs, {item.date for item in competitions}, config, previous_long_dates)
        sessions = tuple(sorted((*competitions, *sessions), key=lambda item: (item.date, item.session_type.value, item.discipline)))
        for session in sessions:
            if session.session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG}:
                previous_long[session.discipline] = session.target_duration_minutes
                previous_long_dates[session.discipline] = session.date
            elif session.discipline == "swimming" and session.phase not in {SeasonPhase.RECOVERY, SeasonPhase.TAPER, SeasonPhase.COMPETITION}:
                previous_long["swimming"] = session.target_duration_minutes
            explicit_quality = session.session_type.name.endswith(("TEMPO", "THRESHOLD", "INTERVAL"))
            embedded_long_quality = (
                session.session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG}
                and session.phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC}
                and (session.target_duration_minutes or 0) >= 75
            )
            if explicit_quality or embedded_long_quality:
                quality_exposure[session.discipline] = quality_exposure.get(session.discipline, 0) + 1
            if explicit_quality:
                quality_exposure[session.session_type] = quality_exposure.get(session.session_type, 0) + 1
            elif embedded_long_quality:
                embedded_type = SessionType.RUN_TEMPO if session.discipline == "running" else SessionType.BIKE_TEMPO
                quality_exposure[embedded_type] = quality_exposure.get(embedded_type, 0) + Decimal("0.50")
        planned_values = [item.target_load for item in sessions if item.target_load is not None]
        planned = _round(sum(planned_values, Decimal(0))) if budget.target_load is not None else None
        delta = _round(planned - budget.target_load) if planned is not None and budget.target_load is not None else None
        dates = tuple(budget.week_start + timedelta(days=offset) for offset in range(budget.available_days_in_horizon))
        session_dates = {item.date for item in sessions}
        unavailable = tuple(day for day, slot in _slots(context, budget) if slot is None or slot.available_minutes <= 0 or slot.max_sessions <= 0)
        rest = tuple(day for day in dates if day not in session_dates)
        week_warnings = list(warnings)
        partial_week = budget.available_days_in_horizon < 7
        preferred_rest_dates = {day for day in dates if day.weekday() in context.preferences.preferred_rest_days}
        training_session_dates = {item.date for item in sessions if item.session_type is not SessionType.COMPETITION}
        occupied_preferred_rest = preferred_rest_dates & training_session_dates
        if not partial_week and occupied_preferred_rest:
            week_warnings.append(PlanningWarning(
                code="PREFERRED_REST_DAY_UNAVAILABLE",
                context={"weekdays": ",".join(str(day.weekday()) for day in sorted(occupied_preferred_rest))},
            ))
        for session in (() if partial_week else sessions):
            preferred = context.preferences.preferred_long_run_day if session.session_type is SessionType.RUN_LONG else context.preferences.preferred_long_bike_day if session.session_type is SessionType.BIKE_LONG else None
            if preferred is not None and session.date.weekday() != preferred:
                week_warnings.append(PlanningWarning(
                    code="PREFERRED_LONG_DAY_UNAVAILABLE",
                    context={"discipline": session.discipline, "preferred_weekday": preferred},
                ))
        if not sessions and any((item.target_share or 0) > 0 for item in budget.disciplines):
            week_warnings.append(PlanningWarning(
                code="SESSION_PLACEMENT_CONSTRAINT",
                context={"reason": "NO_FEASIBLE_AVAILABILITY"},
            ))
        if budget.target_load is None:
            week_warnings.append(PlanningWarning(code="SESSION_LOAD_TARGET_UNAVAILABLE"))
        outside_materialization = delta is not None and (
            abs(delta) > budget.target_load * config.load_tolerance
            or (budget.load_floor is not None and planned < budget.load_floor)
            or (budget.load_ceiling is not None and planned > budget.load_ceiling)
        )
        if outside_materialization and not partial_week:
            week_warnings.append(PlanningWarning(
                code="WEEKLY_LOAD_BUDGET_UNDERSHOT" if delta < 0 else "WEEKLY_LOAD_BUDGET_OVERSHOT",
                context={"load_delta": str(delta), "iso_week": budget.iso_week},
            ))
        for session in sessions:
            if session.session_type in {SessionType.RUN_LONG, SessionType.BIKE_LONG}:
                history = _historical_sport(context, session.discipline)
                if history is None or history.longest_duration_seconds is None:
                    week_warnings.append(PlanningWarning(
                        code="LONG_SESSION_HISTORY_INSUFFICIENT",
                        context={"discipline": session.discipline},
                    ))
        represented = {item.discipline for item in sessions}
        training = [item for item in sessions if item.discipline not in {"competition", "strength"}]
        counts = {discipline: sum(item.discipline == discipline for item in training) for discipline in represented}
        total_count = max(1, len(training))
        for allocation in budget.disciplines:
            if allocation.discipline == "strength" or partial_week:
                continue
            actual_share = Decimal(counts.get(allocation.discipline, 0)) / Decimal(total_count)
            materially_low = (
                allocation.target_share is not None
                and allocation.target_share - actual_share > config.underrepresentation_tolerance
                and budget.dominant_phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC}
            )
            if allocation.target_share and (allocation.discipline not in represented or materially_low):
                week_warnings.append(PlanningWarning(code="DISCIPLINE_UNDERREPRESENTED", context={"discipline": allocation.discipline}))
        requested_strength = context.preferences.strength_sessions_per_week
        actual_strength = sum(item.discipline == "strength" for item in sessions)
        if not partial_week and requested_strength > actual_strength:
            week_warnings.append(PlanningWarning(
                code="DISCIPLINE_UNDERREPRESENTED",
                context={"discipline": "strength", "requested_sessions": requested_strength, "planned_sessions": actual_strength},
            ))
        week_warnings = tuple(sorted({(item.code, str(item.context)): item for item in week_warnings}.values(), key=lambda item: (item.code, str(item.context))))
        plan_warnings.extend(week_warnings)
        weeks.append(WeeklySessionPlan(
            iso_year=budget.iso_year, iso_week=budget.iso_week, week_start=budget.week_start, week_end=budget.week_end,
            sessions=sessions, rest_dates=rest, unavailable_dates=unavailable,
            budget_target_load=budget.target_load, planned_load=planned, load_delta=delta,
            warnings=week_warnings, quality_selection_trace=tuple(quality_trace),
        ))
    fingerprint = context_fingerprint({
        "context_fingerprint": context.fingerprint, "season_structure": season,
        "weekly_budget_fingerprint": budgets.fingerprint, "config": config,
    })
    plan = SessionPlan(
        planning_start=season.planning_start_date, planning_end=season.planning_end_date,
        timezone_name=context.training.timezone_name, weeks=tuple(weeks),
        warnings=tuple(sorted({(item.code, str(item.context)): item for item in plan_warnings}.values(), key=lambda item: (item.code, str(item.context)))),
        algorithm_version=config.algorithm_version, configuration_version=config.version,
        context_fingerprint=context.fingerprint, weekly_budget_fingerprint=budgets.fingerprint,
        fingerprint=fingerprint,
    )
    issues = validate_session_plan(plan, context, season, budgets, config)
    if issues:
        raise SessionPlanValidationError(issues)
    return plan
