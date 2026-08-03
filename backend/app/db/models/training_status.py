from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin


class AthleteDailyTrainingStatus(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "athlete_daily_training_statuses"
    __table_args__ = (
        UniqueConstraint(
            "athlete_profile_id",
            "local_date",
            "timezone_name",
            "training_load_algorithm_version",
            "manual_strength_algorithm_version",
            "training_status_algorithm_version",
            name="uq_daily_training_status_configuration",
        ),
        CheckConstraint(
            "total_load >= 0", name="daily_training_status_total_load_nonnegative"
        ),
        CheckConstraint(
            "fitness >= 0", name="daily_training_status_fitness_nonnegative"
        ),
        CheckConstraint(
            "fatigue >= 0", name="daily_training_status_fatigue_nonnegative"
        ),
        CheckConstraint(
            "history_day_number >= 1",
            name="daily_training_status_history_day_positive",
        ),
        CheckConstraint(
            "length(trim(timezone_name)) > 0",
            name="daily_training_status_timezone_not_empty",
        ),
        CheckConstraint(
            "length(trim(training_load_algorithm_version)) > 0",
            name="daily_training_status_load_version_not_empty",
        ),
        CheckConstraint(
            "length(trim(manual_strength_algorithm_version)) > 0",
            name="daily_training_status_manual_version_not_empty",
        ),
        CheckConstraint(
            "length(trim(training_status_algorithm_version)) > 0",
            name="daily_training_status_algorithm_version_not_empty",
        ),
        Index(
            "ix_daily_training_status_athlete_date_timezone",
            "athlete_profile_id",
            "local_date",
            "timezone_name",
        ),
    )

    athlete_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    training_load_algorithm_version: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    manual_strength_algorithm_version: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    training_status_algorithm_version: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    total_load: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fitness: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fatigue: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    form: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    history_day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_warmup: Mapped[bool] = mapped_column(Boolean, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
