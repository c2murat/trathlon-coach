"""Strava provider metadata and staged OAuth adapter."""

from app.providers.strava.oauth_client import StravaOAuthClient
from app.providers.strava.oauth_types import (
    GrantedScopes,
    StravaRevocationCredential,
    StravaAthleteIdentity,
    StravaTokenResult,
)
from app.providers.strava.provider import StravaProvider

__all__ = [
    "GrantedScopes",
    "StravaAthleteIdentity",
    "StravaOAuthClient",
    "StravaProvider",
    "StravaRevocationCredential",
    "StravaTokenResult",
]
