from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Time, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSON_DOCUMENT, UTCDateTime, UUIDPrimaryKeyMixin, utc_now


class AthletePlanningPreferenceVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "athlete_planning_preference_versions"
    __table_args__ = (
        UniqueConstraint("athlete_profile_id", "version_number", name="uq_planning_preferences_athlete_version"),
        CheckConstraint("version_number >= 1", name="planning_preferences_version_positive"),
        CheckConstraint("max_sessions_per_day BETWEEN 0 AND 4", name="planning_preferences_daily_sessions_valid"),
        CheckConstraint("max_sessions_per_week BETWEEN 0 AND 28", name="planning_preferences_weekly_sessions_valid"),
        CheckConstraint("strength_sessions_per_week BETWEEN 0 AND 7", name="planning_preferences_strength_sessions_valid"),
        Index("ix_planning_preferences_athlete_version", "athlete_profile_id", "version_number"),
    )
    athlete_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    max_sessions_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    max_sessions_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_rest_days: Mapped[list[int]] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    preferred_long_run_day: Mapped[int | None] = mapped_column(Integer)
    preferred_long_bike_day: Mapped[int | None] = mapped_column(Integer)
    strength_sessions_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    slots: Mapped[list[AthleteAvailabilitySlot]] = relationship(
        back_populates="preference_version", cascade="all, delete-orphan",
        order_by="AthleteAvailabilitySlot.position",
    )


class AthleteAvailabilitySlot(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "athlete_availability_slots"
    __table_args__ = (
        UniqueConstraint("preference_version_id", "weekday", "position", name="uq_availability_slot_position"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="availability_slot_weekday_valid"),
        CheckConstraint("position >= 1", name="availability_slot_position_positive"),
        CheckConstraint("available_minutes BETWEEN 0 AND 1440", name="availability_slot_minutes_valid"),
        CheckConstraint("max_sessions BETWEEN 0 AND 4", name="availability_slot_sessions_valid"),
        CheckConstraint("available_minutes > 0 OR max_sessions = 0", name="availability_slot_zero_minutes_sessions"),
        CheckConstraint("earliest_time IS NULL OR latest_time IS NULL OR earliest_time < latest_time", name="availability_slot_time_window_valid"),
        Index("ix_availability_slots_preference", "preference_version_id"),
    )
    preference_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("athlete_planning_preference_versions.id", ondelete="CASCADE"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    available_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    max_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    earliest_time: Mapped[time | None] = mapped_column(Time)
    latest_time: Mapped[time | None] = mapped_column(Time)
    preference_version: Mapped[AthletePlanningPreferenceVersion] = relationship(back_populates="slots")
