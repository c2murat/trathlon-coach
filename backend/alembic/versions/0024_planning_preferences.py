"""Versioned athlete planning preferences and availability."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0024_planning_preferences"
down_revision = "0023_competition_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "athlete_planning_preference_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("athlete_profile_id", sa.Uuid(), sa.ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("max_sessions_per_day", sa.Integer(), nullable=False),
        sa.Column("max_sessions_per_week", sa.Integer(), nullable=False),
        sa.Column("preferred_rest_days", json_document, nullable=False),
        sa.Column("preferred_long_run_day", sa.Integer()),
        sa.Column("preferred_long_bike_day", sa.Integer()),
        sa.Column("strength_sessions_per_week", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("athlete_profile_id", "version_number", name="uq_planning_preferences_athlete_version"),
        sa.CheckConstraint("version_number >= 1", name="planning_preferences_version_positive"),
        sa.CheckConstraint("max_sessions_per_day BETWEEN 0 AND 4", name="planning_preferences_daily_sessions_valid"),
        sa.CheckConstraint("max_sessions_per_week BETWEEN 0 AND 28", name="planning_preferences_weekly_sessions_valid"),
        sa.CheckConstraint("strength_sessions_per_week BETWEEN 0 AND 7", name="planning_preferences_strength_sessions_valid"),
    )
    op.create_index("ix_planning_preferences_athlete_version", "athlete_planning_preference_versions", ["athlete_profile_id", "version_number"])
    op.create_table(
        "athlete_availability_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("preference_version_id", sa.Uuid(), sa.ForeignKey("athlete_planning_preference_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("available_minutes", sa.Integer(), nullable=False),
        sa.Column("max_sessions", sa.Integer(), nullable=False),
        sa.Column("earliest_time", sa.Time()),
        sa.Column("latest_time", sa.Time()),
        sa.UniqueConstraint("preference_version_id", "weekday", "position", name="uq_availability_slot_position"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="availability_slot_weekday_valid"),
        sa.CheckConstraint("position >= 1", name="availability_slot_position_positive"),
        sa.CheckConstraint("available_minutes BETWEEN 0 AND 1440", name="availability_slot_minutes_valid"),
        sa.CheckConstraint("max_sessions BETWEEN 0 AND 4", name="availability_slot_sessions_valid"),
        sa.CheckConstraint("available_minutes > 0 OR max_sessions = 0", name="availability_slot_zero_minutes_sessions"),
        sa.CheckConstraint("earliest_time IS NULL OR latest_time IS NULL OR earliest_time < latest_time", name="availability_slot_time_window_valid"),
    )
    op.create_index("ix_availability_slots_preference", "athlete_availability_slots", ["preference_version_id"])


def downgrade() -> None:
    op.drop_index("ix_availability_slots_preference", table_name="athlete_availability_slots")
    op.drop_table("athlete_availability_slots")
    op.drop_index("ix_planning_preferences_athlete_version", table_name="athlete_planning_preference_versions")
    op.drop_table("athlete_planning_preference_versions")
