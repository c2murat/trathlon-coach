from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import urlencode, urlsplit, urlunsplit

from pydantic import SecretStr

from app.providers.base import (
    AsyncHttpTransport,
    AuthenticationError,
    HttpBasicAuth,
    HttpTimeout,
    OAuthProvider,
    ProviderError,
    RateLimitError,
    TemporaryProviderError,
)
from app.providers.strava.oauth_types import (
    StravaRefreshCredential,
    StravaRefreshResult,
    StravaRevocationCredential,
    StravaTokenResult,
)


class StravaOAuthClient(OAuthProvider):
    """Build authorization URLs and exchange callback codes through a safe transport.

    Authorization-code exchange, token refresh, and revocation share one
    secret-safe transport. Secret-bearing form bodies and provider responses are
    never included in representations or logs.
    """

    provider_name = "strava"
    display_name = "Strava"
    supported_features = frozenset(
        {
            "oauth",
            "historical_activity_import",
            "activity_webhooks",
            "token_refresh",
        }
    )
    supported_activity_types = frozenset(
        {"swimming", "cycling", "running", "strength", "other"}
    )

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: SecretStr,
        authorization_url: str,
        token_url: str,
        revocation_url: str,
        transport: AsyncHttpTransport,
        timeout: HttpTimeout | None = None,
    ) -> None:
        if not client_id or not client_id.isdecimal() or int(client_id) <= 0:
            raise ValueError("Strava client ID must contain digits only")
        if not client_secret.get_secret_value():
            raise ValueError("Strava client secret must not be empty")
        _validate_https_provider_url(authorization_url, "authorization")
        _validate_https_provider_url(token_url, "token")
        _validate_https_provider_url(revocation_url, "revocation")

        self._client_id = client_id
        self._client_secret = client_secret
        self._authorization_url = authorization_url
        self._token_url = token_url
        self._revocation_url = revocation_url
        self._transport = transport
        self._timeout = timeout or HttpTimeout()

    def __repr__(self) -> str:
        return "<StravaOAuthClient provider='strava'>"

    def build_authorization_url(
        self,
        *,
        state: str,
        redirect_uri: str,
        scopes: Sequence[str],
    ) -> str:
        """Return a URL-encoded authorization URL without any client secret."""

        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "approval_prompt": "auto",
                "scope": ",".join(scopes),
                "state": state,
            }
        )
        parsed_url = urlsplit(self._authorization_url)
        return urlunsplit(parsed_url._replace(query=query))

    async def exchange_authorization_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> StravaTokenResult:
        """Exchange one validated code without retaining the raw response."""

        if not code:
            raise AuthenticationError("Authorization code is missing")
        # Strava's documented token request does not require redirect_uri. The
        # argument remains part of the provider-neutral interface for providers
        # that bind code exchange to the callback URI.
        del redirect_uri
        response = await self._transport.post_form(
            self._token_url,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=self._timeout,
        )

        if response.status_code == 200:
            return StravaTokenResult.from_payload(response.json_body)
        if response.status_code in {400, 401, 403}:
            raise AuthenticationError("Strava rejected the authorization exchange")
        if response.status_code == 429:
            raise RateLimitError("Strava token service rate limit reached")
        if response.status_code >= 500:
            raise TemporaryProviderError("Strava token service unavailable")
        raise ProviderError("Strava token exchange failed")

    async def refresh_authorization(self, authorization: object) -> object:
        """Refresh and rotate a Strava token set without exposing either token."""

        if not isinstance(authorization, StravaRefreshCredential):
            raise AuthenticationError("Strava refresh credential is invalid")
        response = await self._transport.post_form(
            self._token_url,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
                "grant_type": "refresh_token",
                "refresh_token": authorization.refresh_token.get_secret_value(),
            },
            timeout=self._timeout,
        )
        if response.status_code == 200:
            return StravaRefreshResult.from_payload(response.json_body)
        if response.status_code in {400, 401, 403}:
            raise AuthenticationError("Strava rejected token refresh")
        if response.status_code == 429:
            raise RateLimitError("Strava token refresh rate limit reached")
        if response.status_code >= 500:
            raise TemporaryProviderError("Strava token refresh unavailable")
        raise ProviderError("Strava token refresh failed")

    async def revoke_authorization(self, authorization: object) -> None:
        """Revoke one token without retaining or exposing provider response data."""

        if not isinstance(authorization, StravaRevocationCredential):
            raise AuthenticationError("Strava revocation credential is invalid")
        response = await self._transport.post_form(
            self._revocation_url,
            data={
                "token": authorization.access_token.get_secret_value(),
                "token_type_hint": "access_token",
            },
            timeout=self._timeout,
            basic_auth=HttpBasicAuth(
                username=self._client_id,
                password=self._client_secret,
            ),
        )
        if response.status_code == 200:
            return
        if response.status_code in {400, 401, 403}:
            raise AuthenticationError("Strava rejected authorization revocation")
        if response.status_code == 429 or response.status_code >= 500:
            raise TemporaryProviderError("Strava revocation service unavailable")
        raise ProviderError("Strava authorization revocation failed")

    def granted_scopes(self, authorization: object) -> Mapping[str, bool]:
        """Expose normalized scope presence for validated token results only."""

        if not isinstance(authorization, StravaTokenResult):
            return {}
        scopes = authorization.granted_scopes
        return {scope: True for scope in scopes.values} if scopes else {}


def _validate_https_provider_url(url: str, label: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(f"Strava {label} URL must be an HTTPS URL")
