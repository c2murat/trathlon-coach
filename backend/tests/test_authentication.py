from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.application.authentication import SessionAuthenticationError, UserAuthSessionService
from app.core.settings import Settings, get_settings
from app.db.base import Base, utc_now
from app.db.models import AthleteProfile, User, UserAthleteMembership, UserAuthSession
from app.db.session import get_db_session
from app.main import create_app
from app.security.passwords import hash_password, verify_password
from app.security.tokens import generate_secret_token, hash_secret_token, verify_secret_token


@pytest.fixture
def auth_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def add_user(session: Session, suffix: str = "a", status: str = "active") -> User:
    user = User(
        email=f"{suffix}@example.test",
        normalized_email=f"{suffix}@example.test",
        auth_subject=f"auth-{suffix}",
        status=status,
    )
    session.add(user)
    session.flush()
    return user


def test_password_hashing_uses_argon2_and_verifies() -> None:
    password = "correct horse battery staple"
    encoded = hash_password(password)
    assert encoded.startswith("$argon2")
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password("incorrect", encoded)


def test_password_verification_rejects_empty_and_malformed_hashes() -> None:
    assert not verify_password("password", "")
    assert not verify_password("password", "not-a-valid-hash")
    with pytest.raises(ValueError):
        hash_password("")


def test_tokens_are_random_and_hashes_are_deterministic() -> None:
    first = generate_secret_token()
    second = generate_secret_token()
    assert first != second
    assert len(first) >= 40
    assert hash_secret_token(first) == hash_secret_token(first)
    assert hash_secret_token(first) != first
    assert hash_secret_token(first) != hash_secret_token(second)
    assert verify_secret_token(first, hash_secret_token(first))
    assert not verify_secret_token(second, hash_secret_token(first))


def test_user_auth_session_creation_relationship_and_expiration(auth_session: Session) -> None:
    user = add_user(auth_session)
    now = utc_now()
    created = UserAuthSessionService(auth_session).create_session(
        user.id, ttl=timedelta(hours=2), now=now
    )
    stored = auth_session.get(UserAuthSession, created.session_id)
    assert stored is not None
    assert stored.user is user
    assert stored in user.auth_sessions
    assert stored.created_at == now
    assert stored.expires_at == now + timedelta(hours=2)
    assert stored.token_hash == hash_secret_token(created.session_token)
    assert stored.csrf_token_hash == hash_secret_token(created.csrf_token)
    assert created.session_token not in stored.token_hash
    assert created.csrf_token not in stored.csrf_token_hash
    assert created.session_token not in repr(created)
    assert created.csrf_token not in repr(created)


def test_session_token_hash_is_unique(auth_session: Session) -> None:
    user = add_user(auth_session)
    common_hash = hash_secret_token("same-token")
    auth_session.add_all([
        UserAuthSession(user=user, token_hash=common_hash, csrf_token_hash="a" * 64, expires_at=utc_now() + timedelta(hours=1)),
        UserAuthSession(user=user, token_hash=common_hash, csrf_token_hash="b" * 64, expires_at=utc_now() + timedelta(hours=1)),
    ])
    with pytest.raises(IntegrityError):
        auth_session.commit()


def test_valid_session_resolves_user(auth_session: Session) -> None:
    user = add_user(auth_session)
    created = UserAuthSessionService(auth_session).create_session(user.id, ttl=timedelta(days=1))
    assert UserAuthSessionService(auth_session).resolve_user(created.session_token) is user


@pytest.mark.parametrize("condition", ["missing", "expired", "revoked", "inactive"])
def test_invalid_session_conditions_are_rejected(auth_session: Session, condition: str) -> None:
    user = add_user(auth_session)
    service = UserAuthSessionService(auth_session)
    now = utc_now()
    created = service.create_session(user.id, ttl=timedelta(hours=1), now=now)
    token = created.session_token
    if condition == "missing":
        token = "unknown-session-token"
    elif condition == "expired":
        with pytest.raises(SessionAuthenticationError):
            service.resolve_user(token, now=now + timedelta(hours=1))
        return
    elif condition == "revoked":
        assert service.revoke_session(token, now=now)
    else:
        user.status = "disabled"
        auth_session.flush()
    with pytest.raises(SessionAuthenticationError):
        service.resolve_user(token, now=now)


def test_revocation_is_idempotent(auth_session: Session) -> None:
    user = add_user(auth_session)
    service = UserAuthSessionService(auth_session)
    created = service.create_session(user.id, ttl=timedelta(days=1))
    assert service.revoke_session(created.session_token)
    revoked_at = auth_session.get(UserAuthSession, created.session_id).revoked_at
    assert service.revoke_session(created.session_token)
    assert auth_session.get(UserAuthSession, created.session_id).revoked_at == revoked_at
    assert not service.revoke_session("missing-token")


def auth_client(session: Session, settings: Settings) -> TestClient:
    application = FastAPI()

    @application.get("/identity")
    def identity(user: AuthenticatedUser = Depends(get_current_user)):
        return {"user_id": str(user.id)}

    def database_override():
        yield session

    application.dependency_overrides[get_db_session] = database_override
    application.dependency_overrides[get_settings] = lambda: settings
    return TestClient(application)


def test_get_current_user_development_mode_preserves_fixed_identity(auth_session: Session) -> None:
    response = auth_client(auth_session, Settings(auth_mode="development", environment="test")).get("/identity")
    assert response.status_code == 200
    assert response.json()["user_id"] == "00000000-0000-4000-8000-000000000001"


def test_get_current_user_session_mode_accepts_valid_cookie(auth_session: Session) -> None:
    user = add_user(auth_session)
    created = UserAuthSessionService(auth_session).create_session(user.id, ttl=timedelta(days=1))
    response = auth_client(auth_session, Settings(auth_mode="session", environment="test")).get(
        "/identity", cookies={"tricoach_session": created.session_token}
    )
    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.id)}


@pytest.mark.parametrize("cookie", [None, "invalid-token"])
def test_get_current_user_session_mode_never_falls_back(auth_session: Session, cookie: str | None) -> None:
    client = auth_client(auth_session, Settings(auth_mode="session", environment="test"))
    response = client.get("/identity", cookies={"tricoach_session": cookie} if cookie else None)
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "authentication_required"}}


def test_session_identity_cannot_select_foreign_athlete(auth_session: Session) -> None:
    user = add_user(auth_session, "owner")
    other = add_user(auth_session, "other")
    owned = AthleteProfile(display_name="Test athlete")
    foreign = AthleteProfile(display_name="Test athlete")
    auth_session.add_all([owned, foreign])
    auth_session.flush()
    auth_session.add(UserAthleteMembership(user=user, athlete_profile=owned, role="owner", is_default=True))
    created = UserAuthSessionService(auth_session).create_session(user.id, ttl=timedelta(days=1))
    auth_session.commit()

    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: (yield auth_session)
    application.dependency_overrides[get_settings] = lambda: Settings(auth_mode="session", environment="test")
    client = TestClient(application)
    cookies = {"tricoach_session": created.session_token}
    assert client.get("/session/context", cookies=cookies).json()["selected_athlete_id"] == str(owned.id)
    response = client.get(
        "/activities", cookies=cookies, headers={"X-TriCoach-Athlete-Id": str(foreign.id)}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "athlete_not_authorized"
