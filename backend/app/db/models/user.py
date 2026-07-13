from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.athlete import AthleteProfile
    from app.db.models.operations import AuditEvent


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled', 'pending_deletion')",
            name="status_valid",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    auth_subject: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    display_name: Mapped[str | None] = mapped_column(String(200))
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    athlete_profile: Mapped[AthleteProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="actor")

