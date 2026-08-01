from dataclasses import dataclass
from enum import Enum


class InvalidManualStrengthInputError(Exception):
    """Raised when manual strength load input is invalid."""


class InvalidBodyRegionSelectionError(InvalidManualStrengthInputError):
    """Raised when the selected body regions are invalid."""


class BodyRegion(str, Enum):
    FULL_BODY = "full_body"
    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    ARMS = "arms"
    CORE = "core"
    QUADRICEPS = "quadriceps"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"


class StrengthLoadMethod(str, Enum):
    STRENGTH_RPE = "strength_rpe"
    STRENGTH_DURATION = "strength_duration"


class StrengthLoadUnit(str, Enum):
    POINTS = "points"


class StrengthLoadQuality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"


class StrengthLoadWarning(str, Enum):
    MISSING_PERCEIVED_EXERTION = "missing_perceived_exertion"


def _validate_body_regions(
    body_regions: tuple[BodyRegion, ...],
) -> tuple[BodyRegion, ...]:
    if not isinstance(body_regions, tuple):
        raise InvalidBodyRegionSelectionError("body_regions must be a tuple")
    if not body_regions:
        raise InvalidBodyRegionSelectionError("at least one body region is required")
    if any(not isinstance(region, BodyRegion) for region in body_regions):
        raise InvalidBodyRegionSelectionError("unknown body region")
    if len(set(body_regions)) != len(body_regions):
        raise InvalidBodyRegionSelectionError("body regions must not be duplicated")
    if BodyRegion.FULL_BODY in body_regions and len(body_regions) != 1:
        raise InvalidBodyRegionSelectionError(
            "full_body cannot be combined with other body regions"
        )
    selected = set(body_regions)
    return tuple(region for region in BodyRegion if region in selected)


def _validate_duration(duration_minutes: int) -> None:
    if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int):
        raise InvalidManualStrengthInputError("duration_minutes must be an integer")
    if not 1 <= duration_minutes <= 1440:
        raise InvalidManualStrengthInputError(
            "duration_minutes must be between 1 and 1440"
        )


def _validate_perceived_exertion(perceived_exertion: int | None) -> None:
    if perceived_exertion is None:
        return
    if isinstance(perceived_exertion, bool) or not isinstance(perceived_exertion, int):
        raise InvalidManualStrengthInputError(
            "perceived_exertion must be an integer"
        )
    if not 1 <= perceived_exertion <= 10:
        raise InvalidManualStrengthInputError(
            "perceived_exertion must be between 1 and 10"
        )


@dataclass(frozen=True, slots=True)
class ManualStrengthLoadInput:
    duration_minutes: int
    body_regions: tuple[BodyRegion, ...]
    perceived_exertion: int | None = None

    def __post_init__(self) -> None:
        _validate_duration(self.duration_minutes)
        _validate_perceived_exertion(self.perceived_exertion)
        canonical_regions = _validate_body_regions(self.body_regions)
        object.__setattr__(self, "body_regions", canonical_regions)


@dataclass(frozen=True, slots=True)
class ManualStrengthLoadResult:
    load_value: float
    method: StrengthLoadMethod
    unit: StrengthLoadUnit
    quality: StrengthLoadQuality
    body_regions: tuple[BodyRegion, ...]
    duration_minutes: int
    perceived_exertion: int | None
    warnings: tuple[StrengthLoadWarning, ...]
    algorithm_version: str
