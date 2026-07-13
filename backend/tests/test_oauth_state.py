from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from uuid import uuid4

import pytest

from app.providers.base import (
    InMemoryOAuthStateStore,
    OAuthState,
    OAuthStateExpiredError,
    OAuthStateMissingError,
    OAuthStateReusedError,
    OAuthStateUserMismatchError,
    SQLiteOAuthStateStore,
    generate_oauth_state,
)


def test_generated_oauth_states_are_unique_and_unpredictable_length() -> None:
    states = {generate_oauth_state() for _ in range(100)}

    assert len(states) == 100
    assert all(len(state) >= 43 for state in states)


def test_state_is_bound_to_user_and_consumed_once() -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    state = OAuthState(
        value=generate_oauth_state(),
        user_id=user_id,
        expires_at=now + timedelta(minutes=10),
    )
    store = InMemoryOAuthStateStore(clock=lambda: now)
    store.save(state)

    assert store.consume(state.value, user_id=user_id) == state
    with pytest.raises(OAuthStateReusedError):
        store.consume(state.value, user_id=user_id)


def test_state_rejects_wrong_user_without_consuming_it() -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    owner_id = uuid4()
    state = OAuthState(
        value=generate_oauth_state(),
        user_id=owner_id,
        expires_at=now + timedelta(minutes=10),
    )
    store = InMemoryOAuthStateStore(clock=lambda: now)
    store.save(state)

    with pytest.raises(OAuthStateUserMismatchError):
        store.consume(state.value, user_id=uuid4())
    assert store.consume(state.value, user_id=owner_id) == state


def test_state_rejects_expired_and_missing_values() -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    user_id = uuid4()
    store = InMemoryOAuthStateStore(clock=lambda: now)
    store.save(
        OAuthState(
            value="expired-state",
            user_id=user_id,
            expires_at=now - timedelta(seconds=1),
        )
    )

    with pytest.raises(OAuthStateExpiredError):
        store.consume("expired-state", user_id=user_id)
    with pytest.raises(OAuthStateMissingError):
        store.consume("unknown-state", user_id=user_id)


def test_sqlite_state_persists_across_store_instances(tmp_path) -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    database_path = tmp_path / "oauth-state.sqlite3"
    user_id = uuid4()
    state = OAuthState(
        value=generate_oauth_state(),
        user_id=user_id,
        expires_at=now + timedelta(minutes=10),
    )

    SQLiteOAuthStateStore(database_path, clock=lambda: now).save(state)
    restarted_store = SQLiteOAuthStateStore(database_path, clock=lambda: now)

    assert restarted_store.consume(state.value, user_id=user_id) == state
    with pytest.raises(OAuthStateReusedError):
        SQLiteOAuthStateStore(database_path, clock=lambda: now).consume(
            state.value, user_id=user_id
        )


def test_sqlite_state_is_user_bound_without_consuming_on_mismatch(tmp_path) -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    store = SQLiteOAuthStateStore(tmp_path / "state.sqlite3", clock=lambda: now)
    owner_id = uuid4()
    state = OAuthState(
        value=generate_oauth_state(),
        user_id=owner_id,
        expires_at=now + timedelta(minutes=10),
    )
    store.save(state)

    with pytest.raises(OAuthStateUserMismatchError):
        store.consume(state.value, user_id=uuid4())
    assert store.consume(state.value, user_id=owner_id) == state


def test_sqlite_expired_state_is_rejected_and_deleted(tmp_path) -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    database_path = tmp_path / "state.sqlite3"
    store = SQLiteOAuthStateStore(database_path, clock=lambda: now)
    state = OAuthState(
        value="expired-sqlite-state",
        user_id=uuid4(),
        expires_at=now - timedelta(seconds=1),
    )
    store.save(state)

    with pytest.raises(OAuthStateExpiredError):
        store.consume(state.value, user_id=state.user_id)
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT state FROM oauth_state WHERE state = ?", (state.value,)
        ).fetchone()
    assert row is None


def test_sqlite_consume_is_atomic_across_store_instances(tmp_path) -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    database_path = tmp_path / "state.sqlite3"
    user_id = uuid4()
    state = OAuthState(
        value=generate_oauth_state(),
        user_id=user_id,
        expires_at=now + timedelta(minutes=10),
    )
    SQLiteOAuthStateStore(database_path, clock=lambda: now).save(state)

    def consume_once() -> str:
        store = SQLiteOAuthStateStore(database_path, clock=lambda: now)
        try:
            store.consume(state.value, user_id=user_id)
            return "success"
        except OAuthStateReusedError:
            return "reused"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(consume_once) for _ in range(2)]
        outcomes = [future.result(timeout=2) for future in futures]

    assert sorted(outcomes) == ["reused", "success"]


def test_sqlite_save_and_consume_complete_without_deadlock(tmp_path) -> None:
    now = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)
    store = SQLiteOAuthStateStore(tmp_path / "state.sqlite3", clock=lambda: now)
    state = OAuthState(
        value=generate_oauth_state(),
        user_id=uuid4(),
        expires_at=now + timedelta(minutes=10),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(store.save, state).result(timeout=2)
        consumed = executor.submit(
            store.consume,
            state.value,
            user_id=state.user_id,
        ).result(timeout=2)

    assert consumed == state


def test_sqlite_schema_contains_required_state_fields(tmp_path) -> None:
    database_path = tmp_path / "state.sqlite3"
    SQLiteOAuthStateStore(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(oauth_state)")
        }

    assert columns == {
        "state",
        "user_id",
        "created_at",
        "expires_at",
        "consumed_at",
    }
