"""Add Strava summary import fields and active-job uniqueness.

Revision ID: 0003_strava_summary_import
Revises: 0002_provider_account_owner
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_strava_summary_import"
down_revision = "0002_provider_account_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "completed_activities",
        sa.Column("weighted_average_power_w", sa.Float(), nullable=True),
    )
    op.add_column(
        "completed_activities",
        sa.Column("max_speed_mps", sa.Float(), nullable=True),
    )
    op.add_column(
        "completed_activities",
        sa.Column("average_cadence_rpm", sa.Float(), nullable=True),
    )
    op.add_column(
        "completed_activities",
        sa.Column("manual", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "completed_activities",
        sa.Column("visibility", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_completed_activities_visibility_valid",
        "completed_activities",
        "visibility IS NULL OR visibility IN "
        "('everyone', 'followers_only', 'only_me', 'unknown')",
    )
    op.create_index(
        "uq_sync_jobs_active_strava_summary",
        "sync_jobs",
        ["integration_account_id"],
        unique=True,
        postgresql_where=sa.text(
            "job_type = 'strava_historical_summary' AND "
            "status IN ('queued', 'running', 'retry_scheduled')"
        ),
        sqlite_where=sa.text(
            "job_type = 'strava_historical_summary' AND "
            "status IN ('queued', 'running', 'retry_scheduled')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_sync_jobs_active_strava_summary",
        table_name="sync_jobs",
    )
    op.drop_constraint(
        "ck_completed_activities_visibility_valid",
        "completed_activities",
        type_="check",
    )
    op.drop_column("completed_activities", "visibility")
    op.drop_column("completed_activities", "manual")
    op.drop_column("completed_activities", "average_cadence_rpm")
    op.drop_column("completed_activities", "max_speed_mps")
    op.drop_column("completed_activities", "weighted_average_power_w")
