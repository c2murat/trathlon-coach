from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.dependencies.providers import get_oauth_state_store
from app.core.settings import Settings, get_settings
from app.main import app
from app.providers.base import OAuthState, OAuthStateStorageError, OAuthStateStore


class RecordingStateStore(OAuthStateStore):
    def __init__(self) -> None:
        self.saved: list[OAuthState] = []

    def save(self, state: OAuthState) -> None:
        self.saved.append(state)

    def consume(self, state_value: str, *, user_id):
        raise NotImplementedError


class FailingStateStore(RecordingStateStore):
    def save(self, state: OAuthState) -> None:
        raise OAuthStateStorageError("test storage failure")


def configured_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "strava_client_id": "12345",
        "strava_client_secret": SecretStr("not-a-real-secret"),
        "strava_redirect_uri": (
            "http://127.0.0.1:8000/integrations/strava/callback"
        ),
        "strava_scopes": "read,activity:read_all",
        "oauth_state_ttl_seconds": 600,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def connect_with(
    settings: Settings,
    store: OAuthStateStore,
) -> tuple:
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_oauth_state_store] = lambda: store
    response = TestClient(app).get(
        "/integrations/strava/connect", follow_redirects=False
    )
    return response, urlsplit(response.headers.get("location", ""))


def test_connect_redirect_contains_only_required_read_authorization() -> None:
    store = RecordingStateStore()
    response, location = connect_with(configured_settings(), store)
    query = parse_qs(location.query)

    assert response.status_code == 307
    assert location.scheme == "https"
    assert location.netloc == "www.strava.com"
    assert location.path == "/oauth/authorize"
    assert query == {
        "client_id": ["12345"],
        "redirect_uri": [
            "http://127.0.0.1:8000/integrations/strava/callback"
        ],
        "response_type": ["code"],
        "approval_prompt": ["auto"],
        "scope": ["read,activity:read_all"],
        "state": [store.saved[0].value],
    }
    assert "write" not in query["scope"][0]


def test_connect_stores_unique_state_with_user_and_expiry() -> None:
    store = RecordingStateStore()
    settings = configured_settings()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_oauth_state_store] = lambda: store
    client = TestClient(app)
    before = datetime.now(timezone.utc)

    first = client.get("/integrations/strava/connect", follow_redirects=False)
    second = client.get("/integrations/strava/connect", follow_redirects=False)

    assert first.status_code == second.status_code == 307
    assert len(store.saved) == 2
    assert store.saved[0].value != store.saved[1].value
    assert store.saved[0].user_id == store.saved[1].user_id
    assert store.saved[0].expires_at > before
    assert 590 <= (store.saved[0].expires_at - before).total_seconds() <= 610


def test_connect_never_exposes_client_secret() -> None:
    secret = "highly-sensitive-test-value"
    response, _ = connect_with(
        configured_settings(strava_client_secret=SecretStr(secret)),
        RecordingStateStore(),
    )
    rendered_response = f"{response.headers!r} {response.text}"

    assert secret not in response.headers["location"]
    assert secret not in rendered_response
    assert "client_secret" not in response.headers["location"]


def test_connect_sets_no_store_headers() -> None:
    response, _ = connect_with(configured_settings(), RecordingStateStore())

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_connect_rejects_missing_configuration_safely() -> None:
    response, _ = connect_with(
        Settings(environment="test"), RecordingStateStore()
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "strava_configuration_missing"}}


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "not-a-url",
        "https://user:password@example.com/callback",
        "http://example.com/callback",
        "https://example.com/callback#fragment",
    ],
)
def test_connect_rejects_invalid_redirect_uri(redirect_uri: str) -> None:
    response, _ = connect_with(
        configured_settings(strava_redirect_uri=redirect_uri), RecordingStateStore()
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "strava_redirect_uri_invalid"}}


def test_connect_ignores_arbitrary_redirect_uri_query_parameter() -> None:
    store = RecordingStateStore()
    app.dependency_overrides[get_settings] = lambda: configured_settings()
    app.dependency_overrides[get_oauth_state_store] = lambda: store

    response = TestClient(app).get(
        "/integrations/strava/connect?redirect_uri=https://attacker.example/callback",
        follow_redirects=False,
    )
    query = parse_qs(urlsplit(response.headers["location"]).query)

    assert query["redirect_uri"] == [
        "http://127.0.0.1:8000/integrations/strava/callback"
    ]


def test_connect_returns_safe_error_when_state_store_fails() -> None:
    response, _ = connect_with(configured_settings(), FailingStateStore())

    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "oauth_state_store_unavailable"}
    }
    assert response.headers["cache-control"] == "no-store"
