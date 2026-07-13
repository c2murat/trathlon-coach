from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.cli.seed_development_user import (
    DEVELOPMENT_AUTH_SUBJECT,
    DEVELOPMENT_EMAIL,
    DEVELOPMENT_TIMEZONE,
    seed_development_user,
)
from app.cli import seed_development_user as seed_module
from app.db.base import Base
from app.db.models import AthleteProfile, User


@pytest.fixture
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        del connection_record
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_first_execution_creates_user_and_profile(session_factory) -> None:
    with session_factory() as session:
        result = seed_development_user(session)

    assert result.user_created is True
    assert result.athlete_profile_created is True
    with session_factory() as verification:
        user = verification.get(User, LOCAL_MVP_USER_ID)
        profile = verification.scalar(
            select(AthleteProfile).where(
                AthleteProfile.user_id == LOCAL_MVP_USER_ID
            )
        )
        assert user is not None
        assert user.email == DEVELOPMENT_EMAIL
        assert user.normalized_email == DEVELOPMENT_EMAIL
        assert user.auth_subject == DEVELOPMENT_AUTH_SUBJECT
        assert user.timezone == DEVELOPMENT_TIMEZONE
        assert profile is not None
        assert profile.timezone == DEVELOPMENT_TIMEZONE
        assert profile.unit_system == "metric"


def test_repeated_execution_does_not_create_duplicates(session_factory) -> None:
    with session_factory() as session:
        first = seed_development_user(session)
        second = seed_development_user(session)

    assert first.user_created is True
    assert first.athlete_profile_created is True
    assert second.user_created is False
    assert second.athlete_profile_created is False
    with session_factory() as verification:
        assert verification.scalar(select(func.count()).select_from(User)) == 1
        assert (
            verification.scalar(
                select(func.count()).select_from(AthleteProfile)
            )
            == 1
        )


def test_existing_user_without_profile_creates_only_profile(session_factory) -> None:
    with session_factory() as session:
        session.add(
            User(
                id=LOCAL_MVP_USER_ID,
                email=DEVELOPMENT_EMAIL,
                normalized_email=DEVELOPMENT_EMAIL,
                auth_subject=DEVELOPMENT_AUTH_SUBJECT,
                timezone=DEVELOPMENT_TIMEZONE,
            )
        )
        session.commit()

        result = seed_development_user(session)

    assert result.user_created is False
    assert result.athlete_profile_created is True
    with session_factory() as verification:
        assert verification.scalar(select(func.count()).select_from(User)) == 1
        profile = verification.scalar(select(AthleteProfile))
        assert profile is not None
        assert profile.user_id == LOCAL_MVP_USER_ID


def test_seed_uses_fixed_local_mvp_uuid(session_factory) -> None:
    assert str(LOCAL_MVP_USER_ID) == "00000000-0000-4000-8000-000000000001"

    with session_factory() as session:
        seed_development_user(session)

    with session_factory() as verification:
        user = verification.scalar(select(User))
        profile = verification.scalar(select(AthleteProfile))
        assert user is not None
        assert profile is not None
        assert user.id == LOCAL_MVP_USER_ID
        assert profile.user_id == LOCAL_MVP_USER_ID


def test_seed_rolls_back_entire_transaction_on_failure(session_factory) -> None:
    with session_factory() as session:

        @event.listens_for(session, "before_flush")
        def fail_seed_flush(
            database_session, flush_context, instances
        ) -> None:
            del database_session, flush_context, instances
            raise RuntimeError("simulated seed failure")

        with pytest.raises(RuntimeError, match="simulated seed failure"):
            seed_development_user(session)

        assert session.in_transaction() is False

    with session_factory() as verification:
        assert verification.scalar(select(func.count()).select_from(User)) == 0
        assert (
            verification.scalar(
                select(func.count()).select_from(AthleteProfile)
            )
            == 0
        )


def test_cli_refuses_non_development_environment(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        seed_module,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )

    exit_code = seed_module.main()

    assert exit_code == 2
    assert "refused" in capsys.readouterr().err
