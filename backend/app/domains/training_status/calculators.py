from datetime import date, timedelta
from math import exp

from .models import (
    DailyTrainingLoadInput,
    DailyTrainingStatus,
    DuplicateTrainingStatusDateError,
    InvalidTrainingStatusInputError,
    InvalidTrainingStatusRangeError,
    TrainingStatusSeries,
    _validate_finite_non_negative,
)


FITNESS_TIME_CONSTANT_DAYS = 42
FATIGUE_TIME_CONSTANT_DAYS = 7
WARMUP_DAYS = 84
ALGORITHM_VERSION = "0.7f.1"


def _validate_range(
    entries: tuple[DailyTrainingLoadInput, ...],
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    if (start_date is None) != (end_date is None):
        raise InvalidTrainingStatusRangeError(
            "start_date and end_date must be provided together"
        )
    if start_date is None:
        if not entries:
            raise InvalidTrainingStatusRangeError(
                "entries or an explicit date range are required"
            )
        return min(entry.date for entry in entries), max(entry.date for entry in entries)
    if type(start_date) is not date or type(end_date) is not date:
        raise InvalidTrainingStatusRangeError("range limits must be dates")
    if end_date < start_date:
        raise InvalidTrainingStatusRangeError("end_date must not precede start_date")
    if any(entry.date < start_date or entry.date > end_date for entry in entries):
        raise InvalidTrainingStatusRangeError("entry falls outside the explicit range")
    return start_date, end_date


def _validate_entries(
    entries: tuple[DailyTrainingLoadInput, ...],
) -> dict[date, float]:
    if not isinstance(entries, tuple):
        raise InvalidTrainingStatusInputError("entries must be a tuple")
    loads_by_date: dict[date, float] = {}
    for entry in entries:
        if not isinstance(entry, DailyTrainingLoadInput):
            raise InvalidTrainingStatusInputError(
                "entries must contain DailyTrainingLoadInput values"
            )
        if entry.date in loads_by_date:
            raise DuplicateTrainingStatusDateError(
                f"duplicate training-status date: {entry.date.isoformat()}"
            )
        loads_by_date[entry.date] = entry.total_load
    return loads_by_date


def _validate_initial_state(
    initial_fitness: float,
    initial_fatigue: float,
    elapsed_history_days: int,
) -> None:
    _validate_finite_non_negative(initial_fitness, "initial_fitness")
    _validate_finite_non_negative(initial_fatigue, "initial_fatigue")
    if (
        isinstance(elapsed_history_days, bool)
        or not isinstance(elapsed_history_days, int)
        or elapsed_history_days < 0
    ):
        raise InvalidTrainingStatusInputError(
            "elapsed_history_days must be a non-negative integer"
        )


def calculate_training_status_series(
    entries: tuple[DailyTrainingLoadInput, ...],
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    initial_fitness: float = 0.0,
    initial_fatigue: float = 0.0,
    elapsed_history_days: int = 0,
) -> TrainingStatusSeries:
    """Calculate a complete daily fitness, fatigue and form time series."""
    loads_by_date = _validate_entries(entries)
    range_start, range_end = _validate_range(entries, start_date, end_date)
    _validate_initial_state(
        initial_fitness,
        initial_fatigue,
        elapsed_history_days,
    )

    fitness_factor = 1 - exp(-1 / FITNESS_TIME_CONSTANT_DAYS)
    fatigue_factor = 1 - exp(-1 / FATIGUE_TIME_CONSTANT_DAYS)
    current_fitness = initial_fitness
    current_fatigue = initial_fatigue
    day_count = (range_end - range_start).days + 1
    results: list[DailyTrainingStatus] = []

    for offset in range(day_count):
        current_date = range_start + timedelta(days=offset)
        total_load = loads_by_date.get(current_date, 0.0)
        current_fitness += (total_load - current_fitness) * fitness_factor
        current_fatigue += (total_load - current_fatigue) * fatigue_factor
        current_form = current_fitness - current_fatigue
        history_day_number = elapsed_history_days + offset + 1
        results.append(
            DailyTrainingStatus(
                date=current_date,
                total_load=round(total_load, 2),
                fitness=round(current_fitness, 2),
                fatigue=round(current_fatigue, 2),
                form=round(current_form, 2),
                is_warmup=history_day_number <= WARMUP_DAYS,
                algorithm_version=ALGORITHM_VERSION,
            )
        )

    return TrainingStatusSeries(
        start_date=range_start,
        end_date=range_end,
        days=tuple(results),
        initial_fitness=initial_fitness,
        initial_fatigue=initial_fatigue,
        elapsed_history_days=elapsed_history_days,
        algorithm_version=ALGORITHM_VERSION,
    )
