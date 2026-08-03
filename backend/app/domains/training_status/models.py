from dataclasses import dataclass
from datetime import date
from math import isfinite


class InvalidTrainingStatusInputError(Exception):
    """Raised when a training-status input value is invalid."""


class DuplicateTrainingStatusDateError(Exception):
    """Raised when more than one load entry exists for the same date."""


class InvalidTrainingStatusRangeError(Exception):
    """Raised when the requested training-status date range is invalid."""


def _validate_finite_non_negative(value: object, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
    ):
        raise InvalidTrainingStatusInputError(
            f"{field_name} must be a finite non-negative number"
        )


@dataclass(frozen=True, slots=True)
class DailyTrainingLoadInput:
    date: date
    total_load: float

    def __post_init__(self) -> None:
        if type(self.date) is not date:
            raise InvalidTrainingStatusInputError("date must be a date")
        _validate_finite_non_negative(self.total_load, "total_load")


@dataclass(frozen=True, slots=True)
class DailyTrainingStatus:
    date: date
    total_load: float
    fitness: float
    fatigue: float
    form: float
    is_warmup: bool
    algorithm_version: str


@dataclass(frozen=True, slots=True)
class TrainingStatusSeries:
    start_date: date
    end_date: date
    days: tuple[DailyTrainingStatus, ...]
    initial_fitness: float
    initial_fatigue: float
    elapsed_history_days: int
    algorithm_version: str
