from dataclasses import asdict
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.dependencies.providers import (
    StravaCallbackConfiguration,
    StravaConnectConfiguration,
    get_oauth_state_store,
    get_strava_http_transport,
    get_strava_oauth_client,
    get_strava_callback_configuration,
    get_strava_connect_configuration,
)
from app.db.session import get_db_session
from app.core.settings import Settings, get_settings
from app.integrations.strava.connection_service import (
    DisconnectTarget,
    StravaConnectionService,
)
from app.integrations.strava.oauth_callback import (
    LocalAthleteMissingError,
    OAuthOwnershipConflictError,
    StravaOAuthPersistenceService,
)
from app.providers.base import (
    OAuthState,
    OAuthStateError,
    OAuthStateExpiredError,
    OAuthStateReusedError,
    OAuthStateStore,
    OAuthStateUserMismatchError,
    AsyncHttpTransport,
    AuthenticationError,
    ProviderError,
    TemporaryProviderError,
    generate_oauth_state,
    utc_now,
)
from app.providers.strava import GrantedScopes, StravaRevocationCredential

router = APIRouter(prefix="/integrations/strava", tags=["integrations"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("/status")
def strava_status(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> JSONResponse:
    """Return only stored, secret-free connection state for the current user."""

    try:
        connection = StravaConnectionService(session).status_for_user(current_user.id)
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_status_unavailable"
        ) from None
    return JSONResponse(
        jsonable_encoder(asdict(connection)),
        status_code=status.HTTP_200_OK,
        headers=NO_STORE_HEADERS,
    )


@router.delete("/disconnect")
async def disconnect_strava(
    current_user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    transport: AsyncHttpTransport = Depends(get_strava_http_transport),
    session: Session = Depends(get_db_session),
) -> JSONResponse:
    """Revoke and remove only the current user's Strava authorization."""

    service = StravaConnectionService(session)
    try:
        target = service.begin_disconnect(current_user.id)
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_disconnect_failed"
        ) from None
    if target is None or target.already_disconnected:
        return _safe_management_response("already_disconnected")

    if target.access_token is not None:
        try:
            client = get_strava_oauth_client(settings=settings, transport=transport)
            await client.revoke_authorization(
                StravaRevocationCredential(access_token=target.access_token)
            )
        except TemporaryProviderError:
            _record_revocation_failure(service, target, "temporary")
            raise _safe_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "strava_revocation_temporarily_unavailable",
            ) from None
        except (AuthenticationError, ProviderError, HTTPException):
            _record_revocation_failure(
                service, target, "authentication_or_configuration"
            )
            raise _safe_error(
                status.HTTP_502_BAD_GATEWAY,
                "strava_revocation_failed",
            ) from None
        remote_revocation_performed = True
    else:
        remote_revocation_performed = False

    try:
        service.complete_disconnect(
            target, remote_revocation_performed=remote_revocation_performed
        )
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_disconnect_failed"
        ) from None
    return _safe_management_response("disconnected")


@router.get("/connect", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def connect_strava(
    current_user: AuthenticatedUser = Depends(get_current_user),
    configuration: StravaConnectConfiguration = Depends(
        get_strava_connect_configuration
    ),
    state_store: OAuthStateStore = Depends(get_oauth_state_store),
) -> RedirectResponse:
    """Create one OAuth request and redirect the local athlete to Strava."""

    state = OAuthState(
        value=generate_oauth_state(),
        user_id=current_user.id,
        expires_at=utc_now() + timedelta(seconds=configuration.state_ttl_seconds),
    )
    try:
        state_store.save(state)
    except Exception:
        raise _safe_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "oauth_state_store_unavailable"
        ) from None

    authorization_url = configuration.client.build_authorization_url(
        state=state.value,
        redirect_uri=configuration.redirect_uri,
        scopes=configuration.scopes,
    )
    return RedirectResponse(
        authorization_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers=NO_STORE_HEADERS,
    )


