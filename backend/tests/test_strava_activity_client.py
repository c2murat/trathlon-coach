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


def test_detail_client_returns_typed_payload_and_safe_rate_data():
    transport = StubTransport(StravaApiResponse(200, {"id": 42, "description": "Ride"}, {"X-ReadRateLimit-Usage": "2,20"}))
    client = StravaActivityClient(api_base_url="https://www.strava.com/api/v3", transport=transport)
    detail = asyncio.run(client.fetch_activity_detail(access_token=SecretStr("detail-secret"), external_activity_id="42"))
    assert detail.payload["id"] == 42
    assert detail.rate_limit.read_usage == (2, 20)
    url, headers, params, timeout = transport.calls[0]
    assert url.endswith("/activities/42") and params == {}
    assert headers["Authorization"] == "Bearer detail-secret" and timeout.response_seconds > 0
    assert "detail-secret" not in repr(detail)


@pytest.mark.parametrize("status_code", [401, 403, 500])
def test_detail_client_maps_authentication_and_temporary_errors(status_code):
    expected = AuthenticationError if status_code in {401, 403} else TemporaryProviderError
    client = StravaActivityClient(api_base_url="https://www.strava.com/api/v3", transport=StubTransport(StravaApiResponse(status_code, {"secret":"hidden"})))
    with pytest.raises(expected):
        asyncio.run(client.fetch_activity_detail(access_token=SecretStr("never-log"), external_activity_id="42"))


def test_lap_client_uses_selected_activity_resource():
    transport=StubTransport(StravaApiResponse(200,[{"lap_index":1}]))
    client=StravaActivityClient(api_base_url="https://www.strava.com/api/v3",transport=transport)
    result=asyncio.run(client.fetch_activity_laps(access_token=SecretStr("secret"),external_activity_id="42"))
    assert result.laps==({"lap_index":1},);assert transport.calls[0][0].endswith("/activities/42/laps")


def test_stream_client_requests_only_selected_types_keyed_by_type():
    transport=StubTransport(StravaApiResponse(200,{"time":{"data":[0,1]}}))
    client=StravaActivityClient(api_base_url="https://www.strava.com/api/v3",transport=transport)
    result=asyncio.run(client.fetch_activity_streams(access_token=SecretStr("secret"),external_activity_id="42",stream_types=("time","heartrate")))
    assert "time" in result.streams;assert transport.calls[0][2]=={"keys":"time,heartrate","key_by_type":"true"}
