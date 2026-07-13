from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import SecretStr

from app.providers.base import InvalidPayloadError


@dataclass(frozen=True, slots=True)
class GrantedScopes:
    """Normalized, non-secret OAuth scopes granted by Strava."""

    values: tuple[str, ...]

    @classmethod
    def parse(cls, value: str | Iterable[str] | None) -> GrantedScopes | None:
        if value is None:
            return None
        raw_values = value.replace(",", " ").split() if isinstance(value, str) else value
        normalized = tuple(
            sorted({scope.strip() for scope in raw_values if scope and scope.strip()})
        )
        return cls(values=normalized)

    def has_required_read_only(self, required: Iterable[str]) -> bool:
        required_set = set(required)
        value_set = set(self.values)
        return required_set.issubset(value_set) and not any(
            "write" in scope for scope in value_set
        )


@dataclass(frozen=True, slots=True)
class StravaAthleteIdentity:
    """Validated external athlete identity returned by Strava."""

    external_id: str
    display_name: str | None = None

    @classmethod
    def from_payload(cls, payload: object) -> StravaAthleteIdentity:
        if not isinstance(payload, Mapping):
            raise InvalidPayloadError("Token response athlete is invalid")
        raw_id = payload.get("id")
        if isinstance(raw_id, bool):
            raise InvalidPayloadError("Token response athlete identifier is invalid")
        external_id = str(raw_id).strip() if isinstance(raw_id, (int, str)) else ""
        if not external_id.isdecimal() or int(external_id) <= 0:
            raise InvalidPayloadError("Token response athlete identifier is invalid")

        names = [payload.get("firstname"), payload.get("lastname")]
        display_name = " ".join(
            name.strip() for name in names if isinstance(name, str) and name.strip()
        ) or None
        return cls(external_id=external_id, display_name=display_name)


@dataclass(frozen=True, slots=True)
class StravaTokenResult:
    """Validated secret-safe internal result of a Strava token exchange."""

    access_token: SecretStr = field(repr=False)
    refresh_token: SecretStr = field(repr=False)
    expires_at: datetime
    expires_in: int | None
    token_type: str
    athlete: StravaAthleteIdentity
    granted_scopes: GrantedScopes | None

    @classmethod
    def from_payload(cls, payload: object) -> StravaTokenResult:
        if not isinstance(payload, Mapping):
            raise InvalidPayloadError("Token response is invalid")

        access_token = _required_secret(payload, "access_token")
        refresh_token = _required_secret(payload, "refresh_token")
        expires_at_value = payload.get("expires_at")
        if isinstance(expires_at_value, bool) or not isinstance(expires_at_value, int):
            raise InvalidPayloadError("Token response expiry is invalid")
        try:
            expires_at = datetime.fromtimestamp(expires_at_value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise InvalidPayloadError("Token response expiry is invalid") from None
        if expires_at <= datetime.now(timezone.utc):
            raise InvalidPayloadError("Token response expiry is invalid")

        expires_in_value = payload.get("expires_in")
        if expires_in_value is not None and (
            isinstance(expires_in_value, bool)
            or not isinstance(expires_in_value, int)
            or expires_in_value < 0
        ):
            raise InvalidPayloadError("Token response lifetime is invalid")

        token_type_value = payload.get("token_type", "Bearer")
        if not isinstance(token_type_value, str) or not token_type_value.strip():
            raise InvalidPayloadError("Token response type is invalid")

        scope_value = payload.get("scope")
        if scope_value is not None and not isinstance(scope_value, (str, list, tuple)):
            raise InvalidPayloadError("Token response scopes are invalid")

        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            expires_in=expires_in_value,
            token_type=token_type_value.strip(),
            athlete=StravaAthleteIdentity.from_payload(payload.get("athlete")),
            granted_scopes=GrantedScopes.parse(scope_value),
        )

    def __repr__(self) -> str:
        return (
            "<StravaTokenResult access_token=<redacted> "
            "refresh_token=<redacted> "
            f"expires_at={self.expires_at!r} athlete={self.athlete!r}>"
        )


@dataclass(frozen=True, slots=True)
class StravaRevocationCredential:
    """One secret token used transiently for remote authorization revocation."""

    access_token: SecretStr = field(repr=False)

    def __repr__(self) -> str:
        return "<StravaRevocationCredential access_token=<redacted>>"


@dataclass(frozen=True, slots=True)
class StravaRefreshCredential:
    """Refresh token passed only to the OAuth refresh boundary."""

    refresh_token: SecretStr = field(repr=False)

    def __repr__(self) -> str:
        return "<StravaRefreshCredential refresh_token=<redacted>>"


@dataclass(frozen=True, slots=True)
class StravaRefreshResult:
    """Validated rotated token set returned by a refresh request."""

    access_token: SecretStr = field(repr=False)
    refresh_token: SecretStr = field(repr=False)
    expires_at: datetime
    token_type: str

    @classmethod
    def from_payload(cls, payload: object) -> StravaRefreshResult:
        if not isinstance(payload, Mapping):
            raise InvalidPayloadError("Refresh response is invalid")
        expires_at_value = payload.get("expires_at")
        if isinstance(expires_at_value, bool) or not isinstance(expires_at_value, int):
            raise InvalidPayloadError("Refresh response expiry is invalid")
        try:
            expires_at = datetime.fromtimestamp(expires_at_value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise InvalidPayloadError("Refresh response expiry is invalid") from None
        if expires_at <= datetime.now(timezone.utc):
            raise InvalidPayloadError("Refresh response expiry is invalid")
        token_type = payload.get("token_type", "Bearer")
        if not isinstance(token_type, str) or not token_type.strip():
            raise InvalidPayloadError("Refresh response type is invalid")
        return cls(
            access_token=_required_secret(payload, "access_token"),
            refresh_token=_required_secret(payload, "refresh_token"),
            expires_at=expires_at,
            token_type=token_type.strip(),
        )

    def __repr__(self) -> str:
        return (
            "<StravaRefreshResult access_token=<redacted> "
            "refresh_token=<redacted> "
            f"expires_at={self.expires_at!r}>"
        )


def _required_secret(payload: Mapping[object, object], field_name: str) -> SecretStr:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise InvalidPayloadError(f"Token response {field_name.replace('_', ' ')} is missing")
    return SecretStr(value)