@router.get("/callback")
async def strava_callback(
    state_value: str | None = Query(default=None, alias="state"),
    code: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    error: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    configuration: StravaCallbackConfiguration = Depends(
        get_strava_callback_configuration
    ),
    state_store: OAuthStateStore = Depends(get_oauth_state_store),
    session: Session = Depends(get_db_session),
) -> JSONResponse:
    """Validate one callback and persist only validated Strava credentials."""

    if not state_value:
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "oauth_state_invalid")

    try:
        state_store.consume(state_value, user_id=current_user.id)
    except OAuthStateUserMismatchError:
        raise _safe_error(status.HTTP_403_FORBIDDEN, "oauth_state_invalid") from None
    except (OAuthStateExpiredError, OAuthStateReusedError, OAuthStateError):
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "oauth_state_invalid") from None

    persistence = StravaOAuthPersistenceService(session)

    if error is not None:
        if error == "access_denied":
            _record_audit(
                persistence,
                action="strava.authorization_denied",
                outcome="denied",
                user_id=current_user.id,
                metadata={
                    "provider": "strava",
                    "local_user_id": str(current_user.id),
                    "outcome": "denied",
                },
            )
            return _safe_response("denied")
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "oauth_callback_invalid")

    if not code:
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "authorization_code_missing")

    callback_scopes = GrantedScopes.parse(scope)
    if callback_scopes is None or not callback_scopes.has_required_read_only(
        configuration.required_scopes
    ):
        _record_scope_failure(persistence, current_user.id, callback_scopes)
        raise _safe_error(status.HTTP_403_FORBIDDEN, "strava_scope_insufficient")

    try:
        token_result = await configuration.client.exchange_authorization_code(
            code=code,
            redirect_uri=configuration.redirect_uri,
        )
    except TemporaryProviderError:
        _record_exchange_failure(persistence, current_user.id)
        raise _safe_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "strava_token_exchange_failed"
        ) from None
    except ProviderError:
        _record_exchange_failure(persistence, current_user.id)
        raise _safe_error(
            status.HTTP_502_BAD_GATEWAY, "strava_token_exchange_failed"
        ) from None

    effective_scopes = token_result.granted_scopes or callback_scopes
    if not effective_scopes.has_required_read_only(configuration.required_scopes):
        _record_scope_failure(persistence, current_user.id, effective_scopes)
        raise _safe_error(status.HTTP_403_FORBIDDEN, "strava_scope_insufficient")

    try:
        result = persistence.persist_connection(
            user_id=current_user.id,
            token_result=token_result,
            scopes=effective_scopes,
        )
    except OAuthOwnershipConflictError:
        _record_audit(
            persistence,
            action="strava.ownership_conflict",
            outcome="rejected",
            user_id=current_user.id,
            metadata={
                "provider": "strava",
                "local_user_id": str(current_user.id),
                "external_athlete_id": token_result.athlete.external_id,
                "scopes": list(effective_scopes.values),
                "outcome": "rejected",
            },
        )
        raise _safe_error(status.HTTP_409_CONFLICT, "strava_ownership_conflict")
    except LocalAthleteMissingError:
        raise _safe_error(status.HTTP_409_CONFLICT, "local_athlete_missing") from None
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_persistence_failed"
        ) from None

    return _safe_response(result.status)


def _record_scope_failure(
    persistence: StravaOAuthPersistenceService,
    user_id: UUID,
    scopes: GrantedScopes | None,
) -> None:
    _record_audit(
        persistence,
        action="strava.scope_insufficient",
        outcome="rejected",
        user_id=user_id,
        metadata={
            "provider": "strava",
            "local_user_id": str(user_id),
            "scopes": list(scopes.values) if scopes else [],
            "outcome": "rejected",
        },
    )


def _record_exchange_failure(
    persistence: StravaOAuthPersistenceService, user_id: UUID
) -> None:
    _record_audit(
        persistence,
        action="strava.token_exchange_failed",
        outcome="failure",
        user_id=user_id,
        metadata={
            "provider": "strava",
            "local_user_id": str(user_id),
            "outcome": "failure",
        },
    )


def _record_audit(
    persistence: StravaOAuthPersistenceService,
    *,
    action: str,
    outcome: str,
    user_id: UUID,
    metadata: dict[str, object],
) -> None:
    try:
        persistence.record_audit(
            action=action,
            outcome=outcome,
            user_id=user_id,
            metadata=metadata,
        )
    except LocalAthleteMissingError:
        raise _safe_error(status.HTTP_409_CONFLICT, "local_athlete_missing") from None
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_audit_failed"
        ) from None


def _safe_response(connection_status: str) -> JSONResponse:
    return JSONResponse(
        {"provider": "strava", "status": connection_status},
        status_code=status.HTTP_200_OK,
        headers=NO_STORE_HEADERS,
    )


def _safe_management_response(connection_status: str) -> JSONResponse:
    return JSONResponse(
        {"provider": "strava", "status": connection_status},
        status_code=status.HTTP_200_OK,
        headers=NO_STORE_HEADERS,
    )


def _record_revocation_failure(
    service: StravaConnectionService, target: DisconnectTarget, category: str
) -> None:
    try:
        service.record_revocation_failure(target, category)
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_audit_failed"
        ) from None


def _safe_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code},
        headers=NO_STORE_HEADERS,
    )
