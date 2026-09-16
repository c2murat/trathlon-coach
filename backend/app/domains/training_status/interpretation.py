"""Descriptive interpretation of persisted model values, not training advice."""
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TRAINING_STATUS_INTERPRETATION_VERSION = "0.8G.2D.1"
TREND_DAYS = 7
BROADER_CONTEXT_DAYS = 21
RECENT_DAYS = 3
MAX_CURRENT_AGE_DAYS = 1
STABLE_DELTA = Decimal("1")
FAST_FATIGUE_DELTA = Decimal("10")
BALANCED_FORM = Decimal("5")
EXTREME_FORM = Decimal("20")


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class FitnessTrend(StrEnum):
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class FatigueTrend(StrEnum):
    RISING_FAST = "RISING_FAST"
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class FormState(StrEnum):
    VERY_FRESH = "VERY_FRESH"
    FRESH = "FRESH"
    BALANCED = "BALANCED"
    LOADED = "LOADED"
    HIGHLY_LOADED = "HIGHLY_LOADED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class OverallState(StrEnum):
    RECOVERING = "RECOVERING"
    FRESH = "FRESH"
    BALANCED = "BALANCED"
    BUILDING = "BUILDING"
    LOADED = "LOADED"
    HIGH_LOAD = "HIGH_LOAD"
    REDUCED_LOAD = "REDUCED_LOAD"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class NotableTrend(StrEnum):
    FATIGUE_RISING_FASTER_THAN_FITNESS = "FATIGUE_RISING_FASTER_THAN_FITNESS"
    RECOVERY_TREND = "RECOVERY_TREND"
    BOTH_STABLE = "BOTH_STABLE"
    BOTH_FALLING = "BOTH_FALLING"
    NO_NOTABLE_TREND = "NO_NOTABLE_TREND"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


class InterpretationReason(StrEnum):
    FATIGUE_ELEVATED_OVER_21D = "FATIGUE_ELEVATED_OVER_21D"
    FITNESS_HIGHER_OVER_21D = "FITNESS_HIGHER_OVER_21D"
    FATIGUE_RECENTLY_FALLING = "FATIGUE_RECENTLY_FALLING"
    FITNESS_RECENTLY_STABLE = "FITNESS_RECENTLY_STABLE"
    RECENT_RECOVERY_TURN = "RECENT_RECOVERY_TURN"
    INSUFFICIENT_BROADER_CONTEXT = "INSUFFICIENT_BROADER_CONTEXT"
    FITNESS_RISING = "FITNESS_RISING"
    FITNESS_STABLE = "FITNESS_STABLE"
    FITNESS_FALLING = "FITNESS_FALLING"
    FATIGUE_RISING_FAST = "FATIGUE_RISING_FAST"
    FATIGUE_RISING = "FATIGUE_RISING"
    FATIGUE_STABLE = "FATIGUE_STABLE"
    FATIGUE_FALLING = "FATIGUE_FALLING"
    FORM_POSITIVE = "FORM_POSITIVE"
    FORM_NEUTRAL = "FORM_NEUTRAL"
    FORM_NEGATIVE = "FORM_NEGATIVE"
    FORM_VERY_NEGATIVE = "FORM_VERY_NEGATIVE"
    FATIGUE_RISING_FASTER_THAN_FITNESS = "FATIGUE_RISING_FASTER_THAN_FITNESS"
    RECOVERY_TREND = "RECOVERY_TREND"
    BOTH_STABLE = "BOTH_STABLE"
    BOTH_FALLING = "BOTH_FALLING"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE_STATUS = "STALE_STATUS"
    MODEL_WARMUP = "MODEL_WARMUP"


class TrainingStatusObservation(FrozenModel):
    athlete_id: UUID
    date: date
    fitness: Decimal = Field(ge=0)
    fatigue: Decimal = Field(ge=0)
    form: Decimal
    is_warmup: bool
    timezone_name: str
    training_load_algorithm_version: str
    manual_strength_algorithm_version: str
    training_status_algorithm_version: str


class TrendWindow(FrozenModel):
    days: int
    start_date: date | None
    fitness_delta: Decimal | None = None
    fatigue_delta: Decimal | None = None
    fitness_trend: FitnessTrend = FitnessTrend.INSUFFICIENT_DATA
    fatigue_trend: FatigueTrend = FatigueTrend.INSUFFICIENT_DATA


class RecentDirection(StrEnum):
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"
    MIXED = "MIXED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class RecentMovement(FrozenModel):
    delta: Decimal | None = None
    direction: RecentDirection = RecentDirection.INSUFFICIENT_DATA
    changed_direction: bool = False


class RecentStatus(FrozenModel):
    days: int = RECENT_DAYS
    start_date: date | None
    fitness: RecentMovement = RecentMovement()
    fatigue: RecentMovement = RecentMovement()
    form_delta: Decimal | None = None
    recovery_turn: bool = False


