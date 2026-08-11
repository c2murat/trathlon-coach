from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.activity import CompletedActivity
    from app.db.models.integration import IntegrationAccount
    from app.db.models.membership import UserAthleteMembership
    from app.db.models.operations import AuditEvent, SyncJob


class AthleteProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "athlete_profiles"
    __table_args__ = (
        CheckConstraint(
            "unit_system IN ('metric', 'imperial')", name="unit_system_valid"
        ),
        CheckConstraint("height_m IS NULL OR height_m > 0", name="height_positive"),
        CheckConstraint("weight_kg IS NULL OR weight_kg > 0", name="weight_positive"),
        CheckConstraint("length(trim(display_name)) BETWEEN 1 AND 200", name="display_name_valid"),
    )

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    unit_system: Mapped[str] = mapped_column(String(16), nullable=False, default="metric")
    birth_year: Mapped[int | None]
    sex_for_training_context: Mapped[str | None] = mapped_column(String(32))
    height_m: Mapped[float | None] = mapped_column(Numeric(5, 3))
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 3))
    experience_level: Mapped[str | None] = mapped_column(String(32))
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    user_memberships: Mapped[list[UserAthleteMembership]] = relationship(
        back_populates="athlete_profile", cascade="all, delete-orphan"
    )
    integration_accounts: Mapped[list[IntegrationAccount]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
    completed_activities: Mapped[list[CompletedActivity]] = relationship(
        back_populates="athlete", cascade="all, delete-orphan"
    )
    sync_jobs: Mapped[list[SyncJob]] = relationship(back_populates="athlete")
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="athlete")
