"""Enforce relational multi-athlete integrity.

Revision ID: 0016_multi_athlete_integrity
Revises: 0015_strava_oauth_state_athlete
"""

from alembic import op

revision = "0016_multi_athlete_integrity"
down_revision = "0015_strava_oauth_state_athlete"
branch_labels = None
depends_on = None


PRECHECKS = """
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM integration_accounts WHERE status='active' AND deleted_at IS NULL GROUP BY athlete_id,provider HAVING count(*)>1) THEN RAISE EXCEPTION 'multi-athlete integrity: duplicate active integration account'; END IF;
 IF EXISTS (SELECT 1 FROM completed_activities a JOIN integration_accounts i ON i.id=a.source_integration_account_id WHERE a.athlete_id<>i.athlete_id) THEN RAISE EXCEPTION 'multi-athlete integrity: activity/account tenant mismatch'; END IF;
 IF EXISTS (SELECT 1 FROM sync_jobs j JOIN integration_accounts i ON i.id=j.integration_account_id WHERE j.athlete_id<>i.athlete_id) THEN RAISE EXCEPTION 'multi-athlete integrity: job/account tenant mismatch'; END IF;
END $$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(PRECHECKS)
    op.execute("CREATE UNIQUE INDEX uq_integration_accounts_active_athlete_provider ON integration_accounts (athlete_id, provider) WHERE status='active' AND deleted_at IS NULL")
    op.execute("""CREATE FUNCTION enforce_activity_integration_tenant() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.source_integration_account_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM integration_accounts i WHERE i.id=NEW.source_integration_account_id AND i.athlete_id=NEW.athlete_id) THEN RAISE EXCEPTION 'integration_tenant_mismatch: activity/account' USING ERRCODE='23514'; END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER trg_completed_activity_integration_tenant BEFORE INSERT OR UPDATE OF athlete_id,source_integration_account_id ON completed_activities FOR EACH ROW EXECUTE FUNCTION enforce_activity_integration_tenant()")
    op.execute("""CREATE FUNCTION enforce_sync_job_integration_tenant() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NOT EXISTS (SELECT 1 FROM integration_accounts i WHERE i.id=NEW.integration_account_id AND i.athlete_id=NEW.athlete_id) THEN RAISE EXCEPTION 'integration_tenant_mismatch: job/account' USING ERRCODE='23514'; END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER trg_sync_job_integration_tenant BEFORE INSERT OR UPDATE OF athlete_id,integration_account_id ON sync_jobs FOR EACH ROW EXECUTE FUNCTION enforce_sync_job_integration_tenant()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_sync_job_integration_tenant ON sync_jobs")
    op.execute("DROP FUNCTION IF EXISTS enforce_sync_job_integration_tenant()")
    op.execute("DROP TRIGGER IF EXISTS trg_completed_activity_integration_tenant ON completed_activities")
    op.execute("DROP FUNCTION IF EXISTS enforce_activity_integration_tenant()")
    op.execute("DROP INDEX IF EXISTS uq_integration_accounts_active_athlete_provider")
