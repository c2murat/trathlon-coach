from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.api.dependencies.providers import get_oauth_state_store, get_strava_http_transport
from app.core.settings import Settings, get_settings
from app.db.base import Base
from app.db.models import AthleteProfile, AuditEvent, IntegrationAccount, OAuthCredential, User, UserAthleteMembership
from app.db.session import get_db_session
from app.main import app
from app.providers.base import AsyncHttpTransport, HttpResponse, OAuthState, SQLiteOAuthStateStore, utc_now


ACCESS = "callback-access-secret"
REFRESH = "callback-refresh-secret"


class StubTransport(AsyncHttpTransport):
    def __init__(self, status_code=200, payload=None) -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else token_payload()
        self.calls = 0

    async def post_form(self, url, *, data, timeout):
        self.calls += 1
        return HttpResponse(self.status_code, self.payload)


def token_payload(*, athlete_id=98765, access=ACCESS, refresh=REFRESH, scope="read,activity:read_all"):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": 1893456000,
        "expires_in": 21600,
        "token_type": "Bearer",
        "scope": scope,
        "athlete": {"id": athlete_id, "firstname": "Test", "lastname": "Athlete"},
    }


@pytest.fixture
def callback_context(tmp_path):
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
            email="athlete@example.test",
            normalized_email="athlete@example.test",
            auth_subject="local-test-athlete",
            timezone="Europe/Madrid",
        )
        session.add(user)
        session.flush()
        athlete = AthleteProfile(id=LOCAL_MVP_USER_ID,user_id=user.id, timezone="Europe/Madrid")
        session.add(athlete)
        session.flush()
        session.add(UserAthleteMembership(user_id=user.id,athlete_profile_id=athlete.id,role="owner",is_active=True,is_default=True))
        session.commit()

    store = SQLiteOAuthStateStore(tmp_path / "oauth-state.sqlite3")
    transport = StubTransport()
    settings = Settings(
        environment="test",
        strava_client_id="12345",
        strava_client_secret=SecretStr("client-secret"),
        strava_redirect_uri="http://127.0.0.1:8000/integrations/strava/callback",
        strava_scopes="read,activity:read_all",
    )

    def db_override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_settings] = lambda: settings
    app.state.oauth_state_store = store
    app.dependency_overrides[get_strava_http_transport] = lambda: transport
    app.dependency_overrides[get_db_session] = db_override
    yield TestClient(app), factory, store, transport
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def save_state(store, *, user_id=LOCAL_MVP_USER_ID, expired=False):
    value = f"state-{uuid4()}"
    expiry = utc_now() + timedelta(minutes=-1 if expired else 10)
    athlete_id = LOCAL_MVP_USER_ID
    store.save(OAuthState(value=value, user_id=user_id, athlete_id=athlete_id, expires_at=expiry))
    return value


def callback(client, state, **params):
    query = {"state": state, "code": "code", "scope": "read,activity:read_all"}
    query.update(params)
    return client.get("/integrations/strava/callback", params=query)


def test_success_persists_account_credential_and_safe_audit(callback_context) -> None:
    client, factory, store, _ = callback_context
    response = callback(client, save_state(store))

    assert response.status_code == 200
    assert response.json() == {"provider": "strava", "status": "connected"}
    assert response.headers["cache-control"] == "no-store"
    rendered = response.text
    with factory() as session:
        account = session.scalar(select(IntegrationAccount))
        credential = session.scalar(select(OAuthCredential))
        audit = session.scalar(select(AuditEvent))
        assert account.external_account_id == "98765"
        assert account.scopes == ["activity:read_all", "read"]
        assert credential.access_token == ACCESS
        assert credential.refresh_token == REFRESH
        assert credential.expires_at.tzinfo is not None
        rendered += repr(credential) + repr(audit.event_metadata)
    assert ACCESS not in rendered
    assert REFRESH not in rendered


