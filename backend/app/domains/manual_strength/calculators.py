from .models import (
    ManualStrengthLoadInput,
    ManualStrengthLoadResult,
    StrengthLoadMethod,
    StrengthLoadQuality,
    StrengthLoadUnit,
    StrengthLoadWarning,
)


ALGORITHM_VERSION = "0.7e.1"


def calculate_manual_strength_load(
    input_data: ManualStrengthLoadInput,
) -> ManualStrengthLoadResult:
    """Calculate load for a validated manual strength session."""
    duration_hours = input_data.duration_minutes / 60

    if input_data.perceived_exertion is None:
        load_value = duration_hours * 50
        method = StrengthLoadMethod.STRENGTH_DURATION
        quality = StrengthLoadQuality.LOW
        warnings = (StrengthLoadWarning.MISSING_PERCEIVED_EXERTION,)
    else:
        load_value = duration_hours * 100 * (input_data.perceived_exertion / 10)
        method = StrengthLoadMethod.STRENGTH_RPE
        quality = StrengthLoadQuality.MEDIUM
        warnings = ()

    return ManualStrengthLoadResult(
        load_value=round(load_value, 2),
        method=method,
        unit=StrengthLoadUnit.POINTS,
        quality=quality,
        body_regions=input_data.body_regions,
        duration_minutes=input_data.duration_minutes,
        perceived_exertion=input_data.perceived_exertion,
        warnings=warnings,
        algorithm_version=ALGORITHM_VERSION,
    )
