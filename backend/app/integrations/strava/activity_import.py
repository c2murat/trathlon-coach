from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import (
    AthleteProfile,
    CompletedActivity,
    IntegrationAccount,
    SyncJob,
)
from app.integrations.strava.token_service import SessionFactory, StravaTokenService
from app.providers.base import (
    AuthenticationError,
    InvalidPayloadError,
    ProviderError,
    TemporaryProviderError,
)
from app.providers.strava.activity_client import (
    StravaActivityClient,
    StravaActivityPage,
    StravaActivityRateLimitError,
)
from app.providers.strava.activity_mapper import (
    StravaActivityMapper,
    StravaActivityOwnershipError,
)


JOB_TYPE = "strava_historical_summary"
IDEMPOTENCY_KEY_PREFIX = "strava-summary-v1"
ACTIVE_JOB_STATUSES = ("queued", "running", "retry_scheduled")
DEFAULT_STATS: dict[str, object] = {
    "imported_count": 0,
    "updated_count": 0,
    "skipped_count": 0,
    "failed_count": 0,
    "page": 0,
    "last_external_activity_id": None,
}


class ActiveStravaConnectionRequiredError(Exception):
    """The current user has no active import-capable Strava connection."""


class ImportJobNotFoundError(Exception):
    """The requested job is not owned by the current local user."""


class ActivityOwnershipMismatchError(Exception):
    """A returned activity belongs to another provider athlete."""


@dataclass(frozen=True, slots=True)
class StravaImportJobView:
    job_id: UUID
    provider: str
    status: str
    imported_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    page: int
    last_external_activity_id: str | None
    started_at: datetime | None
    updated_at: datetime
    completed_at: datetime | None
    next_resume_at: datetime | None
    error_category: str | None


