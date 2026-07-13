from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.athlete import AthleteProfile
    from app.db.models.integration import IntegrationAccount


class CompletedActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "completed_activities"
    __table_args__ = (
        UniqueConstraint(
            "source_integration_account_id",
            "external_activity_id",
            name="uq_completed_activity_source_external_id",
        ),
        CheckConstraint(
            "sport IN ('swimming', 'cycling', 'running', 'strength', "
            "'multisport', 'other')",
            name="sport_valid",
        ),
        CheckConstraint("elapsed_time_s >= 0", name="elapsed_time_nonnegative"),
        CheckConstraint(
            "moving_time_s IS NULL OR moving_time_s >= 0",
            name="moving_time_nonnegative",
        ),
        CheckConstraint(
            "distance_m IS NULL OR distance_m >= 0", name="distance_nonnegative"
        ),
        CheckConstraint("rpe IS NULL OR rpe BETWEEN 1 AND 10", name="rpe_valid"),
    )

    athlete_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("athlete_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Temporary MVP provenance fields. Move them to ActivitySource when that
    # documented entity enters scope; they remain alternate keys, never the PK.
    source_integration_account_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("integration_accounts.id", ondelete="SET NULL"),
        index=True,
    )
    external_activity_id: Mapped[str | None] = mapped_column(String(255))
    source_summary: Mapped[str] = mapped_column(String(32), nullable=False)
    sport: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    start_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    elapsed_time_s: Mapped[int] = mapped_column(Integer, nullable=False)
    moving_time_s: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    average_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    max_heart_rate_bpm: Mapped[float | None] = mapped_column(Float)
    average_power_w: Mapped[float | None] = mapped_column(Float)
    max_power_w: Mapped[float | None] = mapped_column(Float)
    average_speed_mps: Mapped[float | None] = mapped_column(Float)
    calories_kcal: Mapped[float | None] = mapped_column(Float)
    rpe: Mapped[int | None]
    session_rpe_load: Mapped[float | None] = mapped_column(Float)
    indoor: Mapped[bool | None]
    commute: Mapped[bool | None]
    description: Mapped[str | None] = mapped_column(Text)
    provider_created_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    provider_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    provider_deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    athlete: Mapped[AthleteProfile] = relationship(back_populates="completed_activities")
    source_integration_account: Mapped[IntegrationAccount | None] = relationship(
        back_populates="completed_activities"
    )

