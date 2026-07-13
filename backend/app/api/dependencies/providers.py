from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, status

from app.core.settings import Settings, get_settings
from app.providers.base import (
    AsyncHttpTransport,
    HttpxAsyncTransport,
    InMemoryOAuthStateStore,
    OAuthStateStore,
)
from app.providers.strava import StravaOAuthClient


READ_ONLY_STRAVA_SCOPES = ("read", "activity:read_all")


@dataclass(frozen=True, slots=True)
class StravaConnectConfiguration:
    """Validated, non-secret inputs needed to begin Strava authorization."""

    client: StravaOAuthClient
    redirect_uri: str
    scopes: tuple[str, ...]
    state_ttl_seconds: int


@dataclass(frozen=True, slots=True)
class StravaCallbackConfiguration:
    """Validated inputs needed to complete Strava authorization."""

    client: StravaOAuthClient
    redirect_uri: str
    required_scopes: tuple[str, ...]


# Deliberately scoped development singleton. It is not multi-worker safe and
# must be replaced by a shared production store before deployment.
_development_state_store = InMemoryOAuthStateStore()


def get_oauth_state_store() -> OAuthStateStore:
    return _development_state_store


def get_strava_http_transport() -> AsyncHttpTransport:
    """Return the runtime HTTP transport; tests replace this dependency."""

    return HttpxAsyncTransport()


def get_strava_oauth_client(
    settings: Settings = Depends(get_settings),
    transport: AsyncHttpTransport = Depends(get_strava_http_transport),
) -> StravaOAuthClient:
    """Build a secret-safe client after validating required provider settings."""

    if (
        not settings.strava_client_id
        or settings.strava_client_secret is None
        or not settings.strava_client_secret.get_secret_value()
    ):
        raise _configuration_error("strava_configuration_missing")

    try:
        return StravaOAuthClient(
            client_id=settings.strava_client_id,
            client_secret=settings.strava_client_secret,
            authorization_url=settings.strava_authorization_url,
            token_url=settings.strava_token_url,
            revocation_url=settings.strava_revocation_url,
            transport=transport,
        )
    except ValueError:
        raise _configuration_error("strava_configuration_invalid") from None


def get_strava_connect_configuration(
    settings: Settings = Depends(get_settings),
    client: StravaOAuthClient = Depends(get_strava_oauth_client),
) -> StravaConnectConfiguration:
    """Validate connect configuration without returning or logging its secret."""

    redirect_uri, scopes = _validated_callback_inputs(settings)
    if not 60 <= settings.oauth_state_ttl_seconds <= 1800:
        raise _configuration_error("oauth_state_ttl_invalid")

    return StravaConnectConfiguration(
        client=client,
        redirect_uri=redirect_uri,
        scopes=scopes,
        state_ttl_seconds=settings.oauth_state_ttl_seconds,
    )


def get_strava_callback_configuration(
    settings: Settings = Depends(get_settings),
    client: StravaOAuthClient = Depends(get_strava_oauth_client),
) -> StravaCallbackConfiguration:
    """Validate callback configuration without exposing any secret value."""

    redirect_uri, scopes = _validated_callback_inputs(settings)
    return StravaCallbackConfiguration(
        client=client,
        redirect_uri=redirect_uri,
        required_scopes=scopes,
    )


def _validated_callback_inputs(settings: Settings) -> tuple[str, tuple[str, ...]]:
    if not settings.strava_redirect_uri or not settings.strava_scopes:
        raise _configuration_error("strava_configuration_missing")

    if not _is_valid_redirect_uri(
        settings.strava_redirect_uri, environment=settings.environment
    ):
        raise _configuration_error("strava_redirect_uri_invalid")

    scopes = tuple(
        scope.strip() for scope in settings.strava_scopes.split(",") if scope.strip()
    )
    if scopes != READ_ONLY_STRAVA_SCOPES:
        raise _configuration_error("strava_scopes_invalid")
    return settings.strava_redirect_uri, scopes


def _is_valid_redirect_uri(uri: str, *, environment: str) -> bool:
    parsed = urlsplit(uri)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return False

    if parsed.scheme == "https":
        return True

    return environment in {"development", "test"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def _configuration_error(code: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"code": code},
        headers={"Cache-Control": "no-store"},
    )
