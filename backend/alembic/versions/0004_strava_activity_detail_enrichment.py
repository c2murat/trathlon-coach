"""Add provider-owned Strava activity detail enrichment fields.

Revision ID: 0004_strava_activity_detail
Revises: 0003_strava_summary_import
"""
from alembic import op
import sqlalchemy as sa
revision = "0004_strava_activity_detail"
down_revision = "0003_strava_summary_import"
branch_labels = None
depends_on = None
COLUMNS = (
    ("provider_description", sa.Text()), ("device_name", sa.String(300)),
    ("gear_id", sa.String(255)), ("suffer_score", sa.Integer()),
    ("provider_perceived_exertion", sa.Float()), ("total_work_j", sa.Float()),
    ("kilojoules", sa.Float()), ("average_temperature_c", sa.Float()),
    ("workout_type", sa.Integer()), ("achievement_count", sa.Integer()),
    ("kudos_count", sa.Integer()), ("athlete_count", sa.Integer()),
    ("photo_count", sa.Integer()), ("has_heartrate", sa.Boolean()),
    ("has_power_meter", sa.Boolean()), ("hide_from_home", sa.Boolean()),
    ("private", sa.Boolean()), ("flagged", sa.Boolean()),
    ("enriched_at", sa.DateTime(timezone=True)),
    ("enrichment_status", sa.String(32)),
    ("enrichment_error_category", sa.String(100)),
)
def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("completed_activities", sa.Column(name, type_, nullable=True))
    op.create_index("ix_completed_activities_enriched_at", "completed_activities", ["enriched_at"])
    op.create_index("ix_completed_activities_enrichment_status", "completed_activities", ["enrichment_status"])
    op.create_index("uq_sync_jobs_active_strava_detail", "sync_jobs", ["integration_account_id"], unique=True, postgresql_where=sa.text("job_type = 'strava_activity_detail' AND status IN ('queued', 'running', 'retry_scheduled')"), sqlite_where=sa.text("job_type = 'strava_activity_detail' AND status IN ('queued', 'running', 'retry_scheduled')"))
def downgrade() -> None:
    op.drop_index("uq_sync_jobs_active_strava_detail", table_name="sync_jobs")
    op.drop_index("ix_completed_activities_enrichment_status", table_name="completed_activities")
    op.drop_index("ix_completed_activities_enriched_at", table_name="completed_activities")
    for name, _ in reversed(COLUMNS):
        op.drop_column("completed_activities", name)



