from dataclasses import asdict
import logging
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from starlette.concurrency import run_in_threadpool

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.dependencies.athlete_permissions import (
    AthleteCapability,
    athlete_has_capability,
    require_athlete_capability,
)
from app.api.dependencies.providers import (
    StravaCallbackConfiguration,
    StravaConnectConfiguration,
    get_oauth_state_store,
    get_strava_http_transport,
    get_strava_oauth_client,
    get_strava_callback_configuration,
    get_strava_connect_configuration,
    get_strava_import_manager,
)
from app.db.session import get_db_session
from app.db.models import AthleteProfile, UserAthleteMembership
from app.core.settings import Settings, get_settings
from app.integrations.strava.connection_service import (
    DisconnectTarget,
    StravaConnectionService,
)
from app.integrations.strava.oauth_callback import (
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
from app.integrations.strava.account_selection import StravaAccountConfigurationError,active_strava_account
from app.api.v1.schemas.strava_integration import StravaConnectionStartResponse
from app.integrations.strava.activity_import import StravaSummaryImportManager

LOGGER = logging.getLogger(__name__)

read_strava = require_athlete_capability(AthleteCapability.READ_STRAVA_INTEGRATION)
manage_strava = require_athlete_capability(AthleteCapability.MANAGE_STRAVA_CONNECTION)

router = APIRouter(prefix="/integrations/strava", tags=["integrations"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


@router.get("/status")
def strava_status(
    current_athlete: CurrentAthleteContext = Depends(read_strava),
    session: Session = Depends(get_db_session),
) -> JSONResponse:
    """Return only stored, secret-free connection state for the current user."""

    try:
        connection = StravaConnectionService(session).status_for_athlete(
            current_athlete.athlete_id
        )
    except StravaAccountConfigurationError:
        raise _safe_error(
            status.HTTP_409_CONFLICT, "strava_account_configuration_invalid"
        ) from None
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
    current_athlete: CurrentAthleteContext = Depends(manage_strava),
    settings: Settings = Depends(get_settings),
    transport: AsyncHttpTransport = Depends(get_strava_http_transport),
    session: Session = Depends(get_db_session),
) -> JSONResponse:
    """Revoke and remove only the current user's Strava authorization."""

    service = StravaConnectionService(session)
    try:
        target = service.begin_disconnect(
            athlete_id=current_athlete.athlete_id,
            user_id=current_user.id,
        )
    except StravaAccountConfigurationError:
        raise _safe_error(
            status.HTTP_409_CONFLICT, "strava_account_configuration_invalid"
        ) from None
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
async def connect_strava(
    current_user: AuthenticatedUser = Depends(get_current_user),
    current_athlete: CurrentAthleteContext = Depends(manage_strava),
    configuration: StravaConnectConfiguration = Depends(
        get_strava_connect_configuration
    ),
    state_store: OAuthStateStore = Depends(get_oauth_state_store),
    session: Session = Depends(get_db_session),
) -> RedirectResponse:
    """Create one OAuth request and redirect the local athlete to Strava."""

    authorization_url = await _start_strava_connection(
        current_athlete=current_athlete,
        configuration=configuration,
        state_store=state_store,
        session=session,
    )
    return RedirectResponse(
        authorization_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers=NO_STORE_HEADERS,
    )


@router.post("/connect/start", response_model=StravaConnectionStartResponse)
async def start_strava_connection(
    response: Response,
    current_athlete: CurrentAthleteContext = Depends(manage_strava),
    configuration: StravaConnectConfiguration = Depends(get_strava_connect_configuration),
    state_store: OAuthStateStore = Depends(get_oauth_state_store),
    session: Session = Depends(get_db_session),
    import_manager: StravaSummaryImportManager = Depends(get_strava_import_manager),
) -> StravaConnectionStartResponse:
    """Create athlete-bound OAuth state and return only the external URL."""
    del import_manager
    response.headers.update(NO_STORE_HEADERS)
    authorization_url = await _start_strava_connection(
        current_athlete=current_athlete,
        configuration=configuration,
        state_store=state_store,
        session=session,
    )
    return StravaConnectionStartResponse(authorization_url=authorization_url)


async def _start_strava_connection(
    *,
    current_athlete: CurrentAthleteContext,
    configuration: StravaConnectConfiguration,
    state_store: OAuthStateStore,
    session: Session,
) -> str:
    try:
        active_strava_account(session, athlete_id=current_athlete.athlete_id)
    except StravaAccountConfigurationError:
        raise _safe_error(status.HTTP_409_CONFLICT, "strava_account_configuration_invalid") from None
    oauth_state = OAuthState(
        value=generate_oauth_state(),
        user_id=current_athlete.user_id,
        athlete_id=current_athlete.athlete_id,
        expires_at=utc_now() + timedelta(seconds=configuration.state_ttl_seconds),
    )
    try:
        await run_in_threadpool(state_store.save, oauth_state)
    except Exception:
        raise _safe_error(status.HTTP_503_SERVICE_UNAVAILABLE, "oauth_state_store_unavailable") from None
    return configuration.client.build_authorization_url(
        state=oauth_state.value,
        redirect_uri=configuration.redirect_uri,
        scopes=configuration.scopes,
    )


@router.get("/callback")
async def strava_callback(
    request: Request,
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
        oauth_state = await run_in_threadpool(
            state_store.consume,
            state_value,
            user_id=current_user.id,
        )
    except OAuthStateUserMismatchError:
        raise _safe_error(status.HTTP_403_FORBIDDEN, "oauth_state_invalid") from None
    except (OAuthStateExpiredError, OAuthStateReusedError, OAuthStateError):
        raise _safe_error(status.HTTP_400_BAD_REQUEST, "oauth_state_invalid") from None

    persistence = StravaOAuthPersistenceService(session)
    membership = session.scalar(
        select(UserAthleteMembership)
        .options(joinedload(UserAthleteMembership.athlete_profile))
        .where(
            UserAthleteMembership.user_id == current_user.id,
            UserAthleteMembership.athlete_profile_id == oauth_state.athlete_id,
            UserAthleteMembership.is_active.is_(True),
            UserAthleteMembership.athlete_profile.has(AthleteProfile.deleted_at.is_(None)),
        )
    )
    if membership is None:
        raise _safe_error(status.HTTP_403_FORBIDDEN, "athlete_not_authorized")
    callback_athlete = CurrentAthleteContext(
        user_id=current_user.id,
        athlete_id=membership.athlete_profile_id,
        role=membership.role,
        athlete_profile=membership.athlete_profile,
        membership=membership,
    )
    if not athlete_has_capability(
        callback_athlete, AthleteCapability.MANAGE_STRAVA_CONNECTION
    ):
        raise _safe_error(status.HTTP_403_FORBIDDEN, "athlete_permission_denied")

    if error is not None:
        if error == "access_denied":
            _record_audit(
                persistence,
                action="strava.authorization_denied",
                outcome="denied",
                user_id=current_user.id,
                athlete_id=oauth_state.athlete_id,
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
        _record_scope_failure(
            persistence, current_user.id, oauth_state.athlete_id, callback_scopes
        )
        raise _safe_error(status.HTTP_403_FORBIDDEN, "strava_scope_insufficient")

    try:
        token_result = await configuration.client.exchange_authorization_code(
            code=code,
            redirect_uri=configuration.redirect_uri,
        )
    except TemporaryProviderError:
        _record_exchange_failure(persistence, current_user.id, oauth_state.athlete_id)
        raise _safe_error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "strava_token_exchange_failed"
        ) from None
    except ProviderError:
        _record_exchange_failure(persistence, current_user.id, oauth_state.athlete_id)
        raise _safe_error(
            status.HTTP_502_BAD_GATEWAY, "strava_token_exchange_failed"
        ) from None

    effective_scopes = token_result.granted_scopes or callback_scopes
    if not effective_scopes.has_required_read_only(configuration.required_scopes):
        _record_scope_failure(
            persistence, current_user.id, oauth_state.athlete_id, effective_scopes
        )
        raise _safe_error(status.HTTP_403_FORBIDDEN, "strava_scope_insufficient")

    try:
        result = persistence.persist_connection(
            user_id=current_user.id,
            athlete_id=oauth_state.athlete_id,
            token_result=token_result,
            scopes=effective_scopes,
        )
    except OAuthOwnershipConflictError:
        _record_audit(
            persistence,
            action="strava.ownership_conflict",
            outcome="rejected",
            user_id=current_user.id,
            athlete_id=oauth_state.athlete_id,
            metadata={
                "provider": "strava",
                "local_user_id": str(current_user.id),
                "external_athlete_id": token_result.athlete.external_id,
                "scopes": list(effective_scopes.values),
                "outcome": "rejected",
            },
        )
        raise _safe_error(
            status.HTTP_409_CONFLICT,
            "strava_external_account_already_linked",
        )
    except Exception:
        raise _safe_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "strava_persistence_failed"
        ) from None

    manager = getattr(request.app.state, "strava_import_manager", None)
    if isinstance(manager, StravaSummaryImportManager):
        try:
            initial_job = await run_in_threadpool(manager.create_or_resume_job, current_user.id, athlete_id=oauth_state.athlete_id)
            manager.schedule(initial_job.job_id)
        except Exception:
            LOGGER.exception("Automatic Strava import scheduling failed", extra={"athlete_id": str(oauth_state.athlete_id)})
    return _safe_response(result.status)


def _record_scope_failure(
    persistence: StravaOAuthPersistenceService,
    user_id: UUID,
    athlete_id: UUID,
    scopes: GrantedScopes | None,
) -> None:
    _record_audit(
        persistence,
        action="strava.scope_insufficient",
        outcome="rejected",
        user_id=user_id,
        athlete_id=athlete_id,
        metadata={
            "provider": "strava",
            "local_user_id": str(user_id),
            "scopes": list(scopes.values) if scopes else [],
            "outcome": "rejected",
        },
    )


def _record_exchange_failure(
    persistence: StravaOAuthPersistenceService, user_id: UUID, athlete_id: UUID
) -> None:
    _record_audit(
        persistence,
        action="strava.token_exchange_failed",
        outcome="failure",
        user_id=user_id,
        athlete_id=athlete_id,
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
    athlete_id: UUID,
    metadata: dict[str, object],
) -> None:
    try:
        persistence.record_audit(
            action=action,
            outcome=outcome,
            user_id=user_id,
            athlete_id=athlete_id,
            metadata=metadata,
        )
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
