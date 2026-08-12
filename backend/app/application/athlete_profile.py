from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.application.athletes import normalize_athlete_display_name
from app.db.models import AthleteProfile

RECOMMENDED_PROFILE_FIELDS = ("birth_year", "sex_for_training_context", "height_m", "weight_kg")

class AthleteProfileValidationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code

class AthleteProfileUpdateEmptyError(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class AthleteProfileCompleteness:
    status: str
    missing_recommended_fields: tuple[str, ...]

def get_athlete_profile_completeness(profile: AthleteProfile) -> AthleteProfileCompleteness:
    missing = tuple(field for field in RECOMMENDED_PROFILE_FIELDS if getattr(profile, field) is None)
    return AthleteProfileCompleteness(status="contextual" if not missing else "minimal", missing_recommended_fields=missing)

def _timezone(value: str) -> str:
    if not value or len(value) > 64:
        raise AthleteProfileValidationError("athlete_profile_timezone_invalid")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise AthleteProfileValidationError("athlete_profile_timezone_invalid") from None
    return value

def _sex(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > 32:
        raise AthleteProfileValidationError("athlete_profile_sex_context_invalid")
    return normalized

def _decimal(value: Decimal | None, maximum: Decimal, code: str) -> Decimal | None:
    if value is None:
        return None
    if value <= 0 or value > maximum:
        raise AthleteProfileValidationError(code)
    return value

class AthleteProfileApplication:
    def __init__(self, session: Session, *, today=date.today) -> None:
        self._session = session
        self._today = today

    def update(self, profile: AthleteProfile, changes: dict[str, Any]) -> AthleteProfile:
        if not changes:
            raise AthleteProfileUpdateEmptyError
        normalized = dict(changes)
        if "display_name" in normalized:
            try:
                normalized["display_name"] = normalize_athlete_display_name(normalized["display_name"])
            except ValueError:
                raise AthleteProfileValidationError("athlete_profile_display_name_invalid") from None
        if "timezone" in normalized:
            normalized["timezone"] = _timezone(normalized["timezone"])
        if "birth_year" in normalized and normalized["birth_year"] is not None:
            year = normalized["birth_year"]
            if year < 1900 or year > self._today().year:
                raise AthleteProfileValidationError("athlete_profile_birth_year_invalid")
        if "sex_for_training_context" in normalized:
            normalized["sex_for_training_context"] = _sex(normalized["sex_for_training_context"])
        if "height_m" in normalized:
            normalized["height_m"] = _decimal(normalized["height_m"], Decimal("99.999"), "athlete_profile_height_invalid")
        if "weight_kg" in normalized:
            normalized["weight_kg"] = _decimal(normalized["weight_kg"], Decimal("999.999"), "athlete_profile_weight_invalid")
        for field, value in normalized.items():
            setattr(profile, field, value)
        self._session.flush()
        return profile