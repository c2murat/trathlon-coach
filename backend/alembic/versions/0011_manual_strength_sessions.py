"""Persist manual strength sessions and derived loads (0.7E.2)."""

from alembic import op
import sqlalchemy as sa

revision = "0011_manual_strength_sessions"
down_revision = "0010_training_load_aggregates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_strength_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), sa.ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone_name", sa.String(64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("body_regions", sa.JSON(), nullable=False),
        sa.Column("perceived_exertion", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.CheckConstraint("duration_minutes > 0 AND duration_minutes <= 1440", name="ck_manual_strength_duration_valid"),
        sa.CheckConstraint("perceived_exertion IS NULL OR (perceived_exertion >= 1 AND perceived_exertion <= 10)", name="ck_manual_strength_rpe_valid"),
        sa.CheckConstraint("length(trim(timezone_name)) > 0", name="ck_manual_strength_timezone_not_empty"),
    )
    op.create_index("ix_manual_strength_athlete_started", "manual_strength_sessions", ["athlete_id", "started_at"])
    op.create_table(
        "manual_strength_training_loads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("manual_strength_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("load_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("quality", sa.String(24), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("load_value >= 0", name="ck_manual_strength_load_nonnegative"),
        sa.UniqueConstraint("session_id", "algorithm_version", name="uq_manual_strength_load_session_algorithm"),
    )
    op.create_index("ix_manual_strength_load_session", "manual_strength_training_loads", ["session_id"])


def downgrade():
    op.drop_index("ix_manual_strength_load_session", table_name="manual_strength_training_loads")
    op.drop_table("manual_strength_training_loads")
    op.drop_index("ix_manual_strength_athlete_started", table_name="manual_strength_sessions")
    op.drop_table("manual_strength_sessions")
