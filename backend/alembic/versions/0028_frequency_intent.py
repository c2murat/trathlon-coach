"""Nullable weekly frequency intent, without defaults or data updates."""
from alembic import op
import sqlalchemy as sa

revision = "0028_frequency_intent"
down_revision = "0027_session_reschedule_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athlete_planning_preference_versions", sa.Column("target_sessions_per_week", sa.Integer(), nullable=True))
    op.create_check_constraint("planning_preferences_target_sessions_valid", "athlete_planning_preference_versions",
        "target_sessions_per_week IS NULL OR (target_sessions_per_week BETWEEN 1 AND 28 AND target_sessions_per_week <= max_sessions_per_week)")


def downgrade() -> None:
    op.drop_constraint("planning_preferences_target_sessions_valid", "athlete_planning_preference_versions", type_="check")
    op.drop_column("athlete_planning_preference_versions", "target_sessions_per_week")
