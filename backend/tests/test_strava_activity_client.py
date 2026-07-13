from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest
from pydantic import SecretStr

from app.providers.base import AuthenticationError, HttpTimeout, TemporaryProviderError
from app.providers.strava.activity_client import (
    StravaActivityClient,
    StravaActivityRateLimitError,
    StravaApiResponse,
)


class StubTransport:
    def __init__(self, response: StravaApiResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, Mapping[str, str], Mapping[str, int], HttpTimeout]] = []

    async def get_json(self, url, *, headers, params, timeout):
        self.calls.append((url, headers, params, timeout))
        return self.response


def test_client_calls_official_summary_endpoint_with_pagination_and_filters():
    transport = StubTransport(
        StravaApiResponse(
            200,
            [{"id": 10}],
            {
                "X-RateLimit-Limit": "200,2000",
                "X-RateLimit-Usage": "2,20",
                "X-ReadRateLimit-Limit": "100,1000",
                "X-ReadRateLimit-Usage": "1,10",
            },
        )
    )
    client = StravaActivityClient(
        api_base_url="https://www.strava.com/api/v3", transport=transport
    )

    page = asyncio.run(
        client.fetch_activity_summaries(
            access_token=SecretStr("access-secret"),
            page=2,
            per_page=100,
            after=11,
            before=22,
        )
    )

    assert page.activities == ({"id": 10},)
    url, headers, params, timeout = transport.calls[0]
    assert url == "https://www.strava.com/api/v3/athlete/activities"
    assert headers["Authorization"] == "Bearer access-secret"
    assert params == {"page": 2, "per_page": 100, "after": 11, "before": 22}
    assert timeout.connect_seconds > 0
    assert page.rate_limit.read_usage == (1, 10)
    assert "access-secret" not in repr(client)


@pytest.mark.parametrize(
    ("status_code", "exception"),
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (500, TemporaryProviderError),
    ],
)
def test_client_maps_safe_provider_failures(status_code, exception):
    client = StravaActivityClient(
        api_base_url="https://www.strava.com/api/v3",
        transport=StubTransport(StravaApiResponse(status_code, {})),
    )
    with pytest.raises(exception):
        asyncio.run(
            client.fetch_activity_summaries(
                access_token=SecretStr("never-log-this"), page=1
            )
        )


def test_client_exposes_only_safe_rate_limit_delay():
    client = StravaActivityClient(
        api_base_url="https://www.strava.com/api/v3",
        transport=StubTransport(
            StravaApiResponse(
                429,
                {"message": "provider body must not escape"},
                {"Retry-After": "17", "X-RateLimit-Usage": "200,2000"},
            )
        ),
    )
    with pytest.raises(StravaActivityRateLimitError) as captured:
        asyncio.run(
            client.fetch_activity_summaries(
                access_token=SecretStr("never-log-this"), page=1
            )
        )
    assert captured.value.retry_after_seconds == 17
    assert "provider body" not in str(captured.value)
