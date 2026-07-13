from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.api.dependencies.providers import get_strava_http_transport
from app.core.settings import Settings, get_settings
from app.db.base import Base, utc_now
from app.db.models import (
    AthleteProfile,
    AuditEvent,
    CompletedActivity,
    IntegrationAccount,
    OAuthCredential,
    User,
)
from app.db.session import get_db_session
from app.integrations.strava.connection_service import StravaConnectionService
from app.main import app
from app.providers.base import AsyncHttpTransport, HttpBasicAuth, HttpResponse


ACCESS = "disconnect-access-secret"
REFRESH = "disconnect-refresh-secret"
CLIENT_SECRET = "disconnect-client-secret"


class RevocationTransport(AsyncHttpTransport):
    def __init__(self) -> None:
        self.status_code = 200
        self.payload: object = {}
        self.calls: list[tuple[str, dict[str, str], HttpBasicAuth | None]] = []

    async def post_form(self, url, *, data, timeout, basic_auth=None):
        self.calls.append((url, dict(data), basic_auth))
        return HttpResponse(self.status_code, self.payload)


def configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "strava_client_id": "12345",
        "strava_client_secret": SecretStr(CLIENT_SECRET),
        "strava_redirect_uri": "http://127.0.0.1:8000/integrations/strava/callback",
        "strava_scopes": "read,activity:read_all",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def management_context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        user = User(
            id=LOCAL_MVP_USER_ID,
            email="owner@example.test",
            normalized_email="owner@example.test",
            auth_subject="management-owner",
        )
        session.add(user)
        session.flush()
        session.add(AthleteProfile(user_id=user.id, timezone="Europe/Madrid"))
        session.commit()

    transport = RevocationTransport()

    def db_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: configured_settings()
    app.dependency_overrides[get_strava_http_transport] = lambda: transport
    app.dependency_overrides[get_db_session] = db_override
    yield TestClient(app), factory, transport
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_connection(
    factory,
    *,
    status="active",
    scopes=None,
    with_credential=True,
    external_id="98765",
):
    with factory() as session:
        athlete = session.scalar(
            select(AthleteProfile).where(AthleteProfile.user_id == LOCAL_MVP_USER_ID)
        )
        account = IntegrationAccount(
            athlete_id=athlete.id,
            provider="strava",
            external_account_id=external_id,
            status=status,
            scopes=scopes if scopes is not None else ["read", "activity:read_all"],
            connected_at=utc_now(),
        )
        session.add(account)
        session.flush()
        if with_credential:
            session.add(
                OAuthCredential(
                    integration_account_id=account.id,
                    access_token=ACCESS,
                    refresh_token=REFRESH,
                    expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
                    scopes=account.scopes,
                )
            )
        session.commit()
        return account.id, athlete.id


def test_status_not_connected_is_safe_and_not_cached(management_context) -> None:
    client, _, _ = management_context
    response = client.get("/integrations/strava/status")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "provider": "strava",
        "connection_status": "not_connected",
        "connected": False,
        "external_athlete_id": None,
        "granted_scopes": [],
        "connected_at": None,
        "updated_at": None,
        "token_expires_at": None,
        "requires_reconnect": False,
        "last_sync_at": None,
        "message": "Strava is not connected.",
    }


def test_status_connected_serializes_only_allowlisted_safe_fields(management_context) -> None:
    client, factory, _ = management_context
    add_connection(factory)
    response = client.get("/integrations/strava/status")
    body = response.json()
    assert body["connection_status"] == "connected"
    assert body["connected"] is True
    assert body["external_athlete_id"] == "98765"
    assert body["granted_scopes"] == ["activity:read_all", "read"]
    assert body["token_expires_at"].startswith("2030-01-01T00:00:00")
    rendered = response.text
    assert ACCESS not in rendered and REFRESH not in rendered and CLIENT_SECRET not in rendered
    assert set(body) == {
        "provider", "connection_status", "connected", "external_athlete_id",
        "granted_scopes", "connected_at", "updated_at", "token_expires_at",
        "requires_reconnect", "last_sync_at", "message",
    }


@pytest.mark.parametrize(
    ("account_status", "scopes", "credential", "expected"),
    [
        ("active", ["read"], True, "scope_insufficient"),
        ("disconnected", ["read", "activity:read_all"], False, "disconnected"),
        ("revoked", ["read", "activity:read_all"], False, "revoked"),
        ("error", ["read", "activity:read_all"], True, "temporarily_unavailable"),
    ],
)
def test_status_maps_stored_connection_states(
    management_context, account_status, scopes, credential, expected
) -> None:
    client, factory, _ = management_context
    add_connection(factory, status=account_status, scopes=scopes, with_credential=credential)
    body = client.get("/integrations/strava/status").json()
    assert body["connection_status"] == expected
    assert body["connected"] is False


