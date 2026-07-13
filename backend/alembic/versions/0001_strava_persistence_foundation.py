"""Create the Strava persistence foundation.

Revision ID: 0001_strava_foundation
Revises: None
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_strava_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("auth_subject", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'pending_deletion')",
            name="ck_users_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
        sa.UniqueConstraint("auth_subject", name="uq_users_auth_subject"),
    )

    op.create_table(
        "athlete_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("unit_system", sa.String(16), nullable=False),
        sa.Column("birth_year", sa.Integer()),
        sa.Column("sex_for_training_context", sa.String(32)),
        sa.Column("height_m", sa.Numeric(5, 3)),
        sa.Column("weight_kg", sa.Numeric(6, 3)),
        sa.Column("experience_level", sa.String(32)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "unit_system IN ('metric', 'imperial')",
            name="ck_athlete_profiles_unit_system_valid",
        ),
        sa.CheckConstraint(
            "height_m IS NULL OR height_m > 0",
            name="ck_athlete_profiles_height_positive",
        ),
        sa.CheckConstraint(
            "weight_kg IS NULL OR weight_kg > 0",
            name="ck_athlete_profiles_weight_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_athlete_user"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_athlete_profiles"),
        sa.UniqueConstraint("user_id", name="uq_athlete_profiles_user_id"),
    )

    op.create_table(
        "integration_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_account_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("provider_metadata", sa.JSON()),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("sync_cursor", sa.Text()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'refresh_required', 'error', "
            "'disconnected', 'revoked')",
            name="ck_integration_accounts_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athlete_profiles.id"],
            ondelete="CASCADE",
            name="fk_integration_athlete",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_integration_accounts"),
        sa.UniqueConstraint(
            "athlete_id",
            "provider",
            "external_account_id",
            name="uq_integration_account_external_identity",
        ),
    )
    op.create_index(
        "ix_integration_accounts_athlete_id", "integration_accounts", ["athlete_id"]
    )

    op.create_table(
        "oauth_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_account_id", sa.Uuid(), nullable=False),
        # SECURITY TODO: plaintext columns are temporary. Production requires
        # envelope encryption and keys managed outside PostgreSQL.
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text()),
        sa.Column("token_type", sa.String(32), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("key_version", sa.String(64), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_oauth_credentials_expiry_after_creation"
        ),
        sa.ForeignKeyConstraint(
            ["integration_account_id"],
            ["integration_accounts.id"],
            ondelete="CASCADE",
            name="fk_oauth_credential_integration",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_credentials"),
        sa.UniqueConstraint(
            "integration_account_id", name="uq_oauth_credentials_integration_account_id"
        ),
    )

    op.create_table(
        "completed_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        # Temporary until the separately documented ActivitySource is authorized.
        sa.Column("source_integration_account_id", sa.Uuid()),
        sa.Column("external_activity_id", sa.String(255)),
        sa.Column("source_summary", sa.String(32), nullable=False),
        sa.Column("sport", sa.String(32), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("elapsed_time_s", sa.Integer(), nullable=False),
        sa.Column("moving_time_s", sa.Integer()),
        sa.Column("distance_m", sa.Float()),
        sa.Column("elevation_gain_m", sa.Float()),
        sa.Column("average_heart_rate_bpm", sa.Float()),
        sa.Column("max_heart_rate_bpm", sa.Float()),
        sa.Column("average_power_w", sa.Float()),
        sa.Column("max_power_w", sa.Float()),
        sa.Column("average_speed_mps", sa.Float()),
        sa.Column("calories_kcal", sa.Float()),
        sa.Column("rpe", sa.Integer()),
        sa.Column("session_rpe_load", sa.Float()),
        sa.Column("indoor", sa.Boolean()),
        sa.Column("commute", sa.Boolean()),
        sa.Column("description", sa.Text()),
        sa.Column("provider_created_at", sa.DateTime(timezone=True)),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
        sa.Column("provider_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "sport IN ('swimming', 'cycling', 'running', 'strength', "
            "'multisport', 'other')",
            name="ck_completed_activities_sport_valid",
        ),
        sa.CheckConstraint(
            "elapsed_time_s >= 0", name="ck_completed_activities_elapsed_nonnegative"
        ),
        sa.CheckConstraint(
            "moving_time_s IS NULL OR moving_time_s >= 0",
            name="ck_completed_activities_moving_nonnegative",
        ),
        sa.CheckConstraint(
            "distance_m IS NULL OR distance_m >= 0",
            name="ck_completed_activities_distance_nonnegative",
        ),
        sa.CheckConstraint(
            "rpe IS NULL OR rpe BETWEEN 1 AND 10",
            name="ck_completed_activities_rpe_valid",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athlete_profiles.id"],
            ondelete="CASCADE",
            name="fk_activity_athlete",
        ),
        sa.ForeignKeyConstraint(
            ["source_integration_account_id"],
            ["integration_accounts.id"],
            ondelete="SET NULL",
            name="fk_activity_source_integration",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_completed_activities"),
        sa.UniqueConstraint(
            "source_integration_account_id",
            "external_activity_id",
            name="uq_completed_activity_source_external_id",
        ),
    )
    op.create_index(
        "ix_completed_activities_athlete_id", "completed_activities", ["athlete_id"]
    )
    op.create_index(
        "ix_completed_activities_start_at", "completed_activities", ["start_at"]
    )
    op.create_index(
        "ix_completed_activities_source_integration_account_id",
        "completed_activities",
        ["source_integration_account_id"],
    )

    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("athlete_id", sa.Uuid(), nullable=False),
        sa.Column("integration_account_id", sa.Uuid(), nullable=False),
        sa.Column("parent_job_id", sa.Uuid()),
        sa.Column("requested_by_user_id", sa.Uuid()),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("cursor_before", sa.Text()),
        sa.Column("cursor_after", sa.Text()),
        sa.Column("range_start", sa.DateTime(timezone=True)),
        sa.Column("range_end", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("stats", sa.JSON()),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'retry_scheduled', 'succeeded', "
            "'partially_succeeded', 'failed', 'cancelled')",
            name="ck_sync_jobs_status_valid",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_sync_jobs_attempt_count_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athlete_profiles.id"],
            ondelete="CASCADE",
            name="fk_sync_job_athlete",
        ),
        sa.ForeignKeyConstraint(
            ["integration_account_id"],
            ["integration_accounts.id"],
            ondelete="CASCADE",
            name="fk_sync_job_integration",
        ),
        sa.ForeignKeyConstraint(
            ["parent_job_id"],
            ["sync_jobs.id"],
            ondelete="SET NULL",
            name="fk_sync_job_parent",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_sync_job_requester",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sync_jobs"),
        sa.UniqueConstraint(
            "integration_account_id",
            "job_type",
            "idempotency_key",
            name="uq_sync_job_idempotency",
        ),
    )
    op.create_index("ix_sync_jobs_athlete_id", "sync_jobs", ["athlete_id"])
    op.create_index(
        "ix_sync_jobs_integration_account_id", "sync_jobs", ["integration_account_id"]
    )
    op.create_index("ix_sync_jobs_next_retry_at", "sync_jobs", ["next_retry_at"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("integration_account_id", sa.Uuid()),
        sa.Column("sync_job_id", sa.Uuid()),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("deduplication_key", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload_hash", sa.String(128), nullable=False),
        sa.Column("external_owner_id", sa.String(255)),
        sa.Column("external_object_id", sa.String(255)),
        sa.Column("external_event_time", sa.DateTime(timezone=True)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("raw_payload", sa.JSON()),
        sa.Column("raw_payload_expires_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('received', 'ignored', 'queued', 'processing', "
            "'processed', 'failed', 'dead_lettered')",
            name="ck_webhook_events_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["integration_account_id"],
            ["integration_accounts.id"],
            ondelete="SET NULL",
            name="fk_webhook_integration",
        ),
        sa.ForeignKeyConstraint(
            ["sync_job_id"],
            ["sync_jobs.id"],
            ondelete="SET NULL",
            name="fk_webhook_sync_job",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_webhook_events"),
        sa.UniqueConstraint(
            "provider",
            "deduplication_key",
            name="uq_webhook_event_idempotency",
        ),
    )
    op.create_index(
        "ix_webhook_events_integration_account_id",
        "webhook_events",
        ["integration_account_id"],
    )
    op.create_index("ix_webhook_events_sync_job_id", "webhook_events", ["sync_job_id"])
    op.create_index("ix_webhook_events_received_at", "webhook_events", ["received_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("athlete_id", sa.Uuid()),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100)),
        sa.Column("entity_id", sa.Uuid()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_hash", sa.String(128)),
        sa.Column("user_agent_summary", sa.String(300)),
        sa.Column("reason", sa.Text()),
        sa.Column("event_metadata", sa.JSON()),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_audit_actor",
        ),
        sa.ForeignKeyConstraint(
            ["athlete_id"],
            ["athlete_profiles.id"],
            ondelete="SET NULL",
            name="fk_audit_athlete",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_athlete_id", "audit_events", ["athlete_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("webhook_events")
    op.drop_table("sync_jobs")
    op.drop_table("completed_activities")
    op.drop_table("oauth_credentials")
    op.drop_table("integration_accounts")
    op.drop_table("athlete_profiles")
    op.drop_table("users")
