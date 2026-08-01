from dataclasses import FrozenInstanceError

import pytest

from app.domains.manual_strength import (
    ALGORITHM_VERSION,
    BodyRegion,
    InvalidBodyRegionSelectionError,
    InvalidManualStrengthInputError,
    ManualStrengthLoadInput,
    StrengthLoadMethod,
    StrengthLoadQuality,
    StrengthLoadUnit,
    StrengthLoadWarning,
    calculate_manual_strength_load,
)


def make_input(
    duration: int = 60,
    regions: tuple[BodyRegion, ...] = (BodyRegion.FULL_BODY,),
    rpe: int | None = None,
) -> ManualStrengthLoadInput:
    return ManualStrengthLoadInput(duration, regions, rpe)


@pytest.mark.parametrize(("duration", "expected"), [(60, 50.0), (30, 25.0)])
def test_duration_load(duration: int, expected: float) -> None:
    assert calculate_manual_strength_load(make_input(duration)).load_value == expected


@pytest.mark.parametrize(
    ("duration", "rpe", "expected"), [(60, 8, 80.0), (45, 6, 45.0)]
)
def test_rpe_load(duration: int, rpe: int, expected: float) -> None:
    result = calculate_manual_strength_load(make_input(duration, rpe=rpe))
    assert result.load_value == expected


def test_one_valid_region() -> None:
    assert make_input(regions=(BodyRegion.CHEST,)).body_regions == (BodyRegion.CHEST,)


def test_multiple_regions_are_valid_and_canonical() -> None:
    data = make_input(regions=(BodyRegion.CALVES, BodyRegion.BACK, BodyRegion.ARMS))
    assert data.body_regions == (BodyRegion.BACK, BodyRegion.ARMS, BodyRegion.CALVES)


def test_region_order_does_not_change_result() -> None:
    first = make_input(regions=(BodyRegion.GLUTES, BodyRegion.CHEST), rpe=7)
    second = make_input(regions=(BodyRegion.CHEST, BodyRegion.GLUTES), rpe=7)
    assert calculate_manual_strength_load(first) == calculate_manual_strength_load(second)


@pytest.mark.parametrize(
    "regions",
    [
        (),
        (BodyRegion.CHEST, BodyRegion.CHEST),
        (BodyRegion.FULL_BODY, BodyRegion.CHEST),
        ("unknown",),
    ],
)
def test_invalid_body_region_selection(regions: tuple[object, ...]) -> None:
    with pytest.raises(InvalidBodyRegionSelectionError):
        make_input(regions=regions)  # type: ignore[arg-type]


@pytest.mark.parametrize("duration", [0, -1, 1441, True, 60.0])
def test_invalid_duration(duration: object) -> None:
    with pytest.raises(InvalidManualStrengthInputError):
        make_input(duration=duration)  # type: ignore[arg-type]


@pytest.mark.parametrize("rpe", [1, 10])
def test_rpe_boundaries_are_valid(rpe: int) -> None:
    assert make_input(rpe=rpe).perceived_exertion == rpe


@pytest.mark.parametrize("rpe", [0, 11, True, 5.0])
def test_invalid_rpe(rpe: object) -> None:
    with pytest.raises(InvalidManualStrengthInputError):
        make_input(rpe=rpe)  # type: ignore[arg-type]


def test_result_without_rpe_metadata() -> None:
    result = calculate_manual_strength_load(make_input())
    assert result.method is StrengthLoadMethod.STRENGTH_DURATION
    assert result.quality is StrengthLoadQuality.LOW
    assert result.warnings == (StrengthLoadWarning.MISSING_PERCEIVED_EXERTION,)


def test_result_with_rpe_metadata() -> None:
    result = calculate_manual_strength_load(make_input(rpe=8))
    assert result.method is StrengthLoadMethod.STRENGTH_RPE
    assert result.quality is StrengthLoadQuality.MEDIUM
    assert result.warnings == ()


def test_result_unit_and_algorithm_version() -> None:
    result = calculate_manual_strength_load(make_input())
    assert result.unit is StrengthLoadUnit.POINTS
    assert result.algorithm_version == ALGORITHM_VERSION == "0.7e.1"


def test_public_load_is_rounded_to_two_decimals() -> None:
    assert calculate_manual_strength_load(make_input(1, rpe=1)).load_value == 0.17


def test_input_is_immutable() -> None:
    data = make_input()
    with pytest.raises(FrozenInstanceError):
        data.duration_minutes = 30  # type: ignore[misc]


def test_result_is_immutable() -> None:
    result = calculate_manual_strength_load(make_input())
    with pytest.raises(FrozenInstanceError):
        result.load_value = 0  # type: ignore[misc]


def test_calculator_does_not_modify_input() -> None:
    data = make_input(regions=(BodyRegion.CHEST, BodyRegion.BACK), rpe=8)
    before = (data.duration_minutes, data.body_regions, data.perceived_exertion)
    calculate_manual_strength_load(data)
    assert (data.duration_minutes, data.body_regions, data.perceived_exertion) == before


def test_multiple_regions_do_not_multiply_load() -> None:
    single = calculate_manual_strength_load(
        make_input(regions=(BodyRegion.QUADRICEPS,), rpe=8)
    )
    multiple = calculate_manual_strength_load(
        make_input(regions=(BodyRegion.QUADRICEPS, BodyRegion.GLUTES), rpe=8)
    )
    assert multiple.load_value == single.load_value
