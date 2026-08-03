from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from math import exp, inf, nan

import pytest

from app.domains.training_status import (
    ALGORITHM_VERSION,
    FATIGUE_TIME_CONSTANT_DAYS,
    FITNESS_TIME_CONSTANT_DAYS,
    WARMUP_DAYS,
    DailyTrainingLoadInput,
    DuplicateTrainingStatusDateError,
    InvalidTrainingStatusInputError,
    InvalidTrainingStatusRangeError,
    calculate_training_status_series,
)


DAY = date(2026, 1, 1)


def entry(offset: int, load: float) -> DailyTrainingLoadInput:
    return DailyTrainingLoadInput(DAY + timedelta(days=offset), load)


def calculate(entries: tuple[DailyTrainingLoadInput, ...], **kwargs):
    return calculate_training_status_series(entries, **kwargs)


def test_one_day_with_load() -> None:
    result = calculate((entry(0, 100),))
    assert len(result.days) == 1
    assert result.days[0].fitness == round(100 * (1 - exp(-1 / 42)), 2)


def test_several_consecutive_days() -> None:
    result = calculate((entry(0, 40), entry(1, 50), entry(2, 60)))
    assert [day.total_load for day in result.days] == [40, 50, 60]


def test_missing_intermediate_days_are_filled() -> None:
    result = calculate((entry(0, 30), entry(2, 50)))
    assert [day.total_load for day in result.days] == [30, 0, 50]


def test_explicit_rest_only_series() -> None:
    result = calculate((), start_date=DAY, end_date=DAY + timedelta(days=2))
    assert len(result.days) == 3
    assert all(day.total_load == 0 for day in result.days)


def test_rest_day_reduces_fitness() -> None:
    result = calculate((entry(0, 100),), end_date=DAY + timedelta(days=1), start_date=DAY)
    assert result.days[1].fitness < result.days[0].fitness


def test_rest_day_reduces_fatigue() -> None:
    result = calculate((entry(0, 100),), end_date=DAY + timedelta(days=1), start_date=DAY)
    assert result.days[1].fatigue < result.days[0].fatigue


def test_fatigue_reacts_faster_than_fitness() -> None:
    day = calculate((entry(0, 100),)).days[0]
    assert day.fatigue > day.fitness


def test_high_load_initially_produces_negative_form() -> None:
    assert calculate((entry(0, 500),)).days[0].form < 0


def test_rest_days_progressively_recover_form() -> None:
    result = calculate((entry(0, 500),), start_date=DAY, end_date=DAY + timedelta(days=3))
    forms = [day.form for day in result.days]
    assert forms[0] < forms[1] < forms[2] < forms[3]


def test_input_order_does_not_change_result() -> None:
    ordered = (entry(0, 20), entry(1, 40), entry(2, 10))
    assert calculate(ordered) == calculate(tuple(reversed(ordered)))


def test_duplicate_date_is_rejected() -> None:
    with pytest.raises(DuplicateTrainingStatusDateError):
        calculate((entry(0, 10), entry(0, 20)))


def test_negative_load_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        entry(0, -1)


def test_boolean_load_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        entry(0, True)


def test_nan_load_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        entry(0, nan)


def test_infinite_load_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        entry(0, inf)


def test_reversed_range_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusRangeError):
        calculate((), start_date=DAY + timedelta(days=1), end_date=DAY)


def test_start_date_without_end_date_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusRangeError):
        calculate((), start_date=DAY)


def test_end_date_without_start_date_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusRangeError):
        calculate((), end_date=DAY)


def test_entry_outside_explicit_range_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusRangeError):
        calculate((entry(2, 10),), start_date=DAY, end_date=DAY + timedelta(days=1))


def test_explicit_empty_range_generates_zero_days() -> None:
    result = calculate((), start_date=DAY, end_date=DAY + timedelta(days=1))
    assert tuple(day.total_load for day in result.days) == (0, 0)


def test_no_entries_without_range_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusRangeError):
        calculate(())


