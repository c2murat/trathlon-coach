from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import SecretStr

from app.providers.base.exceptions import TemporaryProviderError


@dataclass(frozen=True, slots=True)
class HttpTimeout:
    """Explicit connect and response timeout values for one provider request."""

    connect_seconds: float = 5.0
    response_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Minimal provider response whose body is intentionally excluded from repr."""

    status_code: int
    json_body: Any = field(repr=False)


@dataclass(frozen=True, slots=True)
class HttpBasicAuth:
    """Secret-safe HTTP Basic credentials for a provider request."""

    username: str = field(repr=False)
    password: SecretStr = field(repr=False)

    def __repr__(self) -> str:
        return "<HttpBasicAuth credentials=<redacted>>"


class AsyncHttpTransport(ABC):
    """Small replaceable async form-POST boundary for OAuth token exchange.

    Implementations must not log form bodies or authorization headers because
    these can contain application secrets, authorization codes, and tokens.
    """

    @abstractmethod
    async def post_form(
        self,
        url: str,
        *,
        data: dict[str, str],
        timeout: HttpTimeout,
        basic_auth: HttpBasicAuth | None = None,
    ) -> HttpResponse:
        """POST form data and return a parsed minimal response."""


class HttpxAsyncTransport(AsyncHttpTransport):
    """Production async transport using httpx with bounded explicit timeouts."""

    async def post_form(
        self,
        url: str,
        *,
        data: dict[str, str],
        timeout: HttpTimeout,
        basic_auth: HttpBasicAuth | None = None,
    ) -> HttpResponse:
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
                auth = (
                    (basic_auth.username, basic_auth.password.get_secret_value())
                    if basic_auth is not None
                    else None
                )
                response = await client.post(url, data=data, auth=auth)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TemporaryProviderError("Provider token service unavailable") from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        return HttpResponse(status_code=response.status_code, json_body=body)
