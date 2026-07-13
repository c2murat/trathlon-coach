from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base, utc_now
from app.db.models import (
    AthleteProfile,
    CompletedActivity,
    IntegrationAccount,
    OAuthCredential,
    SyncJob,
    User,
)
from app.integrations.strava.activity_import import (
    ImportJobNotFoundError,
    StravaSummaryImportManager,
)
from app.integrations.strava.token_service import StravaTokenService
from app.providers.base import AuthenticationError, TemporaryProviderError
from app.providers.strava import StravaRefreshResult
from app.providers.strava.activity_client import (
    StravaActivityPage,
    StravaActivityRateLimitError,
    StravaRateLimitSnapshot,
)
from app.providers.strava.activity_mapper import StravaActivityMapper


EMPTY_RATE = StravaRateLimitSnapshot(None, None, None, None)


def activity(activity_id: int, **overrides):
    value = {
        "id": activity_id,
        "athlete": {"id": 456},
        "name": f"Activity {activity_id}",
        "sport_type": "Run",
        "start_date": "2026-07-01T06:00:00Z",
        "elapsed_time": 600,
        "moving_time": 580,
        "distance": 2000.0,
    }
    value.update(overrides)
    return value


class FakeTokenService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def access_token(self, integration_account_id):
        del integration_account_id
        self.calls += 1
        if self.error:
            raise self.error
        return SecretStr("stored-access-secret")


class FakeActivityClient:
    def __init__(self, pages=(), error: Exception | None = None) -> None:
        self.pages = list(pages)
        self.error = error
        self.calls = []

    async def fetch_activity_summaries(self, **kwargs):
        self.calls.append({key: value for key, value in kwargs.items() if key != "access_token"})
        if self.error:
            raise self.error
        return self.pages.pop(0) if self.pages else StravaActivityPage((), EMPTY_RATE)


class FakeRefreshClient:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.seen_refresh = None

    async def refresh_authorization(self, credential):
        self.seen_refresh = credential.refresh_token.get_secret_value()
        if self.error:
            raise self.error
        return self.result


class FailOnActivityMapper:
    def __init__(self, external_id: int) -> None:
        self.external_id = external_id
        self.delegate = StravaActivityMapper()

    def map_summary(self, payload, **kwargs):
        if payload["id"] == self.external_id:
            raise OperationalError("provider upsert", {}, RuntimeError("database"))
        return self.delegate.map_summary(payload, **kwargs)


@pytest.fixture
def database(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'import.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = utc_now()
    with factory() as session:
        user = User(
            email="local@example.invalid",
            normalized_email="local@example.invalid",
            auth_subject="local-user",
            timezone="Europe/Madrid",
        )
        athlete = AthleteProfile(
            user=user, timezone="Europe/Madrid", unit_system="metric"
        )
        account = IntegrationAccount(
            athlete=athlete,
            provider="strava",
            external_account_id="456",
            status="active",
            scopes=["read", "activity:read_all"],
        )
        credential = OAuthCredential(
            integration_account=account,
            access_token="stored-access-secret",
            refresh_token="stored-refresh-secret",
            expires_at=now + timedelta(hours=1),
            scopes=["read", "activity:read_all"],
        )
        session.add_all([user, athlete, account, credential])
        session.commit()
        ids = (user.id, athlete.id, account.id, credential.id)
    yield factory, ids
    engine.dispose()


def manager(database, pages=(), *, error=None, token_service=None, page_size=2):
    factory, _ = database
    client = FakeActivityClient(pages, error)
    service = token_service or FakeTokenService()
    return (
        StravaSummaryImportManager(
            session_factory=factory,
            activity_client=client,
            token_service=service,
            page_size=page_size,
        ),
        client,
        service,
    )


def test_first_import_and_multiple_pages_commit_checkpoints(database):
    importer, client, _ = manager(
        database,
        [
            StravaActivityPage((activity(3), activity(2)), EMPTY_RATE),
            StravaActivityPage((activity(1),), EMPTY_RATE),
        ],
    )
    factory, (user_id, _, _, _) = database
    job = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(job.job_id))

    with factory() as session:
        stored = session.scalars(
            select(CompletedActivity).order_by(CompletedActivity.external_activity_id)
        ).all()
        persisted_job = session.get(SyncJob, job.job_id)
        assert [item.external_activity_id for item in stored] == ["1", "2", "3"]
        assert persisted_job.status == "succeeded"
        assert persisted_job.stats["imported_count"] == 3
        assert persisted_job.stats["page"] == 2
        assert persisted_job.stats["last_external_activity_id"] == "1"
    assert [call["page"] for call in client.calls] == [1, 2]
    assert all(call["per_page"] == 2 for call in client.calls)


