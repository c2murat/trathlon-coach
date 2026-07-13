from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    JSON_DOCUMENT,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from app.db.models.athlete import AthleteProfile
    from app.db.models.integration import IntegrationAccount
    from app.db.models.user import User


class SyncJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        UniqueConstraint(
            "integration_account_id",
            "job_type",
            "idempotency_key",
            name="uq_sync_job_idempotency",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_scheduled', 'succeeded', "
            "'partially_succeeded', 'failed', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        Index(
            "uq_sync_jobs_active_strava_summary",
            "integration_account_id",
            unique=True,
            postgresql_where=text(
                "job_type = 'strava_historical_summary' AND "
                "status IN ('queued', 'running', 'retry_scheduled')"
            ),
            sqlite_where=text(
                "job_type = 'strava_historical_summary' AND "
                "status IN ('queued', 'running', 'retry_scheduled')"
            ),
        ),
    )

    athlete_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("athlete_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("integration_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sync_jobs.id", ondelete="SET NULL")
    )
    requested_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_before: Mapped[str | None] = mapped_column(Text)
    cursor_after: Mapped[str | None] = mapped_column(Text)
    range_start: Mapped[datetime | None] = mapped_column(UTCDateTime())
    range_end: Mapped[datetime | None] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, object] | None] = mapped_column(JSON_DOCUMENT)

    athlete: Mapped[AthleteProfile] = relationship(back_populates="sync_jobs")
    integration_account: Mapped[IntegrationAccount] = relationship(
        back_populates="sync_jobs"
    )
    parent_job: Mapped[SyncJob | None] = relationship(remote_side="SyncJob.id")
    webhook_events: Mapped[list[WebhookEvent]] = relationship(back_populates="sync_job")


class WebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "deduplication_key", name="uq_webhook_event_idempotency"
        ),
        CheckConstraint(
            "status IN ('received', 'ignored', 'queued', 'processing', "
            "'processed', 'failed', 'dead_lettered')",
            name="status_valid",
        ),
    )

    integration_account_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("integration_accounts.id", ondelete="SET NULL"),
        index=True,
    )
    sync_job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sync_jobs.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    external_owner_id: Mapped[str | None] = mapped_column(String(255))
    external_object_id: Mapped[str | None] = mapped_column(String(255))
    external_event_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_detail: Mapped[str | None] = mapped_column(Text)
    # Raw payload storage is optional, restricted, and short-lived (30 days max).
    # Prefer payload_hash plus normalized envelope fields whenever replay is unnecessary.
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSON_DOCUMENT)
    raw_payload_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    integration_account: Mapped[IntegrationAccount | None] = relationship(
        back_populates="webhook_events"
    )
    sync_job: Mapped[SyncJob | None] = relationship(back_populates="webhook_events")


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    athlete_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("athlete_profiles.id", ondelete="SET NULL"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    ip_hash: Mapped[str | None] = mapped_column(String(128))
    user_agent_summary: Mapped[str | None] = mapped_column(String(300))
    reason: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON_DOCUMENT)

    actor: Mapped[User | None] = relationship(back_populates="audit_events")
    athlete: Mapped[AthleteProfile | None] = relationship(back_populates="audit_events")