@pytest.mark.parametrize("with_header_for_other_athlete", [False, True])
def test_callback_uses_state_athlete_not_current_selection(
    callback_context, with_header_for_other_athlete
) -> None:
    client, factory, store, _ = callback_context
    headers = {}
    if with_header_for_other_athlete:
        with factory() as session:
            other_owner=User(email="other-owner@example.test",normalized_email="other-owner@example.test",auth_subject="other-owner")
            other = AthleteProfile(user=other_owner,timezone="UTC")
            session.add_all([other_owner,other])
            session.flush()
            session.add(UserAthleteMembership(user_id=LOCAL_MVP_USER_ID,athlete_profile_id=other.id,role="owner",is_active=True,is_default=False))
            session.commit()
            headers["X-TriCoach-Athlete-Id"] = str(other.id)
    response = client.get(
        "/integrations/strava/callback",
        params={"state": save_state(store), "code": "code", "scope": "read,activity:read_all"},
        headers=headers,
    )
    assert response.status_code == 200
    with factory() as session:
        assert session.scalar(select(IntegrationAccount)).athlete_id == LOCAL_MVP_USER_ID


@pytest.mark.parametrize("mutation,expected_code", [("inactive","athlete_not_authorized"),("viewer","athlete_permission_denied")])
def test_callback_revalidates_membership_and_capability(callback_context,mutation,expected_code) -> None:
    client,factory,store,transport=callback_context;state=save_state(store)
    with factory() as session:
        membership=session.scalar(select(UserAthleteMembership));membership.is_active=mutation!="inactive";membership.role="viewer" if mutation=="viewer" else membership.role;session.commit()
    response=callback(client,state);assert response.status_code==403;assert response.json()["detail"]["code"]==expected_code;assert transport.calls==0
    with factory() as session:
        assert session.scalar(select(IntegrationAccount)) is None;assert session.scalar(select(OAuthCredential)) is None


def test_connect_and_callback_share_application_state_store(callback_context) -> None:
    client, factory, _, transport = callback_context
    connect_response = client.get(
        "/integrations/strava/connect", follow_redirects=False
    )
    state = parse_qs(urlsplit(connect_response.headers["location"]).query)["state"][0]

    callback_response = callback(client, state)

    assert connect_response.status_code == 307
    assert callback_response.status_code == 200
    assert callback_response.json() == {
        "provider": "strava",
        "status": "connected",
    }
    assert transport.calls == 1
    with factory() as session:
        assert session.scalar(select(IntegrationAccount)) is not None
        assert session.scalar(select(OAuthCredential)) is not None


def test_state_is_consumed_exactly_once(callback_context) -> None:
    client, _, store, transport = callback_context
    state = save_state(store)
    assert callback(client, state).status_code == 200
    reused = callback(client, state)
    assert reused.status_code == 400
    assert reused.json() == {"detail": {"code": "oauth_state_invalid"}}
    assert transport.calls == 1


@pytest.mark.parametrize("case", ["missing", "expired", "mismatch"])
def test_invalid_states_are_rejected_before_exchange(callback_context, case) -> None:
    client, _, store, transport = callback_context
    if case == "missing":
        response = client.get("/integrations/strava/callback", params={"code": "code"})
    else:
        state = save_state(store, expired=case == "expired", user_id=uuid4() if case == "mismatch" else LOCAL_MVP_USER_ID)
        response = callback(client, state)
    assert response.status_code in {400, 403}
    assert transport.calls == 0


def test_denial_is_audited_without_credentials(callback_context) -> None:
    client, factory, store, transport = callback_context
    response = client.get(
        "/integrations/strava/callback",
        params={"state": save_state(store), "error": "access_denied"},
    )
    assert response.json() == {"provider": "strava", "status": "denied"}
    assert transport.calls == 0
    with factory() as session:
        assert session.scalar(select(OAuthCredential)) is None
        assert session.scalar(select(AuditEvent)).action == "strava.authorization_denied"