def test_duplicate_updates_provider_fields_and_preserves_local_fields(database):
    importer, _, _ = manager(
        database, [StravaActivityPage((activity(10),), EMPTY_RATE)]
    )
    factory, (user_id, _, _, _) = database
    job = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(job.job_id))
    with factory() as session:
        stored = session.scalar(select(CompletedActivity))
        stored.description = "Athlete note"
        stored.rpe = 7
        persisted_job = session.get(SyncJob, job.job_id)
        persisted_job.status = "failed"
        persisted_job.stats = {**persisted_job.stats, "page": 0}
        session.commit()

    resumed, _, _ = manager(
        database,
        [
            StravaActivityPage(
                (activity(10, name="Provider rename", distance=2500.0),),
                EMPTY_RATE,
            )
        ],
    )
    replacement = resumed.create_or_resume_job(user_id)
    assert replacement.job_id != job.job_id
    asyncio.run(resumed.run_job(replacement.job_id))
    with factory() as session:
        rows = session.scalars(select(CompletedActivity)).all()
        assert len(rows) == 1
        assert rows[0].name == "Provider rename"
        assert rows[0].distance_m == 2500.0
        assert rows[0].description == "Athlete note"
        assert rows[0].rpe == 7
        persisted_job = session.get(SyncJob, replacement.job_id)
        assert persisted_job.stats["updated_count"] == 1


def test_interrupted_running_job_resumes_at_next_page(database):
    importer, _, _ = manager(database)
    factory, (user_id, _, _, _) = database
    job = importer.create_or_resume_job(user_id)
    with factory() as session:
        stored_job = session.get(SyncJob, job.job_id)
        stored_job.status = "running"
        stored_job.stats = {**stored_job.stats, "page": 1, "imported_count": 2}
        session.commit()
    resumed, client, _ = manager(
        database, [StravaActivityPage((activity(1),), EMPTY_RATE)]
    )
    assert resumed.create_or_resume_job(user_id).status == "queued"
    asyncio.run(resumed.run_job(job.job_id))
    assert client.calls[0]["page"] == 2
    with factory() as session:
        assert session.get(SyncJob, job.job_id).stats["imported_count"] == 3


def test_malformed_activity_isolated_and_import_continues(database):
    importer, _, _ = manager(
        database,
        [
            StravaActivityPage(
                (activity(2, elapsed_time=-1), activity(1)), EMPTY_RATE
            )
        ],
    )
    factory, (user_id, _, _, _) = database
    job = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(job.job_id))
    with factory() as session:
        assert session.scalar(select(func.count(CompletedActivity.id))) == 1
        stats = session.get(SyncJob, job.job_id).stats
        assert stats["failed_count"] == 1
        assert stats["imported_count"] == 1


def test_rate_limit_and_temporary_failure_pause_without_losing_progress(database):
    factory, (user_id, _, _, _) = database
    rate_error = StravaActivityRateLimitError(
        retry_after_seconds=37, rate_limit=EMPTY_RATE
    )
    importer, _, _ = manager(database, error=rate_error)
    job = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(job.job_id))
    with factory() as session:
        stored = session.get(SyncJob, job.job_id)
        assert stored.status == "retry_scheduled"
        assert stored.error_code == "rate_limited"
        assert stored.next_retry_at is not None

    with factory() as session:
        stored = session.get(SyncJob, job.job_id)
        stored.status = "failed"
        session.commit()
    temporary, _, _ = manager(
        database, error=TemporaryProviderError("safe temporary error")
    )
    replacement = temporary.create_or_resume_job(user_id)
    assert replacement.job_id != job.job_id
    asyncio.run(temporary.run_job(replacement.job_id))
    with factory() as session:
        stored = session.get(SyncJob, replacement.job_id)
        assert stored.status == "retry_scheduled"
        assert stored.error_code == "provider_temporary"


def test_invalid_credentials_require_reconnect(database):
    factory, (user_id, _, account_id, _) = database
    importer, _, _ = manager(
        database,
        token_service=FakeTokenService(AuthenticationError("invalid")),
    )
    job = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(job.job_id))
    with factory() as session:
        assert session.get(SyncJob, job.job_id).error_code == (
            "authentication_reconnect_required"
        )
        assert session.get(IntegrationAccount, account_id).status == "refresh_required"


def test_token_refresh_rotates_both_tokens_and_temporary_failure_preserves_them(database):
    factory, (_, _, account_id, credential_id) = database
    now = utc_now()
    with factory() as session:
        credential = session.get(OAuthCredential, credential_id)
        credential.created_at = now - timedelta(hours=2)
        credential.expires_at = now - timedelta(hours=1)
        session.commit()
    result = StravaRefreshResult(
        access_token=SecretStr("rotated-access"),
        refresh_token=SecretStr("rotated-refresh"),
        expires_at=now + timedelta(hours=6),
        token_type="Bearer",
    )
    oauth = FakeRefreshClient(result=result)
    service = StravaTokenService(session_factory=factory, oauth_client=oauth)
    token = asyncio.run(service.access_token(account_id))
    assert token.get_secret_value() == "rotated-access"
    assert oauth.seen_refresh == "stored-refresh-secret"
    with factory() as session:
        credential = session.get(OAuthCredential, credential_id)
        assert credential.access_token == "rotated-access"
        assert credential.refresh_token == "rotated-refresh"

        credential.expires_at = utc_now() - timedelta(minutes=1)
        credential.access_token = "preserved-access"
        credential.refresh_token = "preserved-refresh"
        session.commit()
    failing = StravaTokenService(
        session_factory=factory,
        oauth_client=FakeRefreshClient(error=TemporaryProviderError("temporary")),
    )
    with pytest.raises(TemporaryProviderError):
        asyncio.run(failing.access_token(account_id))
    with factory() as session:
        credential = session.get(OAuthCredential, credential_id)
        assert credential.access_token == "preserved-access"
        assert credential.refresh_token == "preserved-refresh"


