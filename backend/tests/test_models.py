from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base, utc_now
from app.db.models import (
    AthleteProfile,
    AuditEvent,
    CompletedActivity,
    IntegrationAccount,
    OAuthCredential,
    SyncJob,
    User,
    WebhookEvent,
)


@pytest.fixture
def session() -> Session:
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
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_identity(session: Session, suffix: str = "1") -> tuple[User, AthleteProfile]:
    user = User(
        email=f"athlete{suffix}@example.com",
        normalized_email=f"athlete{suffix}@example.com",
        auth_subject=f"auth-{suffix}",
        timezone="Europe/Madrid",
    )
    athlete = AthleteProfile(user=user, timezone="Europe/Madrid", unit_system="metric")
    session.add_all([user, athlete])
    session.flush()
    return user, athlete


def make_integration(
    session: Session, athlete: AthleteProfile, external_id: str = "strava-athlete-1"
) -> IntegrationAccount:
    account = IntegrationAccount(
        athlete=athlete,
        provider="strava",
        external_account_id=external_id,
        status="active",
        scopes=["activity:read_all"],
    )
    session.add(account)
    session.flush()
    return account


def test_model_creation_and_utc_timestamps(session: Session) -> None:
    now = utc_now()
    user, athlete = make_identity(session)
    account = make_integration(session, athlete)
    credential = OAuthCredential(
        integration_account=account,
        access_token="unit-test-access-secret",
        refresh_token="unit-test-refresh-secret",
        scopes=["activity:read_all"],
        expires_at=now + timedelta(hours=6),
    )
    activity = CompletedActivity(
        athlete=athlete,
        source_integration_account=account,
        external_activity_id="activity-100",
        source_summary="strava",
        sport="cycling",
        name="Morning ride",
        start_at=now,
        timezone="Europe/Madrid",
        elapsed_time_s=3600,
        distance_m=30000,
    )
    sync_job = SyncJob(
        athlete=athlete,
        integration_account=account,
        job_type="historical_import",
        idempotency_key="history-2026-01",
    )
    webhook = WebhookEvent(
        integration_account=account,
        sync_job=sync_job,
        provider="strava",
        deduplication_key="event-1",
        event_type="activity.created",
        payload_hash="sha256:test",
        received_at=now,
    )
    audit = AuditEvent(
        actor=user,
        athlete=athlete,
        action="integration.connected",
        outcome="success",
        request_id="request-1",
        occurred_at=now,
    )
    session.add_all([credential, activity, sync_job, webhook, audit])
    session.commit()

    expected_tables = {
        "users",
        "athlete_profiles",
        "integration_accounts",
        "oauth_credentials",
        "completed_activities",
        "sync_jobs",
        "webhook_events",
        "audit_events",
        "activity_laps",
        "activity_streams",
        "activity_route_evidence",
        "activity_evidence_states",
        "activity_metrics",
        "athlete_performance_profile_versions",
        "athlete_performance_references",
    }
    assert set(Base.metadata.tables) == expected_tables
    assert activity.start_at.utcoffset() == timedelta(0)
    assert all(
        entity.created_at.utcoffset() == timedelta(0)
        for entity in (user, athlete, account, credential, activity, sync_job, webhook, audit)
    )


def test_uuid_primary_keys_are_generated(session: Session) -> None:
    user, athlete = make_identity(session)
    account = make_integration(session, athlete)

    assert isinstance(user.id, UUID)
    assert isinstance(athlete.id, UUID)
    assert isinstance(account.id, UUID)
    assert len({user.id, athlete.id, account.id}) == 3


def test_integration_external_identity_is_unique(session: Session) -> None:
    _, athlete = make_identity(session)
    make_integration(session, athlete)
    session.commit()

    duplicate = IntegrationAccount(
        athlete=athlete,
        provider="strava",
        external_account_id="strava-athlete-1",
        status="active",
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.commit()


def test_external_activity_identity_is_unique_per_integration(session: Session) -> None:
    _, athlete = make_identity(session)
    account = make_integration(session, athlete)
    now = utc_now()
    common = {
        "athlete": athlete,
        "source_integration_account": account,
        "external_activity_id": "strava-activity-9",
        "source_summary": "strava",
        "sport": "running",
        "start_at": now,
        "timezone": "Europe/Madrid",
        "elapsed_time_s": 1800,
    }
    session.add(CompletedActivity(name="First import", **common))
    session.commit()
    session.add(CompletedActivity(name="Duplicate import", **common))

    with pytest.raises(IntegrityError):
        session.commit()


def test_sync_job_idempotency_is_unique(session: Session) -> None:
    _, athlete = make_identity(session)
    account = make_integration(session, athlete)
    common = {
        "athlete": athlete,
        "integration_account": account,
        "job_type": "historical_import",
        "idempotency_key": "same-request",
    }
    session.add(SyncJob(**common))
    session.commit()
    session.add(SyncJob(**common))

    with pytest.raises(IntegrityError):
        session.commit()


def test_webhook_idempotency_key_is_unique_per_provider(session: Session) -> None:
    now = utc_now()
    session.add(
        WebhookEvent(
            provider="strava",
            deduplication_key="same-event",
            event_type="activity.updated",
            payload_hash="sha256:first",
            received_at=now,
        )
    )
    session.commit()
    session.add(
        WebhookEvent(
            provider="strava",
            deduplication_key="same-event",
            event_type="activity.updated",
            payload_hash="sha256:second",
            received_at=now,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_oauth_credential_repr_redacts_secrets() -> None:
    credential = OAuthCredential(
        access_token="access-super-secret",
        refresh_token="refresh-super-secret",
        expires_at=utc_now() + timedelta(hours=1),
    )

    rendered = repr(credential)
    assert "access-super-secret" not in rendered
    assert "refresh-super-secret" not in rendered
    assert "access_token" not in rendered
    assert "refresh_token" not in rendered