@pytest.mark.parametrize(
    ("overrides", "expected_status", "expected_code"),
    [
        ({"code": ""}, 400, "authorization_code_missing"),
        ({"scope": "read"}, 403, "strava_scope_insufficient"),
        ({"scope": "read,activity:read_all,activity:write"}, 403, "strava_scope_insufficient"),
    ],
)
def test_callback_rejects_missing_code_or_insufficient_scope(callback_context, overrides, expected_status, expected_code) -> None:
    client, _, store, transport = callback_context
    response = callback(client, save_state(store), **overrides)
    assert response.status_code == expected_status
    assert response.json() == {"detail": {"code": expected_code}}
    assert transport.calls == 0


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_status"),
    [
        (503, {}, 503),
        (400, {}, 502),
        (200, {}, 502),
        (200, {**token_payload(), "athlete": None}, 502),
    ],
)
def test_token_exchange_failures_are_safe(callback_context, status_code, payload, expected_status) -> None:
    client, _, store, transport = callback_context
    transport.status_code = status_code
    transport.payload = payload
    response = callback(client, save_state(store))
    assert response.status_code == expected_status
    assert response.json() == {"detail": {"code": "strava_token_exchange_failed"}}
    assert ACCESS not in response.text and REFRESH not in response.text


def test_reconnection_rotates_credentials_without_duplicate_account(callback_context) -> None:
    client, factory, store, transport = callback_context
    assert callback(client, save_state(store)).json()["status"] == "connected"
    transport.payload = token_payload(access="new-access", refresh="new-refresh")
    response = callback(client, save_state(store))
    assert response.json()["status"] == "reconnected"
    with factory() as session:
        assert len(list(session.scalars(select(IntegrationAccount)))) == 1
        credential = session.scalar(select(OAuthCredential))
        assert credential.access_token == "new-access"
        assert credential.refresh_token == "new-refresh"


def test_rejects_different_external_account_for_same_local_athlete(callback_context) -> None:
    client, factory, store, transport = callback_context
    assert callback(client, save_state(store)).status_code == 200
    transport.payload = token_payload(athlete_id=123456)
    response = callback(client, save_state(store))
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "strava_external_account_already_linked"}}
    with factory() as session:
        assert len(list(session.scalars(select(IntegrationAccount)))) == 1


def test_rejects_external_account_owned_by_another_local_athlete(callback_context) -> None:
    client, factory, store, _, = callback_context
    with factory() as session:
        other_user = User(email="other@test", normalized_email="other@test", auth_subject="other")
        other_athlete = AthleteProfile(user=other_user)
        session.add(IntegrationAccount(athlete=other_athlete, provider="strava", external_account_id="98765"))
        session.commit()
    response = callback(client, save_state(store))
    assert response.status_code == 409
    with factory() as session:
        assert len(list(session.scalars(select(IntegrationAccount)))) == 1


def test_persistence_rolls_back_all_rows_when_commit_fails(callback_context) -> None:
    from app.integrations.strava.oauth_callback import StravaOAuthPersistenceService
    from app.providers.strava import GrantedScopes, StravaTokenResult

    _, factory, _, _ = callback_context
    with factory() as session:
        service = StravaOAuthPersistenceService(session)
        result = StravaTokenResult.from_payload(token_payload())

        def fail_commit() -> None:
            raise RuntimeError("forced commit failure")

        session.commit = fail_commit
        with pytest.raises(RuntimeError, match="forced commit failure"):
            service.persist_connection(
                user_id=LOCAL_MVP_USER_ID,
                athlete_id=LOCAL_MVP_USER_ID,
                token_result=result,
                scopes=GrantedScopes.parse("read,activity:read_all"),
            )

    with factory() as verification:
        assert verification.scalar(select(IntegrationAccount)) is None
        assert verification.scalar(select(OAuthCredential)) is None
        assert verification.scalar(select(AuditEvent)) is None
