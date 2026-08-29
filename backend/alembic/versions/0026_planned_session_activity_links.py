"""Explicit N:M links between planned sessions and completed activities."""
from alembic import op
import sqlalchemy as sa

revision = "0026_session_activity_links"
down_revision = "0025_training_plan_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planned_session_activity_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("athlete_profile_id", sa.Uuid(), sa.ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("planned_training_session_id", sa.Uuid(), sa.ForeignKey("planned_training_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("completed_activity_id", sa.Uuid(), sa.ForeignKey("completed_activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_source", sa.String(16), nullable=False),
        sa.Column("match_confidence", sa.String(16), nullable=False),
        sa.Column("algorithm_version", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("match_source IN ('automatic','manual')", name="planned_session_activity_link_source_valid"),
        sa.CheckConstraint("match_confidence IN ('high','medium','low')", name="planned_session_activity_link_confidence_valid"),
        sa.CheckConstraint("(match_source = 'automatic' AND algorithm_version IS NOT NULL) OR (match_source = 'manual' AND algorithm_version IS NULL)", name="planned_session_activity_link_algorithm_valid"),
        sa.UniqueConstraint("planned_training_session_id", "completed_activity_id", name="uq_planned_session_activity_link_pair"),
    )
    op.create_index("ix_planned_session_activity_links_athlete", "planned_session_activity_links", ["athlete_profile_id"])
    op.create_index("ix_planned_session_activity_links_session", "planned_session_activity_links", ["planned_training_session_id"])
    op.create_index("ix_planned_session_activity_links_activity", "planned_session_activity_links", ["completed_activity_id"])


def downgrade() -> None:
    op.drop_index("ix_planned_session_activity_links_activity", table_name="planned_session_activity_links")
    op.drop_index("ix_planned_session_activity_links_session", table_name="planned_session_activity_links")
    op.drop_index("ix_planned_session_activity_links_athlete", table_name="planned_session_activity_links")
    op.drop_table("planned_session_activity_links")
