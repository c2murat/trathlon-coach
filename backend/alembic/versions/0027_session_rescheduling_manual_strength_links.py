"""session rescheduling and manual strength links"""
from alembic import op
import sqlalchemy as sa

revision = "0027_session_reschedule_links"
down_revision = "0026_session_activity_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planned_session_schedule_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("athlete_profile_id", sa.Uuid(), sa.ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("planned_training_session_id", sa.Uuid(), sa.ForeignKey("planned_training_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("training_plan_id", sa.Uuid(), sa.ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_scheduled_date", sa.Date(), nullable=False),
        sa.Column("new_scheduled_date", sa.Date(), nullable=False),
        sa.Column("changed_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.CheckConstraint("previous_scheduled_date <> new_scheduled_date", name="planned_session_schedule_change_date_changed"),
    )
    op.create_index("ix_planned_session_schedule_changes_athlete", "planned_session_schedule_changes", ["athlete_profile_id"])
    op.create_index("ix_planned_session_schedule_changes_session", "planned_session_schedule_changes", ["planned_training_session_id"])
    op.create_table(
        "planned_session_manual_strength_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("athlete_profile_id", sa.Uuid(), sa.ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("planned_training_session_id", sa.Uuid(), sa.ForeignKey("planned_training_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manual_strength_session_id", sa.Uuid(), sa.ForeignKey("manual_strength_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_source", sa.String(length=16), nullable=False),
        sa.Column("match_confidence", sa.String(length=16), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("match_source = 'manual'", name="planned_session_manual_strength_link_source_manual"),
        sa.CheckConstraint("match_confidence IN ('high','medium','low')", name="planned_session_manual_strength_link_confidence_valid"),
        sa.UniqueConstraint("planned_training_session_id", "manual_strength_session_id", name="uq_planned_session_manual_strength_link_pair"),
    )
    op.create_index("ix_planned_session_manual_strength_links_athlete", "planned_session_manual_strength_links", ["athlete_profile_id"])
    op.create_index("ix_planned_session_manual_strength_links_session", "planned_session_manual_strength_links", ["planned_training_session_id"])
    op.create_index("ix_planned_session_manual_strength_links_manual", "planned_session_manual_strength_links", ["manual_strength_session_id"])


def downgrade() -> None:
    op.drop_index("ix_planned_session_manual_strength_links_manual", table_name="planned_session_manual_strength_links")
    op.drop_index("ix_planned_session_manual_strength_links_session", table_name="planned_session_manual_strength_links")
    op.drop_index("ix_planned_session_manual_strength_links_athlete", table_name="planned_session_manual_strength_links")
    op.drop_table("planned_session_manual_strength_links")
    op.drop_index("ix_planned_session_schedule_changes_session", table_name="planned_session_schedule_changes")
    op.drop_index("ix_planned_session_schedule_changes_athlete", table_name="planned_session_schedule_changes")
    op.drop_table("planned_session_schedule_changes")