class TrainingStatusInterpretation(FrozenModel):
    athlete_id: UUID
    as_of_date: date
    interpretation_version: str = TRAINING_STATUS_INTERPRETATION_VERSION
    data_date: date | None
    window_start_date: date | None
    trend_days: int = TREND_DAYS
    short_term: TrendWindow
    broader_context: TrendWindow
    recent: RecentStatus
    fitness: Decimal | None
    fatigue: Decimal | None
    form: Decimal | None
    fitness_delta: Decimal | None
    fatigue_delta: Decimal | None
    fitness_trend: FitnessTrend
    fatigue_trend: FatigueTrend
    form_state: FormState
    overall_state: OverallState
    headline_key: OverallState
    summary_key: OverallState
    fitness_explanation_key: FitnessTrend
    fatigue_explanation_key: FatigueTrend
    form_explanation_key: FormState
    notable_trend_key: NotableTrend
    reason_codes: tuple[InterpretationReason, ...]


def _trend(delta: Decimal) -> FitnessTrend:
    return FitnessTrend.RISING if delta > STABLE_DELTA else FitnessTrend.FALLING if delta < -STABLE_DELTA else FitnessTrend.STABLE


def _form(value: Decimal) -> FormState:
    if value <= -EXTREME_FORM:
        return FormState.HIGHLY_LOADED
    if value < -BALANCED_FORM:
        return FormState.LOADED
    if value <= BALANCED_FORM:
        return FormState.BALANCED
    return FormState.VERY_FRESH if value >= EXTREME_FORM else FormState.FRESH


def _window(rows, days, fresh):
    start = rows[-1].date - timedelta(days=days) if rows else None
    selected = [row for row in rows if row.date >= start] if start else []
    if not fresh or len(selected) != days + 1:
        return TrendWindow(days=days, start_date=start)
    fitness = selected[-1].fitness - selected[0].fitness
    fatigue = selected[-1].fatigue - selected[0].fatigue
    return TrendWindow(days=days, start_date=start, fitness_delta=fitness, fatigue_delta=fatigue,
        fitness_trend=_trend(fitness), fatigue_trend=FatigueTrend.RISING_FAST
        if fatigue >= FAST_FATIGUE_DELTA else FatigueTrend(_trend(fatigue).value))


def _recent_movement(rows, metric):
    # Seven-day history is complete here. Compare its first four days with its last three.
    values = [getattr(row, metric) for row in rows[-(RECENT_DAYS+1):]]
    delta = values[-1] - values[0]
    if max(values)-min(values) <= STABLE_DELTA:
        direction = RecentDirection.STABLE
    elif delta > STABLE_DELTA and all(a <= b for a, b in zip(values, values[1:])):
        direction = RecentDirection.RISING
    elif delta < -STABLE_DELTA and all(a >= b for a, b in zip(values, values[1:])):
        direction = RecentDirection.FALLING
    else:
        direction = RecentDirection.MIXED
    prior = _trend(values[0] - getattr(rows[0], metric))
    changed = (direction == RecentDirection.FALLING and prior == FitnessTrend.RISING
        or direction == RecentDirection.RISING and prior == FitnessTrend.FALLING)
    return RecentMovement(delta=delta, direction=direction, changed_direction=changed)


