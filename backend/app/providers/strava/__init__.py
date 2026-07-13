"""Strava provider metadata and staged OAuth adapter."""

from app.providers.strava.oauth_client import StravaOAuthClient
from app.providers.strava.oauth_types import (
    GrantedScopes,
    StravaRefreshCredential,
    StravaRefreshResult,
    StravaRevocationCredential,
    StravaAthleteIdentity,
    StravaTokenResult,
)
from app.providers.strava.provider import StravaProvider
from app.providers.strava.activity_client import (
    HttpxStravaActivityTransport,
    StravaActivityClient,
    StravaActivityPage,
    StravaActivityRateLimitError,
)
from app.providers.strava.activity_mapper import StravaActivityMapper

__all__ = [
    "GrantedScopes",
    "HttpxStravaActivityTransport",
    "StravaActivityClient",
    "StravaActivityMapper",
    "StravaActivityPage",
    "StravaActivityRateLimitError",
    "StravaAthleteIdentity",
    "StravaOAuthClient",
    "StravaProvider",
    "StravaRefreshCredential",
    "StravaRefreshResult",
    "StravaRevocationCredential",
    "StravaTokenResult",
]
