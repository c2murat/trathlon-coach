from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.providers.base import InvalidPayloadError


class StravaActivityOwnershipError(InvalidPayloadError):
    """The returned summary belongs to a different external athlete."""


@dataclass(frozen=True, slots=True)
class MappedStravaActivitySummary:
    """Validated provider-owned fields for one canonical activity upsert."""

    external_activity_id: str
    sport: str
    name: str
    start_at: datetime
    timezone: str
    elapsed_time_s: int
    moving_time_s: int | None
    distance_m: float | None
    elevation_gain_m: float | None
    average_heart_rate_bpm: float | None
    max_heart_rate_bpm: float | None
    average_power_w: float | None
    max_power_w: float | None
    weighted_average_power_w: float | None
    average_speed_mps: float | None
    max_speed_mps: float | None
    average_cadence_rpm: float | None
    indoor: bool | None
    commute: bool | None
    manual: bool | None
    visibility: str | None

    def provider_fields(self) -> dict[str, object]:
        return {
            "source_summary": "strava",
            "sport": self.sport,
            "name": self.name,
            "start_at": self.start_at,
            "timezone": self.timezone,
            "elapsed_time_s": self.elapsed_time_s,
            "moving_time_s": self.moving_time_s,
            "distance_m": self.distance_m,
            "elevation_gain_m": self.elevation_gain_m,
            "average_heart_rate_bpm": self.average_heart_rate_bpm,
            "max_heart_rate_bpm": self.max_heart_rate_bpm,
            "average_power_w": self.average_power_w,
            "max_power_w": self.max_power_w,
            "weighted_average_power_w": self.weighted_average_power_w,
            "average_speed_mps": self.average_speed_mps,
            "max_speed_mps": self.max_speed_mps,
            "average_cadence_rpm": self.average_cadence_rpm,
            "indoor": self.indoor,
            "commute": self.commute,
            "manual": self.manual,
            "visibility": self.visibility,
        }


class StravaActivityMapper:
    """Map one Strava summary without HTTP, persistence, or raw retention."""

    def map_summary(
        self,
        payload: object,
        *,
        external_account_id: str,
        athlete_timezone: str,
    ) -> MappedStravaActivitySummary:
        if not isinstance(payload, Mapping):
            raise InvalidPayloadError("Strava activity summary is invalid")
        external_id = _external_id(payload.get("id"))
        _validate_owner(payload.get("athlete"), external_account_id)
        sport = _sport(payload.get("sport_type") or payload.get("type"))
        start_at = _start_at(payload.get("start_date"))
        elapsed = _required_nonnegative_int(payload.get("elapsed_time"), "elapsed time")
        name_value = payload.get("name")
        name = (
            name_value.strip()
            if isinstance(name_value, str) and name_value.strip()
            else f"{sport.title()} activity"
        )
        return MappedStravaActivitySummary(
            external_activity_id=external_id,
            sport=sport,
            name=name[:300],
            start_at=start_at,
            timezone=_timezone(payload.get("timezone"), athlete_timezone),
            elapsed_time_s=elapsed,
            moving_time_s=_optional_nonnegative_int(payload.get("moving_time")),
            distance_m=_optional_nonnegative_number(payload.get("distance")),
            elevation_gain_m=_optional_nonnegative_number(
                payload.get("total_elevation_gain")
            ),
            average_heart_rate_bpm=_optional_nonnegative_number(
                payload.get("average_heartrate")
            ),
            max_heart_rate_bpm=_optional_nonnegative_number(
                payload.get("max_heartrate")
            ),
            average_power_w=_optional_nonnegative_number(
                payload.get("average_watts")
            ),
            max_power_w=_optional_nonnegative_number(payload.get("max_watts")),
            weighted_average_power_w=_optional_nonnegative_number(
                payload.get("weighted_average_watts")
            ),
            average_speed_mps=_optional_nonnegative_number(
                payload.get("average_speed")
            ),
            max_speed_mps=_optional_nonnegative_number(payload.get("max_speed")),
            average_cadence_rpm=_optional_nonnegative_number(
                payload.get("average_cadence")
            ),
            indoor=_optional_bool(payload.get("trainer")),
            commute=_optional_bool(payload.get("commute")),
            manual=_optional_bool(payload.get("manual")),
            visibility=_visibility(payload),
        )


def _external_id(value: object) -> str:
    if isinstance(value, bool):
        raise InvalidPayloadError("Strava activity identifier is invalid")
    result = str(value).strip() if isinstance(value, (int, str)) else ""
    if not result.isdecimal() or int(result) <= 0:
        raise InvalidPayloadError("Strava activity identifier is invalid")
    return result


def _validate_owner(value: object, expected: str) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise InvalidPayloadError("Strava activity owner is invalid")
    owner = value.get("id")
    if isinstance(owner, bool) or not isinstance(owner, (int, str)):
        raise InvalidPayloadError("Strava activity owner is invalid")
    if str(owner) != expected:
        raise StravaActivityOwnershipError("Strava activity owner mismatch")


def _start_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise InvalidPayloadError("Strava activity start time is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidPayloadError("Strava activity start time is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidPayloadError("Strava activity start time is invalid")
    return parsed.astimezone(timezone.utc)


def _required_nonnegative_int(value: object, label: str) -> int:
    parsed = _optional_nonnegative_int(value)
    if parsed is None:
        raise InvalidPayloadError(f"Strava activity {label} is invalid")
    return parsed


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidPayloadError("Strava activity integer metric is invalid")
    return value


def _optional_nonnegative_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidPayloadError("Strava activity numeric metric is invalid")
    parsed = float(value)
    if parsed < 0:
        raise InvalidPayloadError("Strava activity numeric metric is invalid")
    return parsed


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise InvalidPayloadError("Strava activity flag is invalid")
    return value


def _timezone(value: object, fallback: str) -> str:
    candidates: list[str] = []
    if isinstance(value, str) and value.strip():
        candidates.append(value.strip().split()[-1])
    candidates.append(fallback)
    for candidate in candidates:
        try:
            ZoneInfo(candidate)
            return candidate
        except ZoneInfoNotFoundError:
            continue
    return "UTC"


def _visibility(payload: Mapping[object, object]) -> str | None:
    value = payload.get("visibility")
    if isinstance(value, str):
        normalized = value.strip().lower().replace(" ", "_")
        if normalized in {"everyone", "followers_only", "only_me"}:
            return normalized
        return "unknown"
    private = payload.get("private")
    if isinstance(private, bool):
        return "only_me" if private else "everyone"
    return None


def _sport(value: object) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if normalized == "swim":
        return "swimming"
    if normalized in {
        "ride",
        "virtualride",
        "ebikeride",
        "emountainbikeride",
        "mountainbikeride",
        "gravelride",
        "handcycle",
        "velomobile",
    }:
        return "cycling"
    if normalized in {"run", "virtualrun", "trailrun", "wheelchair"}:
        return "running"
    if normalized in {
        "weighttraining",
        "crossfit",
        "workout",
        "highintensityintervaltraining",
    }:
        return "strength"
    if normalized == "multisport":
        return "multisport"
    return "other"
