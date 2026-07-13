import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from app.providers.base import (
    AsyncHttpTransport,
    AuthenticationError,
    HttpResponse,
    HttpTimeout,
    InvalidPayloadError,
    RateLimitError,
    TemporaryProviderError,
)
from app.providers.strava import StravaOAuthClient


VALID_PAYLOAD = {
    "access_token": "access-secret",
    "refresh_token": "refresh-secret",
    "expires_at": 1893456000,
    "expires_in": 21600,
    "token_type": "Bearer",
    "scope": "read,activity:read_all",
    "athlete": {"id": 98765, "firstname": "Ada", "lastname": "Lovelace"},
}


class RecordingTransport(AsyncHttpTransport):
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str], HttpTimeout]] = []

    async def post_form(self, url, *, data, timeout):
        self.calls.append((url, dict(data), timeout))
        return self.response


def make_client(transport: AsyncHttpTransport) -> StravaOAuthClient:
    return StravaOAuthClient(
        client_id="12345",
        client_secret=SecretStr("client-secret"),
        authorization_url="https://www.strava.com/oauth/authorize",
        token_url="https://www.strava.com/oauth/token",
        revocation_url="https://www.strava.com/oauth/revoke",
        transport=transport,
    )


def test_exchange_uses_exact_form_and_returns_typed_secret_safe_result() -> None:
    transport = RecordingTransport(HttpResponse(200, VALID_PAYLOAD))
    result = asyncio.run(make_client(transport).exchange_authorization_code(
        code="one-time-code", redirect_uri="http://127.0.0.1/callback"
    ))

    url, form, timeout = transport.calls[0]
    assert url == "https://www.strava.com/oauth/token"
    assert form == {
        "client_id": "12345",
        "client_secret": "client-secret",
        "code": "one-time-code",
        "grant_type": "authorization_code",
    }
    assert timeout == HttpTimeout(connect_seconds=5.0, response_seconds=10.0)
    assert result.athlete.external_id == "98765"
    assert result.athlete.display_name == "Ada Lovelace"
    assert result.expires_at == datetime.fromtimestamp(1893456000, timezone.utc)
    assert result.granted_scopes.values == ("activity:read_all", "read")
    rendered = repr(result) + repr(make_client(transport))
    assert "access-secret" not in rendered
    assert "refresh-secret" not in rendered
    assert "client-secret" not in rendered


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [(400, AuthenticationError), (429, RateLimitError), (503, TemporaryProviderError)],
)
def test_exchange_maps_provider_failures(status_code, exception_type) -> None:
    client = make_client(RecordingTransport(HttpResponse(status_code, {})))

    with pytest.raises(exception_type):
        asyncio.run(client.exchange_authorization_code(code="code", redirect_uri="callback"))


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**VALID_PAYLOAD, "access_token": ""},
        {**VALID_PAYLOAD, "athlete": None},
        {**VALID_PAYLOAD, "expires_at": 1},
    ],
)
def test_exchange_rejects_malformed_or_incomplete_payload(payload) -> None:
    client = make_client(RecordingTransport(HttpResponse(200, payload)))

    with pytest.raises(InvalidPayloadError):
        asyncio.run(client.exchange_authorization_code(code="code", redirect_uri="callback"))
