from __future__ import annotations

from enum import Enum
from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status

from app.api.dependencies.current_athlete import (
    CurrentAthleteContext,
    get_current_athlete,
)


class AthleteCapability(str, Enum):
    READ_ATHLETE_DATA = "read_athlete_data"
    RECALCULATE_ATHLETE_DATA = "recalculate_athlete_data"
    CREATE_MANUAL_STRENGTH = "create_manual_strength"
    UPDATE_MANUAL_STRENGTH = "update_manual_strength"
    DELETE_MANUAL_STRENGTH = "delete_manual_strength"
    CREATE_PERFORMANCE_PROFILE = "create_performance_profile"
    CREATE_PERFORMANCE_REFERENCE = "create_performance_reference"
    READ_STRAVA_INTEGRATION = "read_strava_integration"
    MANAGE_STRAVA_CONNECTION = "manage_strava_connection"
    RUN_STRAVA_IMPORT = "run_strava_import"
    RUN_STRAVA_ENRICHMENT = "run_strava_enrichment"
    RUN_STRAVA_EVIDENCE = "run_strava_evidence"
    DELETE_STRAVA_LOCATION_EVIDENCE = "delete_strava_location_evidence"


_ALL_SPORT_CAPABILITIES = frozenset(AthleteCapability)
_COACH_CAPABILITIES = _ALL_SPORT_CAPABILITIES - {
    AthleteCapability.DELETE_MANUAL_STRENGTH,
    AthleteCapability.MANAGE_STRAVA_CONNECTION,
    AthleteCapability.DELETE_STRAVA_LOCATION_EVIDENCE,
}
_ROLE_CAPABILITIES: dict[str, frozenset[AthleteCapability]] = {
    "owner": _ALL_SPORT_CAPABILITIES,
    "editor": _ALL_SPORT_CAPABILITIES,
    "coach": _COACH_CAPABILITIES,
    "viewer": frozenset({
        AthleteCapability.READ_ATHLETE_DATA,
        AthleteCapability.READ_STRAVA_INTEGRATION,
    }),
}


def athlete_has_capability(
    current_athlete: CurrentAthleteContext,
    capability: AthleteCapability,
) -> bool:
    return capability in _ROLE_CAPABILITIES.get(current_athlete.role, frozenset())


def require_athlete_capability(
    capability: AthleteCapability,
) -> Callable[..., CurrentAthleteContext]:
    def dependency(
        current_athlete: Annotated[
            CurrentAthleteContext,
            Depends(get_current_athlete),
        ],
    ) -> CurrentAthleteContext:
        if not athlete_has_capability(current_athlete, capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "athlete_permission_denied",
                    "message": (
                        "The selected athlete membership does not permit "
                        "this operation."
                    ),
                },
            )
        return current_athlete

    return dependency
