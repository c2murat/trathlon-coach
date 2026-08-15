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
    READ_ATHLETE_HEALTH = "read_athlete_health"
    RECALCULATE_ATHLETE_DATA = "recalculate_athlete_data"
    EDIT_ATHLETE_PROFILE = "edit_athlete_profile"
    CREATE_MANUAL_STRENGTH = "create_manual_strength"
    UPDATE_MANUAL_STRENGTH = "update_manual_strength"
    DELETE_MANUAL_STRENGTH = "delete_manual_strength"
    CREATE_PERFORMANCE_PROFILE = "create_performance_profile"
    CREATE_PERFORMANCE_REFERENCE = "create_performance_reference"
    READ_STRAVA_INTEGRATION = "read_strava_integration"
    MANAGE_STRAVA_CONNECTION = "manage_strava_connection"
    CONNECT_STRAVA = "connect_strava"
    DISCONNECT_STRAVA = "disconnect_strava"
    MANAGE_ATHLETE_MEMBERSHIPS = "manage_athlete_memberships"
    RUN_STRAVA_IMPORT = "run_strava_import"
    RUN_STRAVA_ENRICHMENT = "run_strava_enrichment"
    RUN_STRAVA_EVIDENCE = "run_strava_evidence"
    DELETE_STRAVA_LOCATION_EVIDENCE = "delete_strava_location_evidence"
    READ_TRAINING_PLANNING = "read_training_planning"
    MANAGE_COMPETITION_GOALS = "manage_competition_goals"


_ALL_SPORT_CAPABILITIES = frozenset(AthleteCapability)
_ATHLETE_SELF_SERVICE_CAPABILITIES = frozenset({
    AthleteCapability.READ_ATHLETE_DATA,
    AthleteCapability.READ_ATHLETE_HEALTH,
    AthleteCapability.RECALCULATE_ATHLETE_DATA,
    AthleteCapability.EDIT_ATHLETE_PROFILE,
    AthleteCapability.CREATE_MANUAL_STRENGTH,
    AthleteCapability.UPDATE_MANUAL_STRENGTH,
    AthleteCapability.DELETE_MANUAL_STRENGTH,
    AthleteCapability.CREATE_PERFORMANCE_PROFILE,
    AthleteCapability.CREATE_PERFORMANCE_REFERENCE,
    AthleteCapability.READ_STRAVA_INTEGRATION,
    AthleteCapability.MANAGE_STRAVA_CONNECTION,
    AthleteCapability.CONNECT_STRAVA,
    AthleteCapability.DISCONNECT_STRAVA,
    AthleteCapability.RUN_STRAVA_IMPORT,
    AthleteCapability.RUN_STRAVA_ENRICHMENT,
    AthleteCapability.RUN_STRAVA_EVIDENCE,
    AthleteCapability.DELETE_STRAVA_LOCATION_EVIDENCE,
    AthleteCapability.READ_TRAINING_PLANNING,
    AthleteCapability.MANAGE_COMPETITION_GOALS,
})
_COACH_CAPABILITIES = _ALL_SPORT_CAPABILITIES - {
    AthleteCapability.DELETE_MANUAL_STRENGTH,
    AthleteCapability.EDIT_ATHLETE_PROFILE,
    AthleteCapability.READ_ATHLETE_HEALTH,
    AthleteCapability.MANAGE_STRAVA_CONNECTION,
    AthleteCapability.CONNECT_STRAVA,
    AthleteCapability.MANAGE_ATHLETE_MEMBERSHIPS,
    AthleteCapability.DELETE_STRAVA_LOCATION_EVIDENCE,
    AthleteCapability.MANAGE_COMPETITION_GOALS,
}
_ROLE_CAPABILITIES: dict[str, frozenset[AthleteCapability]] = {
    "owner": _ALL_SPORT_CAPABILITIES,
    "athlete": _ATHLETE_SELF_SERVICE_CAPABILITIES,
    "editor": _ALL_SPORT_CAPABILITIES - {AthleteCapability.MANAGE_ATHLETE_MEMBERSHIPS},
    "coach": _COACH_CAPABILITIES,
    "viewer": frozenset({
        AthleteCapability.READ_ATHLETE_DATA,
        AthleteCapability.READ_STRAVA_INTEGRATION,
        AthleteCapability.READ_TRAINING_PLANNING,
    }),
}

def capabilities_for_role(role: str) -> tuple[AthleteCapability, ...]:
    return tuple(sorted(_ROLE_CAPABILITIES.get(role, frozenset()), key=lambda item: item.value))


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
