from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    JSON_DOCUMENT,
    TimestampMixin,
    UTCDateTime,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from app.db.models.activity import CompletedActivity
    from app.db.models.athlete import AthleteProfile
    from app.db.models.operations import SyncJob, WebhookEvent


class IntegrationAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_accounts"
    __table_args__ = (
        UniqueConstraint(
            "athlete_id",
            "provider",
            "external_account_id",
            name="uq_integration_account_external_identity",
        ),
        UniqueConstraint(
            "provider",
            "external_account_id",
            name="uq_integration_account_provider_external_identity",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'refresh_required', 'error', "
            "'disconnected', 'revoked')",
            name="status_valid",
        ),
    )

    athlete_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("athlete_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    scopes: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    display_name: Mapped[str | None] = mapped_column(String(200))
    provider_metadata: Mapped[dict[str, object] | None] = mapped_column(JSON_DOCUMENT)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    disconnected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sync_cursor: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    athlete: Mapped[AthleteProfile] = relationship(back_populates="integration_accounts")
    oauth_credential: Mapped[OAuthCredential | None] = relationship(
        back_populates="integration_account",
        cascade="all, delete-orphan",
        uselist=False,
    )
    completed_activities: Mapped[list[CompletedActivity]] = relationship(
        back_populates="source_integration_account"
    )
    sync_jobs: Mapped[list[SyncJob]] = relationship(back_populates="integration_account")
    webhook_events: Mapped[list[WebhookEvent]] = relationship(
        back_populates="integration_account"
    )


class OAuthCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "oauth_credentials"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
    )

    integration_account_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("integration_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # SECURITY TODO: these fields are plaintext placeholders for local development.
    # Production must use envelope encryption with keys stored outside PostgreSQL.
    access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info={"secret": True, "production_encryption_required": True},
    )
    refresh_token: Mapped[str | None] = mapped_column(
        Text,
        info={"secret": True, "production_encryption_required": True},
    )
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Bearer")
    scopes: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    key_version: Mapped[str] = mapped_column(String(64), nullable=False, default="plaintext-dev")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    integration_account: Mapped[IntegrationAccount] = relationship(
        back_populates="oauth_credential"
    )

    def __repr__(self) -> str:
        return (
            f"<OAuthCredential id={self.id!r} "
            f"integration_account_id={self.integration_account_id!r} "
            f"expires_at={self.expires_at!r}>"
        )

