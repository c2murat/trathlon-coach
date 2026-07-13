from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status

from app.core.settings import Settings, get_settings
from app.db.session import SessionLocal
from app.integrations.strava.activity_import import StravaSummaryImportManager
from app.integrations.strava.token_service import StravaTokenService
from app.providers.base import (
    AsyncHttpTransport,
    HttpxAsyncTransport,
    OAuthStateStore,
)
from app.providers.strava import StravaOAuthClient
from app.providers.strava.activity_client import (
    HttpxStravaActivityTransport,
    StravaActivityClient,
)


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


def get_oauth_state_store(request: Request) -> OAuthStateStore:
    """Return the store owned by the exact FastAPI application serving the request."""

    store = getattr(request.app.state, "oauth_state_store", None)
    if not isinstance(store, OAuthStateStore):
        raise _configuration_error("oauth_state_store_unavailable")
    return store


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


def get_strava_import_manager(
    request: Request,
    settings: Settings = Depends(get_settings),
    oauth_client: StravaOAuthClient = Depends(get_strava_oauth_client),
) -> StravaSummaryImportManager:
    """Return one app-owned summary importer with mockable provider boundaries."""

    manager = getattr(request.app.state, "strava_import_manager", None)
    if isinstance(manager, StravaSummaryImportManager):
        return manager
    try:
        activity_client = StravaActivityClient(
            api_base_url=settings.strava_api_base_url,
            transport=HttpxStravaActivityTransport(),
        )
        manager = StravaSummaryImportManager(
            session_factory=SessionLocal,
            activity_client=activity_client,
            token_service=StravaTokenService(
                session_factory=SessionLocal,
                oauth_client=oauth_client,
            ),
            page_size=settings.strava_import_page_size,
            retry_seconds=settings.strava_import_retry_seconds,
            incremental_overlap_seconds=settings.strava_import_overlap_seconds,
        )
    except ValueError:
        raise _configuration_error("strava_import_configuration_invalid") from None
    request.app.state.strava_import_manager = manager
    return manager


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