class StravaSummaryImportManager:
    """Schedule and checkpoint summary-only historical Strava imports."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        activity_client: StravaActivityClient,
        token_service: StravaTokenService,
        mapper: StravaActivityMapper | None = None,
        page_size: int = 100,
        retry_seconds: int = 60,
        incremental_overlap_seconds: int = 86400,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if (
            not 1 <= page_size <= 200
            or retry_seconds < 1
            or incremental_overlap_seconds < 0
        ):
            raise ValueError("Invalid Strava import configuration")
        self._session_factory = session_factory
        self._activity_client = activity_client
        self._token_service = token_service
        self._mapper = mapper or StravaActivityMapper()
        self._page_size = page_size
        self._retry_seconds = retry_seconds
        self._incremental_overlap = timedelta(
            seconds=incremental_overlap_seconds
        )
        self._clock = clock
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def create_or_resume_job(
        self, user_id: UUID, *, full_reimport: bool = False
    ) -> StravaImportJobView:
        """Reuse active work or create a new checkpointed import generation.

        The full-reimport switch is reserved for a future explicit workflow and
        is not exposed by the HTTP API.
        """

        with self._session_factory() as session:
            account = self._active_account(session, user_id)
            if account is None:
                raise ActiveStravaConnectionRequiredError
            job = session.scalar(
                select(SyncJob)
                .where(
                    SyncJob.integration_account_id == account.id,
                    SyncJob.job_type == JOB_TYPE,
                    SyncJob.status.in_(ACTIVE_JOB_STATUSES),
                )
                .order_by(SyncJob.created_at.desc())
            )
            now = self._clock()
            if job is not None:
                local_task = self._tasks.get(job.id)
                interrupted = job.status == "running" and (
                    local_task is None or local_task.done()
                )
                if interrupted:
                    job.status = "queued"
                    session.commit()
                return self._view(job, account.provider)

            previous = session.scalar(
                select(SyncJob)
                .where(
                    SyncJob.integration_account_id == account.id,
                    SyncJob.job_type == JOB_TYPE,
                )
                .order_by(SyncJob.created_at.desc())
            )
            range_start, range_end, stats, parent_job_id = self._new_job_context(
                session,
                account=account,
                previous=previous,
                now=now,
                full_reimport=full_reimport,
            )
            job = SyncJob(
                athlete_id=account.athlete_id,
                integration_account_id=account.id,
                requested_by_user_id=user_id,
                job_type=JOB_TYPE,
                status="queued",
                idempotency_key=f"{IDEMPOTENCY_KEY_PREFIX}:{uuid4().hex}",
                attempt_count=0,
                parent_job_id=parent_job_id,
                range_start=range_start,
                range_end=range_end,
                stats=stats,
            )
            session.add(job)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(SyncJob)
                    .where(
                        SyncJob.integration_account_id == account.id,
                        SyncJob.job_type == JOB_TYPE,
                        SyncJob.status.in_(ACTIVE_JOB_STATUSES),
                    )
                    .order_by(SyncJob.created_at.desc())
                )
                if existing is None:
                    raise
                job = existing
            return self._view(job, account.provider)

    def _new_job_context(
        self,
        session: Session,
        *,
        account: IntegrationAccount,
        previous: SyncJob | None,
        now: datetime,
        full_reimport: bool,
    ) -> tuple[
        datetime | None,
        datetime,
        dict[str, object],
        UUID | None,
    ]:
        if full_reimport or previous is None:
            return None, now, dict(DEFAULT_STATS), None

        if previous.status in {"failed", "cancelled", "partially_succeeded"}:
            return (
                previous.range_start,
                previous.range_end or now,
                self._stats(previous),
                previous.id,
            )

        newest_activity_at = session.scalar(
            select(func.max(CompletedActivity.start_at)).where(
                CompletedActivity.source_integration_account_id == account.id,
                CompletedActivity.provider_deleted_at.is_(None),
            )
        )
        high_water_mark = newest_activity_at or previous.range_end
        range_start = (
            high_water_mark - self._incremental_overlap
            if high_water_mark is not None
            else None
        )
        return range_start, now, dict(DEFAULT_STATS), previous.id

    def job_for_user(self, user_id: UUID, job_id: UUID) -> StravaImportJobView:
        with self._session_factory() as session:
            row = session.execute(
                select(SyncJob, IntegrationAccount)
                .join(
                    IntegrationAccount,
                    SyncJob.integration_account_id == IntegrationAccount.id,
                )
                .join(
                    AthleteProfile,
                    IntegrationAccount.athlete_id == AthleteProfile.id,
                )
                .where(
                    SyncJob.id == job_id,
                    AthleteProfile.user_id == user_id,
                    IntegrationAccount.provider == "strava",
                )
            ).one_or_none()
            if row is None:
                raise ImportJobNotFoundError
            return self._view(row[0], row[1].provider)

    def schedule(self, job_id: UUID) -> None:
        existing = self._tasks.get(job_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(self.run_job(job_id))
        self._tasks[job_id] = task
        task.add_done_callback(lambda completed: self._tasks.pop(job_id, None))

    async def run_job(self, job_id: UUID) -> None:
        try:
            state = await asyncio.to_thread(self._mark_running, job_id)
            if state is None:
                return
            account_id, page, after, before = state
            while True:
                token = await self._token_service.access_token(account_id)
                result = await self._activity_client.fetch_activity_summaries(
                    access_token=token,
                    page=page,
                    per_page=self._page_size,
                    after=after,
                    before=before,
                )
                if not result.activities:
                    await asyncio.to_thread(self._mark_succeeded, job_id)
                    return
                await asyncio.to_thread(
                    self._persist_page,
                    job_id,
                    page,
                    result,
                )
                if self._rate_exhausted(result):
                    await asyncio.to_thread(
                        self._pause,
                        job_id,
                        "rate_limited",
                        900,
                    )
                    return
                if len(result.activities) < self._page_size:
                    await asyncio.to_thread(self._mark_succeeded, job_id)
                    return
                page += 1
        except StravaActivityRateLimitError as exc:
            await asyncio.to_thread(
                self._pause,
                job_id,
                "rate_limited",
                exc.retry_after_seconds or 900,
            )
        except AuthenticationError:
            await asyncio.to_thread(self._mark_reconnect_required, job_id)
        except TemporaryProviderError:
            await asyncio.to_thread(
                self._pause,
                job_id,
                "provider_temporary",
                self._retry_seconds,
            )
        except ActivityOwnershipMismatchError:
            await asyncio.to_thread(
                self._mark_failed,
                job_id,
                "ownership_mismatch",
            )
        except SQLAlchemyError:
            await asyncio.to_thread(self._mark_failed, job_id, "database_error")
        except (ProviderError, InvalidPayloadError):
            await asyncio.to_thread(self._mark_failed, job_id, "provider_payload")
        except Exception:
            await asyncio.to_thread(self._mark_failed, job_id, "unexpected")

    def _mark_running(
        self, job_id: UUID
    ) -> tuple[UUID, int, int | None, int | None] | None:
        with self._session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None or job.status not in {"queued", "retry_scheduled"}:
                return None
            now = self._clock()
            if job.status == "retry_scheduled" and job.next_retry_at is not None:
                if job.next_retry_at > now:
                    return None
            stats = self._stats(job)
            job.status = "running"
            job.started_at = job.started_at or now
            job.attempt_count += 1
            job.next_retry_at = None
            session.commit()
            return (
                job.integration_account_id,
                int(stats["page"]) + 1,
                int(job.range_start.timestamp()) if job.range_start else None,
                int(job.range_end.timestamp()) if job.range_end else None,
            )

    def _persist_page(
        self,
        job_id: UUID,
        page_number: int,
        result: StravaActivityPage,
    ) -> None:
        with self._session_factory() as session:
            try:
                job = session.get(SyncJob, job_id)
                if job is None or job.status != "running":
                    raise RuntimeError("Import job is not running")
                account = session.get(
                    IntegrationAccount,
                    job.integration_account_id,
                )
                if account is None:
                    raise RuntimeError("Import integration disappeared")
                athlete = session.get(AthleteProfile, account.athlete_id)
                if athlete is None:
                    raise RuntimeError("Import athlete disappeared")
                stats = self._stats(job)
                now = self._clock()
                for payload in result.activities:
                    try:
                        mapped = self._mapper.map_summary(
                            payload,
                            external_account_id=account.external_account_id,
                            athlete_timezone=athlete.timezone,
                        )
                    except StravaActivityOwnershipError:
                        raise ActivityOwnershipMismatchError from None
                    except InvalidPayloadError:
                        stats["failed_count"] = int(stats["failed_count"]) + 1
                        continue

                    activity = session.scalar(
                        select(CompletedActivity).where(
                            CompletedActivity.source_integration_account_id
                            == account.id,
                            CompletedActivity.external_activity_id
                            == mapped.external_activity_id,
                        )
                    )
                    provider_fields = mapped.provider_fields()
                    if activity is None:
                        activity = CompletedActivity(
                            athlete_id=account.athlete_id,
                            source_integration_account_id=account.id,
                            external_activity_id=mapped.external_activity_id,
                            last_synced_at=now,
                            **provider_fields,
                        )
                        session.add(activity)
                        stats["imported_count"] = int(stats["imported_count"]) + 1
                    else:
                        changed = any(
                            getattr(activity, field_name) != value
                            for field_name, value in provider_fields.items()
                        )
                        for field_name, value in provider_fields.items():
                            setattr(activity, field_name, value)
                        activity.last_synced_at = now
                        counter = "updated_count" if changed else "skipped_count"
                        stats[counter] = int(stats[counter]) + 1
                    stats["last_external_activity_id"] = (
                        mapped.external_activity_id
                    )

                stats["page"] = page_number
                job.stats = stats
                job.cursor_before = str(page_number)
                account.last_synced_at = now
                session.commit()
            except Exception:
                session.rollback()
                raise

    def _mark_succeeded(self, job_id: UUID) -> None:
        with self._session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            job.status = "succeeded"
            job.finished_at = self._clock()
            job.next_retry_at = None
            job.error_code = None
            job.error_detail = None
            session.commit()

    def _pause(
        self,
        job_id: UUID,
        category: str,
        retry_seconds: int,
    ) -> None:
        with self._session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            job.status = "retry_scheduled"
            job.error_code = category
            job.error_detail = None
            job.next_retry_at = self._clock() + timedelta(seconds=retry_seconds)
            session.commit()

    def _mark_reconnect_required(self, job_id: UUID) -> None:
        with self._session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            account = session.get(
                IntegrationAccount,
                job.integration_account_id,
            )
            if account is not None:
                account.status = "refresh_required"
            job.status = "failed"
            job.finished_at = self._clock()
            job.error_code = "authentication_reconnect_required"
            job.error_detail = None
            session.commit()

    def _mark_failed(self, job_id: UUID, category: str) -> None:
        with self._session_factory() as session:
            job = session.get(SyncJob, job_id)
            if job is None:
                return
            job.status = "failed"
            job.finished_at = self._clock()
            job.error_code = category
            job.error_detail = None
            session.commit()

    @staticmethod
    def _active_account(
        session: Session, user_id: UUID
    ) -> IntegrationAccount | None:
        return session.scalar(
            select(IntegrationAccount)
            .join(
                AthleteProfile,
                IntegrationAccount.athlete_id == AthleteProfile.id,
            )
            .where(
                AthleteProfile.user_id == user_id,
                IntegrationAccount.provider == "strava",
                IntegrationAccount.status == "active",
                IntegrationAccount.deleted_at.is_(None),
            )
        )

    @staticmethod
    def _stats(job: SyncJob) -> dict[str, object]:
        return {**DEFAULT_STATS, **(job.stats or {})}

    @staticmethod
    def _rate_exhausted(result: StravaActivityPage) -> bool:
        snapshot = result.rate_limit
        for limit, usage in (
            (snapshot.general_limit, snapshot.general_usage),
            (snapshot.read_limit, snapshot.read_usage),
        ):
            if limit and usage and (
                usage[0] >= limit[0] or usage[1] >= limit[1]
            ):
                return True
        return False

    @classmethod
    def _view(cls, job: SyncJob, provider: str) -> StravaImportJobView:
        stats = cls._stats(job)
        return StravaImportJobView(
            job_id=job.id,
            provider=provider,
            status=job.status,
            imported_count=int(stats["imported_count"]),
            updated_count=int(stats["updated_count"]),
            skipped_count=int(stats["skipped_count"]),
            failed_count=int(stats["failed_count"]),
            page=int(stats["page"]),
            last_external_activity_id=(
                str(stats["last_external_activity_id"])
                if stats["last_external_activity_id"] is not None
                else None
            ),
            started_at=job.started_at,
            updated_at=job.updated_at,
            completed_at=job.finished_at,
            next_resume_at=job.next_retry_at,
            error_category=job.error_code,
        )
