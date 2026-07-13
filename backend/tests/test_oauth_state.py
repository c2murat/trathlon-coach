from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.providers.base import (
    InMemoryOAuthStateStore,
    OAuthState,
    OAuthStateExpiredError,
    OAuthStateMissingError,
    OAuthStateReusedError,
    OAuthStateUserMismatchError,
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

