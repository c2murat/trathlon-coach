from __future__ import annotations

import secrets
import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID


logger = logging.getLogger("uvicorn.error.oauth_state")
STATE_LOG_PREFIX_LENGTH = 8


def _state_prefix(value: str) -> str:
    return value[:STATE_LOG_PREFIX_LENGTH] if value else "<empty>"


def _diagnostic_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


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


class SQLiteOAuthStateStore(OAuthStateStore):
    """Durable development OAuth state store backed by one local SQLite file.

    Each operation owns its connection. Consumption uses ``BEGIN IMMEDIATE`` so
    validation and the unconsumed-to-consumed transition are atomic across
    threads, processes, and distinct store instances sharing the file.
    PostgreSQL or Redis must replace this development adapter in production.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], datetime] = utc_now,
        timeout_seconds: float = 5.0,
        diagnostics_enabled: bool = False,
        application_instance_id: str = "unassigned",
    ) -> None:
        self._database_path = Path(database_path).resolve()
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._diagnostics_enabled = diagnostics_enabled
        self._application_instance_id = application_instance_id
        if self._diagnostics_enabled:
            logger.setLevel(logging.INFO)
            logging.getLogger("uvicorn.access").disabled = True
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def save(self, state: OAuthState) -> None:
        if not state.value:
            raise OAuthStateStorageError("OAuth state must not be empty")
        if state.expires_at.tzinfo is None or state.expires_at.utcoffset() is None:
            raise OAuthStateStorageError("OAuth state expiry must be timezone-aware")

        now = self._aware_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM oauth_state WHERE expires_at <= ?",
                (now.timestamp(),),
            )
            try:
                connection.execute(
                    """
                    INSERT INTO oauth_state (
                        state, user_id, created_at, expires_at, consumed_at
                    ) VALUES (?, ?, ?, ?, NULL)
                    """,
                    (
                        state.value,
                        str(state.user_id),
                        now.timestamp(),
                        state.expires_at.astimezone(timezone.utc).timestamp(),
                    ),
                )
            except sqlite3.IntegrityError:
                connection.rollback()
                self._diagnostic(
                    state_prefix=_state_prefix(state.value),
                    lookup_result="consumed",
                    consume_result="rejected",
                )
                raise OAuthStateStorageError("OAuth state collision") from None
            stored_count = self._pending_count(connection, now)
            connection.commit()
            self._diagnostic(
                state_prefix=_state_prefix(state.value),
                stored_row_count=stored_count,
                created_at=now,
                expires_at=state.expires_at,
                lookup_result="found",
                consume_result="not_attempted",
            )
        except OAuthStateError:
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise OAuthStateStorageError("OAuth state storage unavailable") from exc
        finally:
            connection.close()

    def consume(self, state_value: str, *, user_id: UUID) -> OAuthState:
        now = self._aware_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT state, user_id, created_at, expires_at, consumed_at
                FROM oauth_state
                WHERE state = ?
                """,
                (state_value,),
            ).fetchone()
            connection.execute(
                "DELETE FROM oauth_state WHERE expires_at <= ? AND state <> ?",
                (now.timestamp(), state_value),
            )
            stored_count = self._pending_count(connection, now)
            if row is None:
                self._log_lookup(
                    state_value,
                    stored_count=stored_count,
                    lookup_result="missing",
                    consume_result="rejected",
                )
                connection.commit()
                raise OAuthStateMissingError("OAuth state was not found")

            created_at = datetime.fromtimestamp(row[2], tz=timezone.utc)
            expires_at = datetime.fromtimestamp(row[3], tz=timezone.utc)
            if expires_at <= now:
                self._log_lookup(
                    state_value,
                    stored_count=stored_count,
                    created_at=created_at,
                    expires_at=expires_at,
                    lookup_result="expired",
                    consume_result="rejected",
                )
                connection.execute(
                    "DELETE FROM oauth_state WHERE state = ?", (state_value,)
                )
                connection.commit()
                raise OAuthStateExpiredError("OAuth state expired")
            if row[4] is not None:
                self._log_lookup(
                    state_value,
                    stored_count=stored_count,
                    created_at=created_at,
                    expires_at=expires_at,
                    lookup_result="consumed",
                    consume_result="rejected",
                )
                connection.commit()
                raise OAuthStateReusedError("OAuth state was already consumed")
            if row[1] != str(user_id):
                self._log_lookup(
                    state_value,
                    stored_count=stored_count,
                    created_at=created_at,
                    expires_at=expires_at,
                    lookup_result="user_mismatch",
                    consume_result="rejected",
                )
                connection.commit()
                raise OAuthStateUserMismatchError("OAuth state user mismatch")

            self._log_lookup(
                state_value,
                stored_count=stored_count,
                created_at=created_at,
                expires_at=expires_at,
                lookup_result="found",
                consume_result="pending",
            )
            updated = connection.execute(
                """
                UPDATE oauth_state
                SET consumed_at = ?
                WHERE state = ? AND consumed_at IS NULL
                """,
                (now.timestamp(), state_value),
            )
            if updated.rowcount != 1:
                connection.rollback()
                self._log_lookup(
                    state_value,
                    stored_count=stored_count,
                    created_at=created_at,
                    expires_at=expires_at,
                    lookup_result="consumed",
                    consume_result="rejected",
                )
                raise OAuthStateReusedError("OAuth state was already consumed")
            connection.commit()
            self._log_lookup(
                state_value,
                stored_count=max(stored_count - 1, 0),
                created_at=created_at,
                expires_at=expires_at,
                lookup_result="found",
                consume_result="success",
            )
            return OAuthState(
                value=row[0],
                user_id=UUID(row[1]),
                expires_at=expires_at,
            )
        except OAuthStateError:
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise OAuthStateStorageError("OAuth state storage unavailable") from exc
        finally:
            connection.close()

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_state (
                    state TEXT PRIMARY KEY NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    consumed_at REAL NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_oauth_state_expires_at
                ON oauth_state (expires_at)
                """
            )
            stored_count = self._pending_count(connection, self._aware_now())
            connection.commit()
            self._diagnostic(stored_row_count=stored_count)
        except sqlite3.Error as exc:
            raise OAuthStateStorageError("OAuth state storage unavailable") from exc
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(
            self._database_path,
            timeout=self._timeout_seconds,
            isolation_level=None,
        )

    def _aware_now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise OAuthStateStorageError("OAuth state clock must be timezone-aware")
        return now.astimezone(timezone.utc)

    @staticmethod
    def _pending_count(connection: sqlite3.Connection, now: datetime) -> int:
        row = connection.execute(
            """
            SELECT COUNT(*) FROM oauth_state
            WHERE consumed_at IS NULL AND expires_at > ?
            """,
            (now.timestamp(),),
        ).fetchone()
        return int(row[0])

    def log_public_error(
        self,
        *,
        state_value: str | None,
        public_error_code: str,
    ) -> None:
        """Log one redacted callback error when safe diagnostics are enabled."""

        self._diagnostic(
            callback_state_prefix=_state_prefix(state_value or ""),
            public_error_code=public_error_code,
        )

    def _log_lookup(
        self,
        state_value: str,
        *,
        stored_count: int,
        lookup_result: str,
        consume_result: str,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        self._diagnostic(
            callback_state_prefix=_state_prefix(state_value),
            stored_row_count=stored_count,
            created_at=created_at,
            expires_at=expires_at,
            lookup_result=lookup_result,
            consume_result=consume_result,
        )

    def _diagnostic(
        self,
        *,
        state_prefix: str | None = None,
        callback_state_prefix: str | None = None,
        stored_row_count: int | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        lookup_result: str | None = None,
        consume_result: str | None = None,
        public_error_code: str | None = None,
    ) -> None:
        if not self._diagnostics_enabled:
            return
        logger.info(
            "oauth_state_diagnostic process_id=%s application_instance_id=%s "
            "database_path=%s state_prefix=%s stored_row_count=%s "
            "created_at=%s expires_at=%s callback_state_prefix=%s "
            "lookup_result=%s consume_result=%s public_error_code=%s",
            os.getpid(),
            self._application_instance_id,
            self._database_path,
            state_prefix,
            stored_row_count,
            _diagnostic_timestamp(created_at),
            _diagnostic_timestamp(expires_at),
            callback_state_prefix,
            lookup_result,
            consume_result,
            public_error_code,
        )


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