@pytest.mark.parametrize("active_status", ["queued", "running", "retry_scheduled"])
def test_active_job_reuse_and_ownership_isolation(database, active_status):
    importer, _, _ = manager(database)
    factory, (user_id, _, _, _) = database
    first = importer.create_or_resume_job(user_id)
    with factory() as session:
        stored = session.get(SyncJob, first.job_id)
        stored.status = active_status
        if active_status == "retry_scheduled":
            stored.next_retry_at = utc_now() + timedelta(minutes=5)
        session.commit()
    second = importer.create_or_resume_job(user_id)
    assert first.job_id == second.job_id
    with factory() as session:
        assert session.scalar(select(func.count(SyncJob.id))) == 1
    with pytest.raises(ImportJobNotFoundError):
        importer.job_for_user(uuid4(), first.job_id)


@pytest.mark.parametrize("terminal_status", ["succeeded", "failed", "cancelled"])
def test_terminal_job_creates_new_job(database, terminal_status):
    importer, _, _ = manager(database)
    factory, (user_id, _, _, _) = database
    first = importer.create_or_resume_job(user_id)
    with factory() as session:
        stored = session.get(SyncJob, first.job_id)
        stored.status = terminal_status
        stored.finished_at = utc_now()
        session.commit()

    second = importer.create_or_resume_job(user_id)

    assert second.job_id != first.job_id
    assert second.status == "queued"
    with factory() as session:
        assert session.scalar(select(func.count(SyncJob.id))) == 2


def test_succeeded_history_creates_incremental_overlap_without_duplicates(database):
    importer, _, _ = manager(
        database, [StravaActivityPage((activity(10),), EMPTY_RATE)]
    )
    factory, (user_id, _, _, _) = database
    first = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(first.job_id))
    latest_start = utc_now().replace(
        year=2026, month=7, day=1, hour=6, minute=0, second=0, microsecond=0
    )

    client = FakeActivityClient(
        [StravaActivityPage((activity(10), activity(11)), EMPTY_RATE)]
    )
    incremental = StravaSummaryImportManager(
        session_factory=factory,
        activity_client=client,
        token_service=FakeTokenService(),
        page_size=100,
        incremental_overlap_seconds=60,
    )
    second = incremental.create_or_resume_job(user_id)
    assert second.job_id != first.job_id
    with factory() as session:
        stored = session.get(SyncJob, second.job_id)
        assert stored.range_start == latest_start - timedelta(seconds=60)
        assert stored.parent_job_id == first.job_id

    asyncio.run(incremental.run_job(second.job_id))

    assert client.calls[0]["after"] == int(
        (latest_start - timedelta(seconds=60)).timestamp()
    )
    with factory() as session:
        rows = session.scalars(
            select(CompletedActivity).order_by(
                CompletedActivity.external_activity_id
            )
        ).all()
        assert [row.external_activity_id for row in rows] == ["10", "11"]


def test_wrong_provider_athlete_halts_page_and_safe_view_contains_no_secrets(
    database, caplog
):
    importer, _, _ = manager(
        database,
        [
            StravaActivityPage(
                (activity(1), activity(2, athlete={"id": 999})), EMPTY_RATE
            )
        ],
    )
    factory, (user_id, _, _, _) = database
    job = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(job.job_id))
    view = importer.job_for_user(user_id, job.job_id)
    serialized = str(asdict(view))
    assert "secret" not in serialized
    assert "stored-access-secret" not in caplog.text
    with factory() as session:
        assert session.scalar(select(func.count(CompletedActivity.id))) == 0
        assert session.get(SyncJob, job.job_id).error_code == "ownership_mismatch"


def test_database_failure_rolls_back_only_current_page(database):
    factory, (user_id, _, _, _) = database
    client = FakeActivityClient(
        [
            StravaActivityPage((activity(1),), EMPTY_RATE),
            StravaActivityPage((activity(2),), EMPTY_RATE),
        ]
    )
    importer = StravaSummaryImportManager(
        session_factory=factory,
        activity_client=client,
        token_service=FakeTokenService(),
        mapper=FailOnActivityMapper(2),
        page_size=1,
    )
    job = importer.create_or_resume_job(user_id)
    asyncio.run(importer.run_job(job.job_id))
    with factory() as session:
        rows = session.scalars(select(CompletedActivity)).all()
        stored_job = session.get(SyncJob, job.job_id)
        assert [row.external_activity_id for row in rows] == ["1"]
        assert stored_job.stats["page"] == 1
        assert stored_job.stats["imported_count"] == 1
        assert stored_job.status == "failed"
        assert stored_job.error_code == "database_error"