def test_status_and_disconnect_are_isolated_to_current_owner(management_context) -> None:
    client, factory, transport = management_context
    with factory() as session:
        other_user = User(email="other@test", normalized_email="other@test", auth_subject="other-owner")
        other_athlete = AthleteProfile(user=other_user)
        account = IntegrationAccount(
            athlete=other_athlete,
            provider="strava",
            external_account_id="other-external",
            status="active",
            scopes=["read", "activity:read_all"],
        )
        account.oauth_credential = OAuthCredential(
            access_token=ACCESS,
            refresh_token=REFRESH,
            expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )
        session.add(account)
        session.commit()
    assert client.get("/integrations/strava/status").json()["connection_status"] == "not_connected"
    assert client.delete("/integrations/strava/disconnect").json()["status"] == "already_disconnected"
    assert transport.calls == []
    with factory() as session:
        assert session.scalar(select(OAuthCredential)) is not None


def test_disconnect_revokes_removes_credential_and_preserves_activity(management_context) -> None:
    client, factory, transport = management_context
    account_id, athlete_id = add_connection(factory)
    with factory() as session:
        session.add(
            CompletedActivity(
                athlete_id=athlete_id,
                source_integration_account_id=account_id,
                external_activity_id="activity-1",
                source_summary="strava",
                sport="running",
                name="Preserved run",
                start_at=utc_now(),
                timezone="Europe/Madrid",
                elapsed_time_s=1800,
            )
        )
        session.commit()

    response = client.delete("/integrations/strava/disconnect")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"provider": "strava", "status": "disconnected"}
    url, form, auth = transport.calls[0]
    assert url == "https://www.strava.com/oauth/revoke"
    assert form == {"token": ACCESS, "token_type_hint": "access_token"}
    assert auth.username == "12345"
    assert auth.password.get_secret_value() == CLIENT_SECRET
    assert ACCESS not in repr(auth) and CLIENT_SECRET not in repr(auth)

    with factory() as session:
        account = session.get(IntegrationAccount, account_id)
        assert account.status == "disconnected"
        assert account.disconnected_at is not None
        assert session.scalar(select(OAuthCredential)) is None
        assert session.scalar(select(CompletedActivity)).name == "Preserved run"
        audits = list(session.scalars(select(AuditEvent)))
        rendered_audits = repr([(audit.action, audit.event_metadata) for audit in audits])
        assert {audit.action for audit in audits} == {
            "strava.disconnect_requested",
            "strava.remote_revocation_succeeded",
            "strava.disconnect_completed",
        }
    assert ACCESS not in rendered_audits and REFRESH not in rendered_audits


def test_repeated_disconnect_and_missing_account_are_idempotent(management_context) -> None:
    client, factory, transport = management_context
    assert client.delete("/integrations/strava/disconnect").json()["status"] == "already_disconnected"
    add_connection(factory)
    assert client.delete("/integrations/strava/disconnect").json()["status"] == "disconnected"
    assert client.delete("/integrations/strava/disconnect").json()["status"] == "already_disconnected"
    assert len(transport.calls) == 1


def test_remote_200_for_already_invalid_token_is_success(management_context) -> None:
    client, factory, transport = management_context
    add_connection(factory)
    transport.payload = {"message": "token was already invalid"}
    assert client.delete("/integrations/strava/disconnect").json()["status"] == "disconnected"
    with factory() as session:
        assert session.scalar(select(OAuthCredential)) is None


@pytest.mark.parametrize(
    ("status_code", "expected_http", "expected_action"),
    [
        (503, 503, "strava.revocation_temporarily_failed"),
        (401, 502, "strava.revocation_authentication_failed"),
    ],
)
def test_remote_failure_preserves_retry_credential_and_is_secret_safe(
    management_context, status_code, expected_http, expected_action
) -> None:
    client, factory, transport = management_context
    account_id, _ = add_connection(factory)
    transport.status_code = status_code
    transport.payload = {"provider_debug": ACCESS, "client": CLIENT_SECRET}
    response = client.delete("/integrations/strava/disconnect")
    assert response.status_code == expected_http
    assert ACCESS not in response.text and CLIENT_SECRET not in response.text
    with factory() as session:
        account = session.get(IntegrationAccount, account_id)
        credential = session.scalar(select(OAuthCredential))
        assert account.status == "active"
        assert credential.access_token == ACCESS
        audits = list(session.scalars(select(AuditEvent)))
        assert expected_action in {audit.action for audit in audits}
        assert ACCESS not in repr([audit.event_metadata for audit in audits])


def test_invalid_client_configuration_does_not_mark_disconnected(management_context) -> None:
    client, factory, _ = management_context
    account_id, _ = add_connection(factory)
    app.dependency_overrides[get_settings] = lambda: configured_settings(
        strava_client_secret=None
    )
    response = client.delete("/integrations/strava/disconnect")
    assert response.status_code == 502
    with factory() as session:
        assert session.get(IntegrationAccount, account_id).status == "active"
        assert session.scalar(select(OAuthCredential)) is not None


def test_local_disconnect_transaction_rolls_back_on_commit_failure(management_context) -> None:
    _, factory, _ = management_context
    account_id, _ = add_connection(factory)
    with factory() as session:
        service = StravaConnectionService(session)
        target = service.begin_disconnect(LOCAL_MVP_USER_ID)

        def fail_commit() -> None:
            raise RuntimeError("forced commit failure")

        session.commit = fail_commit
        with pytest.raises(RuntimeError, match="forced commit failure"):
            service.complete_disconnect(target, remote_revocation_performed=True)

    with factory() as session:
        assert session.get(IntegrationAccount, account_id).status == "active"
        assert session.scalar(select(OAuthCredential)) is not None