def test_custom_initial_seeds_are_applied() -> None:
    result = calculate((entry(0, 0),), initial_fitness=50, initial_fatigue=30)
    assert result.initial_fitness == 50
    assert result.initial_fatigue == 30
    assert result.days[0].fitness == round(50 + (0 - 50) * (1 - exp(-1 / 42)), 2)


def test_negative_seed_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        calculate((entry(0, 0),), initial_fitness=-1)


def test_boolean_seed_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        calculate((entry(0, 0),), initial_fatigue=True)


def test_nan_seed_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        calculate((entry(0, 0),), initial_fitness=nan)


def test_infinite_seed_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        calculate((entry(0, 0),), initial_fatigue=inf)


def test_negative_elapsed_history_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        calculate((entry(0, 0),), elapsed_history_days=-1)


def test_boolean_elapsed_history_is_rejected() -> None:
    with pytest.raises(InvalidTrainingStatusInputError):
        calculate((entry(0, 0),), elapsed_history_days=True)


def test_first_84_days_are_warmup() -> None:
    result = calculate((), start_date=DAY, end_date=DAY + timedelta(days=83))
    assert len(result.days) == WARMUP_DAYS
    assert all(day.is_warmup for day in result.days)


def test_day_85_is_not_warmup() -> None:
    result = calculate((), start_date=DAY, end_date=DAY + timedelta(days=84))
    assert result.days[83].is_warmup is True
    assert result.days[84].is_warmup is False


def test_elapsed_history_continues_warmup_count() -> None:
    result = calculate((entry(0, 0), entry(1, 0)), elapsed_history_days=83)
    assert [day.is_warmup for day in result.days] == [True, False]


def test_internal_values_are_not_rounded_between_days() -> None:
    factor = 1 - exp(-1 / 42)
    internal_day_one = 1 * factor
    internal_day_two = internal_day_one + (1 - internal_day_one) * factor
    result = calculate((entry(0, 1), entry(1, 1)))
    assert result.days[1].fitness == round(internal_day_two, 2)
    rounded_day_two = result.days[0].fitness + (1 - result.days[0].fitness) * factor
    assert result.days[1].fitness != round(rounded_day_two, 2)


def test_public_values_are_rounded_to_two_decimals() -> None:
    day = calculate((entry(0, 12.3456),)).days[0]
    for value in (day.total_load, day.fitness, day.fatigue, day.form):
        assert value == round(value, 2)
    assert day.total_load == 12.35


def test_form_uses_same_day_internal_fitness_minus_fatigue() -> None:
    fitness = 100 * (1 - exp(-1 / 42))
    fatigue = 100 * (1 - exp(-1 / 7))
    assert calculate((entry(0, 100),)).days[0].form == round(fitness - fatigue, 2)


def test_calculation_does_not_mutate_input() -> None:
    entries = (entry(1, 20), entry(0, 10))
    original = tuple(entries)
    calculate(entries)
    assert entries == original


def test_models_are_immutable() -> None:
    input_value = entry(0, 10)
    status = calculate((input_value,)).days[0]
    with pytest.raises(FrozenInstanceError):
        input_value.total_load = 20
    with pytest.raises(FrozenInstanceError):
        status.fitness = 20


def test_public_collections_are_tuples() -> None:
    result = calculate((entry(0, 10),))
    assert isinstance(result.days, tuple)


def test_result_is_deterministic() -> None:
    entries = (entry(0, 10), entry(2, 40))
    assert calculate(entries) == calculate(entries)


def test_algorithm_version_is_exact() -> None:
    result = calculate((entry(0, 10),))
    assert ALGORITHM_VERSION == "0.7f.1"
    assert result.algorithm_version == ALGORITHM_VERSION
    assert all(day.algorithm_version == ALGORITHM_VERSION for day in result.days)


def test_time_constants_are_exact() -> None:
    assert FITNESS_TIME_CONSTANT_DAYS == 42
    assert FATIGUE_TIME_CONSTANT_DAYS == 7
