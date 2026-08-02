from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSON_DOCUMENT, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.athlete import AthleteProfile


class ManualStrengthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'manual_strength_sessions'
    __table_args__ = (
        CheckConstraint('duration_minutes > 0 AND duration_minutes <= 1440', name='manual_strength_duration_valid'),
        CheckConstraint('perceived_exertion IS NULL OR (perceived_exertion >= 1 AND perceived_exertion <= 10)', name='manual_strength_rpe_valid'),
        CheckConstraint('length(trim(timezone_name)) > 0', name='manual_strength_timezone_not_empty'),
        Index('ix_manual_strength_athlete_started', 'athlete_id', 'started_at'),
    )
    athlete_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('athlete_profiles.id', ondelete='CASCADE'), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    body_regions: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    perceived_exertion: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    athlete: Mapped[AthleteProfile] = relationship()
    training_loads: Mapped[list[ManualStrengthTrainingLoad]] = relationship(
        back_populates='session', cascade='all, delete-orphan', passive_deletes=True
    )


class ManualStrengthTrainingLoad(UUIDPrimaryKeyMixin, Base):
    __tablename__ = 'manual_strength_training_loads'
    __table_args__ = (
        CheckConstraint('load_value >= 0', name='manual_strength_load_nonnegative'),
        UniqueConstraint('session_id', 'algorithm_version', name='uq_manual_strength_load_session_algorithm'),
        Index('ix_manual_strength_load_session', 'session_id'),
    )
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('manual_strength_sessions.id', ondelete='CASCADE'), nullable=False)
    load_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    quality: Mapped[str] = mapped_column(String(24), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    session: Mapped[ManualStrengthSession] = relationship(back_populates='training_loads')
