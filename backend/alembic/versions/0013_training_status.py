"""Add persisted daily training status."""

from alembic import op
import sqlalchemy as sa


revision = "0013_training_status"
down_revision = "0012_manual_strength_aggregates"
branch_labels = None
depends_on = None

TABLE = "athlete_daily_training_statuses"
INDEX = "ix_daily_training_status_athlete_date_timezone"


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("athlete_profile_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.Column("training_load_algorithm_version", sa.String(32), nullable=False),
        sa.Column("manual_strength_algorithm_version", sa.String(32), nullable=False),
        sa.Column("training_status_algorithm_version", sa.String(32), nullable=False),
        sa.Column("total_load", sa.Numeric(14, 2), nullable=False),
        sa.Column("fitness", sa.Numeric(14, 2), nullable=False),
        sa.Column("fatigue", sa.Numeric(14, 2), nullable=False),
        sa.Column("form", sa.Numeric(14, 2), nullable=False),
        sa.Column("history_day_number", sa.Integer(), nullable=False),
        sa.Column("is_warmup", sa.Boolean(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_load >= 0", name="ck_daily_training_status_total_load_nonnegative"),
        sa.CheckConstraint("fitness >= 0", name="ck_daily_training_status_fitness_nonnegative"),
        sa.CheckConstraint("fatigue >= 0", name="ck_daily_training_status_fatigue_nonnegative"),
        sa.CheckConstraint("history_day_number >= 1", name="ck_daily_training_status_history_day_positive"),
        sa.CheckConstraint("length(trim(timezone_name)) > 0", name="ck_daily_training_status_timezone_not_empty"),
        sa.CheckConstraint("length(trim(training_load_algorithm_version)) > 0", name="ck_daily_training_status_load_version_not_empty"),
        sa.CheckConstraint("length(trim(manual_strength_algorithm_version)) > 0", name="ck_daily_training_status_manual_version_not_empty"),
        sa.CheckConstraint("length(trim(training_status_algorithm_version)) > 0", name="ck_daily_training_status_algorithm_version_not_empty"),
        sa.ForeignKeyConstraint(["athlete_profile_id"], ["athlete_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "athlete_profile_id",
            "local_date",
            "timezone_name",
            "training_load_algorithm_version",
            "manual_strength_algorithm_version",
            "training_status_algorithm_version",
            name="uq_daily_training_status_configuration",
        ),
    )
    op.create_index(
        INDEX,
        TABLE,
        ["athlete_profile_id", "local_date", "timezone_name"],
        unique=False,
    )


def downgrade():
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
