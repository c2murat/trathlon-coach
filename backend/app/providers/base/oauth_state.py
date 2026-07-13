from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID


def utc_now() -> datetime:
    """Return the current timezone-aware UTC instant."""

    return datetime.now(timezone.utc)


def generate_oauth_state() -> str:
    """Generate an unpredictable OAuth state with at least 256 bits of entropy."""

    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class OAuthState:
    """A pending OAuth request bound to its initiating local user."""

    value: str
    user_id: UUID
    expires_at: datetime


class OAuthStateError(Exception):
    """Base class for failures that must reject an OAuth state."""


class OAuthStateMissingError(OAuthStateError):
    """The supplied state was never saved or is no longer available."""


class OAuthStateExpiredError(OAuthStateError):
    """The supplied state has passed its UTC expiry instant."""


class OAuthStateReusedError(OAuthStateError):
    """The supplied state has already been consumed successfully."""


class OAuthStateUserMismatchError(OAuthStateError):
    """The state belongs to a different initiating local user."""


class OAuthStateStorageError(OAuthStateError):
    """The state store could not persist a pending authorization request."""


class OAuthStateStore(ABC):
    """Persist and atomically consume short-lived OAuth CSRF state.

    Implementations must bind each unpredictable value to the initiating user
    and a UTC expiry, allow successful consumption exactly once, and reject
    unknown, expired, reused, or user-mismatched values. A production store must
    work across all API workers and instances.
    """

    @abstractmethod
    def save(self, state: OAuthState) -> None:
        """Persist one unconsumed state or raise :class:`OAuthStateStorageError`."""

    @abstractmethod
    def consume(self, state_value: str, *, user_id: UUID) -> OAuthState:
        """Atomically validate, remove, and return a state exactly once."""


class InMemoryOAuthStateStore(OAuthStateStore):
    """Thread-safe state store for one development/test Python process only.

    State is lost on restart and is not shared by multiple workers or hosts.
    This implementation is intentionally unsuitable for production deployments.
    """

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._clock = clock
        self._pending: dict[str, OAuthState] = {}
        self._consumed_until: dict[str, datetime] = {}
        self._lock = RLock()

    def save(self, state: OAuthState) -> None:
        if not state.value:
            raise OAuthStateStorageError("OAuth state must not be empty")
        if state.expires_at.tzinfo is None or state.expires_at.utcoffset() is None:
            raise OAuthStateStorageError("OAuth state expiry must be timezone-aware")

        with self._lock:
            self._prune()
            if state.value in self._pending or state.value in self._consumed_until:
                raise OAuthStateStorageError("OAuth state collision")
            self._pending[state.value] = state

    def consume(self, state_value: str, *, user_id: UUID) -> OAuthState:
        with self._lock:
            now = self._clock()
            self._prune(now)

            if state_value in self._consumed_until:
                raise OAuthStateReusedError("OAuth state was already consumed")

            state = self._pending.get(state_value)
            if state is None:
                raise OAuthStateMissingError("OAuth state was not found")
            if state.expires_at <= now:
                del self._pending[state_value]
                raise OAuthStateExpiredError("OAuth state expired")
            if state.user_id != user_id:
                raise OAuthStateUserMismatchError("OAuth state user mismatch")

            del self._pending[state_value]
            self._consumed_until[state_value] = state.expires_at
            return state

    def _prune(self, now: datetime | None = None) -> None:
        current = now or self._clock()
        self._consumed_until = {
            value: expiry
            for value, expiry in self._consumed_until.items()
            if expiry > current
        }

