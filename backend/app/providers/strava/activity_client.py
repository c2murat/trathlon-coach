from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import SecretStr

from app.providers.base import (
    AuthenticationError,
    HttpTimeout,
    InvalidPayloadError,
    ProviderError,
    TemporaryProviderError,
)


@dataclass(frozen=True, slots=True)
class StravaApiResponse:
    """Minimal HTTP response with its provider body excluded from repr."""

    status_code: int
    json_body: object = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


class StravaActivityTransport(Protocol):
    """Mockable authenticated GET boundary for Strava resource requests."""

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, int],
        timeout: HttpTimeout,
    ) -> StravaApiResponse:
        """Return one parsed response without logging headers or payloads."""


class HttpxStravaActivityTransport:
    """HTTPX transport with bounded timeouts and no secret-bearing logging."""

    async def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, int],
        timeout: HttpTimeout,
    ) -> StravaApiResponse:
        httpx_timeout = httpx.Timeout(
            connect=timeout.connect_seconds,
            read=timeout.response_seconds,
            write=timeout.response_seconds,
            pool=timeout.connect_seconds,
        )
        try:
            async with httpx.AsyncClient(
                timeout=httpx_timeout, follow_redirects=False
            ) as client:
                response = await client.get(
                    url,
                    headers=dict(headers),
                    params=dict(params),
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TemporaryProviderError("Strava activity service unavailable") from exc
        try:
            body: object = response.json()
        except ValueError:
            body = None
        return StravaApiResponse(
            status_code=response.status_code,
            json_body=body,
            headers=dict(response.headers),
        )


@dataclass(frozen=True, slots=True)
class StravaRateLimitSnapshot:
    """Numeric rate observations safe to retain without request credentials."""

    general_limit: tuple[int, int] | None
    general_usage: tuple[int, int] | None
    read_limit: tuple[int, int] | None
    read_usage: tuple[int, int] | None


@dataclass(frozen=True, slots=True)
class StravaActivityPage:
    """One activity-summary page and its safe rate observations."""

    activities: tuple[object, ...]
    rate_limit: StravaRateLimitSnapshot


class StravaActivityRateLimitError(TemporaryProviderError):
    """A rate response carrying only a safe retry delay and numeric observations."""

    def __init__(
        self,
        *,
        retry_after_seconds: int | None,
        rate_limit: StravaRateLimitSnapshot,
    ) -> None:
        super().__init__("Strava activity rate limit reached")
        self.retry_after_seconds = retry_after_seconds
        self.rate_limit = rate_limit


class StravaActivityClient:
    """Fetch paginated athlete activity summaries from Strava."""

    def __init__(
        self,
        *,
        api_base_url: str,
        transport: StravaActivityTransport,
        timeout: HttpTimeout | None = None,
    ) -> None:
        self._api_base_url = api_base_url.rstrip("/")
        if not self._api_base_url.startswith("https://"):
            raise ValueError("Strava API base URL must use HTTPS")
        self._transport = transport
        self._timeout = timeout or HttpTimeout()

    async def fetch_activity_summaries(
        self,
        *,
        access_token: SecretStr,
        page: int,
        per_page: int = 100,
        after: int | None = None,
        before: int | None = None,
    ) -> StravaActivityPage:
        if page < 1 or not 1 <= per_page <= 200:
            raise ValueError("Invalid Strava activity pagination")
        params = {"page": page, "per_page": per_page}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        response = await self._transport.get_json(
            f"{self._api_base_url}/athlete/activities",
            headers={
                "Authorization": f"Bearer {access_token.get_secret_value()}",
                "Accept": "application/json",
            },
            params=params,
            timeout=self._timeout,
        )
        rate_limit = _parse_rate_headers(response.headers)
        if response.status_code == 200:
            if not isinstance(response.json_body, list):
                raise InvalidPayloadError("Strava activity page is invalid")
            return StravaActivityPage(
                activities=tuple(response.json_body),
                rate_limit=rate_limit,
            )
        if response.status_code in {401, 403}:
            raise AuthenticationError("Strava activity authorization rejected")
        if response.status_code == 429:
            raise StravaActivityRateLimitError(
                retry_after_seconds=_positive_int(
                    _header(response.headers, "retry-after")
                ),
                rate_limit=rate_limit,
            )
        if response.status_code >= 500:
            raise TemporaryProviderError("Strava activity service unavailable")
        raise ProviderError("Strava activity request failed")

    def __repr__(self) -> str:
        return "<StravaActivityClient provider='strava'>"


def _parse_rate_headers(headers: Mapping[str, str]) -> StravaRateLimitSnapshot:
    return StravaRateLimitSnapshot(
        general_limit=_pair(_header(headers, "x-ratelimit-limit")),
        general_usage=_pair(_header(headers, "x-ratelimit-usage")),
        read_limit=_pair(_header(headers, "x-readratelimit-limit")),
        read_usage=_pair(_header(headers, "x-readratelimit-usage")),
    )


def _header(headers: Mapping[str, str], name: str) -> str | None:
    normalized = name.lower()
    for key, value in headers.items():
        if key.lower() == normalized:
            return value
    return None


def _pair(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    parts = value.split(",")
    if len(parts) != 2:
        return None
    parsed = tuple(_positive_or_zero(part.strip()) for part in parts)
    if any(item is None for item in parsed):
        return None
    return parsed[0], parsed[1]  # type: ignore[return-value]


def _positive_int(value: str | None) -> int | None:
    parsed = _positive_or_zero(value)
    return parsed if parsed and parsed > 0 else None


def _positive_or_zero(value: str | None) -> int | None:
    if value is None or not value.isdecimal():
        return None
    return int(value)