class TrainingStatusInterpreter:
    def interpret(self, *, athlete_id: UUID, as_of_date: date,
                  observations: tuple[TrainingStatusObservation, ...]) -> TrainingStatusInterpretation:
        if any(item.athlete_id != athlete_id for item in observations):
            raise ValueError("training status athlete mismatch")
        rows = sorted((item for item in observations if item.date <= as_of_date), key=lambda item: item.date)
        if len({item.date for item in rows}) != len(rows):
            raise ValueError("duplicate training status date")
        if len({(item.timezone_name, item.training_load_algorithm_version,
                 item.manual_strength_algorithm_version, item.training_status_algorithm_version) for item in rows}) > 1:
            raise ValueError("mixed training status configuration")
        current = rows[-1] if rows else None
        start = current.date - timedelta(days=TREND_DAYS) if current else None
        recent = [item for item in rows if item.date >= start] if start else []
        sufficient = current is not None and (as_of_date-current.date).days <= MAX_CURRENT_AGE_DAYS and len(recent) == TREND_DAYS+1
        fresh = current is not None and (as_of_date-current.date).days <= MAX_CURRENT_AGE_DAYS
        short_term = _window(rows, TREND_DAYS, fresh)
        broader_context = _window(rows, BROADER_CONTEXT_DAYS, fresh)
        recent_status = RecentStatus(start_date=current.date-timedelta(days=RECENT_DAYS) if current else None)
        if sufficient:
            recent_fitness = _recent_movement(recent, "fitness")
            recent_fatigue = _recent_movement(recent, "fatigue")
            form_delta = current.form-recent[-(RECENT_DAYS+1)].form
            recent_status = RecentStatus(start_date=recent_status.start_date,
                fitness=recent_fitness, fatigue=recent_fatigue, form_delta=form_delta,
                recovery_turn=recent_fatigue.changed_direction
                and recent_fatigue.direction == RecentDirection.FALLING and form_delta > STABLE_DELTA)
        fitness_trend = FitnessTrend.INSUFFICIENT_DATA
        fatigue_trend = FatigueTrend.INSUFFICIENT_DATA
        form_state = FormState.INSUFFICIENT_DATA
        overall = OverallState.INSUFFICIENT_DATA
        notable = NotableTrend.INSUFFICIENT_HISTORY
        fitness_delta = fatigue_delta = None
        reasons = set()
        if broader_context.fitness_trend == FitnessTrend.INSUFFICIENT_DATA:
            reasons.add(InterpretationReason.INSUFFICIENT_BROADER_CONTEXT)
        if broader_context.fitness_trend == FitnessTrend.RISING:
            reasons.add(InterpretationReason.FITNESS_HIGHER_OVER_21D)
        if broader_context.fatigue_trend in (FatigueTrend.RISING, FatigueTrend.RISING_FAST):
            reasons.add(InterpretationReason.FATIGUE_ELEVATED_OVER_21D)
        if recent_status.fatigue.direction == RecentDirection.FALLING:
            reasons.add(InterpretationReason.FATIGUE_RECENTLY_FALLING)
        if recent_status.fitness.direction == RecentDirection.STABLE:
            reasons.add(InterpretationReason.FITNESS_RECENTLY_STABLE)
        if recent_status.recovery_turn:
            reasons.add(InterpretationReason.RECENT_RECOVERY_TURN)
        if current and current.is_warmup:
            reasons.add(InterpretationReason.MODEL_WARMUP)
        if not sufficient:
            reasons.add(InterpretationReason.INSUFFICIENT_HISTORY)
            if current and (as_of_date-current.date).days > MAX_CURRENT_AGE_DAYS:
                reasons.add(InterpretationReason.STALE_STATUS)
        else:
            fitness_delta = short_term.fitness_delta
            fatigue_delta = short_term.fatigue_delta
            fitness_trend = short_term.fitness_trend
            fatigue_trend = short_term.fatigue_trend
            form_state = _form(current.form)
            reasons.update((InterpretationReason("FITNESS_"+fitness_trend.value),
                            InterpretationReason("FATIGUE_"+fatigue_trend.value)))
            reasons.add(InterpretationReason.FORM_VERY_NEGATIVE if form_state == FormState.HIGHLY_LOADED
                else InterpretationReason.FORM_NEGATIVE if form_state == FormState.LOADED
                else InterpretationReason.FORM_NEUTRAL if form_state == FormState.BALANCED
                else InterpretationReason.FORM_POSITIVE)
            notable = NotableTrend.NO_NOTABLE_TREND
            if fatigue_delta > STABLE_DELTA and fatigue_delta-fitness_delta > STABLE_DELTA:
                notable = NotableTrend.FATIGUE_RISING_FASTER_THAN_FITNESS
            elif fatigue_trend == FatigueTrend.FALLING and fitness_trend in (FitnessTrend.STABLE, FitnessTrend.RISING):
                notable = NotableTrend.RECOVERY_TREND
            elif fitness_trend == FitnessTrend.STABLE and fatigue_trend == FatigueTrend.STABLE:
                notable = NotableTrend.BOTH_STABLE
            elif fitness_trend == FitnessTrend.FALLING and fatigue_trend == FatigueTrend.FALLING:
                notable = NotableTrend.BOTH_FALLING
            if notable != NotableTrend.NO_NOTABLE_TREND:
                reasons.add(InterpretationReason(notable.value))
            if form_state == FormState.HIGHLY_LOADED:
                overall = OverallState.HIGH_LOAD
            elif form_state == FormState.LOADED:
                overall = OverallState.LOADED
            elif notable == NotableTrend.BOTH_FALLING:
                overall = OverallState.REDUCED_LOAD
            elif notable == NotableTrend.RECOVERY_TREND:
                overall = OverallState.RECOVERING
            elif form_state in (FormState.FRESH, FormState.VERY_FRESH):
                overall = OverallState.FRESH
            elif fitness_trend == FitnessTrend.RISING:
                overall = OverallState.BUILDING
            else:
                overall = OverallState.BALANCED
        return TrainingStatusInterpretation(athlete_id=athlete_id, as_of_date=as_of_date,
            short_term=short_term, broader_context=broader_context, recent=recent_status,
            data_date=current.date if current else None, window_start_date=start,
            fitness=current.fitness if current else None, fatigue=current.fatigue if current else None,
            form=current.form if current else None, fitness_delta=fitness_delta, fatigue_delta=fatigue_delta,
            fitness_trend=fitness_trend, fatigue_trend=fatigue_trend, form_state=form_state,
            overall_state=overall, headline_key=overall, summary_key=overall,
            fitness_explanation_key=fitness_trend, fatigue_explanation_key=fatigue_trend,
            form_explanation_key=form_state, notable_trend_key=notable, reason_codes=tuple(sorted(reasons)))
