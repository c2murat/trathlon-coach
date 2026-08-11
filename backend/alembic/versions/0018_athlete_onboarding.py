"""Prepare persistent multi-athlete onboarding safely.

Revision ID: 0018_athlete_onboarding
Revises: 0017_authentication_base
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_athlete_onboarding"
down_revision = "0017_authentication_base"
branch_labels = None
depends_on = None

UPGRADE_PREFLIGHT = """
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM athlete_profiles a WHERE NOT EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.athlete_profile_id=a.id AND m.role='owner' AND m.is_active IS TRUE)) THEN RAISE EXCEPTION 'athlete onboarding preflight: athlete_without_active_owner'; END IF;
 IF EXISTS (SELECT 1 FROM athlete_profiles a WHERE NOT EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.athlete_profile_id=a.id AND m.user_id=a.user_id AND m.role='owner' AND m.is_active IS TRUE)) THEN RAISE EXCEPTION 'athlete onboarding preflight: legacy_owner_membership_missing'; END IF;
 IF EXISTS (SELECT 1 FROM athlete_profiles a JOIN user_athlete_memberships m ON m.athlete_profile_id=a.id AND m.role='owner' AND m.is_active IS TRUE WHERE m.user_id<>a.user_id) THEN RAISE EXCEPTION 'athlete onboarding preflight: legacy_owner_mismatch'; END IF;
 IF EXISTS (SELECT 1 FROM user_athlete_memberships WHERE is_active IS TRUE AND is_default IS TRUE GROUP BY user_id HAVING count(*)>1) THEN RAISE EXCEPTION 'athlete onboarding preflight: multiple_active_defaults'; END IF;
 IF EXISTS (SELECT 1 FROM user_athlete_memberships WHERE is_active IS FALSE AND is_default IS TRUE) THEN RAISE EXCEPTION 'athlete onboarding preflight: inactive_default'; END IF;
 IF EXISTS (SELECT 1 FROM user_athlete_memberships m JOIN athlete_profiles a ON a.id=m.athlete_profile_id WHERE m.is_default IS TRUE AND a.deleted_at IS NOT NULL) THEN RAISE EXCEPTION 'athlete onboarding preflight: deleted_athlete_default'; END IF;
 IF EXISTS (SELECT 1 FROM user_athlete_memberships m JOIN athlete_profiles a ON a.id=m.athlete_profile_id WHERE m.is_active IS TRUE AND a.deleted_at IS NOT NULL) THEN RAISE EXCEPTION 'athlete onboarding preflight: active_membership_deleted_athlete'; END IF;
END $$;
"""

DOWNGRADE_PREFLIGHT = """
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM athlete_profiles a LEFT JOIN user_athlete_memberships m ON m.athlete_profile_id=a.id AND m.role='owner' AND m.is_active IS TRUE GROUP BY a.id HAVING count(m.id)<>1) THEN RAISE EXCEPTION 'athlete onboarding downgrade: ownership_ambiguous'; END IF;
 IF EXISTS (SELECT 1 FROM user_athlete_memberships WHERE role='owner' AND is_active IS TRUE GROUP BY user_id HAVING count(*)>1) THEN RAISE EXCEPTION 'athlete onboarding downgrade: user_owns_multiple_athletes'; END IF;
END $$;
"""

def upgrade() -> None:
    bind=op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("0018_athlete_onboarding requires PostgreSQL")
    op.execute(UPGRADE_PREFLIGHT)
    op.add_column("athlete_profiles", sa.Column("display_name", sa.String(200), nullable=True))
    op.execute("""UPDATE athlete_profiles a SET display_name=COALESCE(NULLIF(left(regexp_replace(btrim(u.display_name), '\\s+', ' ', 'g'),200),''), 'Atleta ' || left(a.id::text,8)) FROM users u WHERE u.id=a.user_id""")
    op.alter_column("athlete_profiles", "display_name", nullable=False)
    op.create_check_constraint("display_name_valid", "athlete_profiles", "char_length(btrim(display_name)) BETWEEN 1 AND 200")
    op.create_index("uq_user_athlete_memberships_active_default_user", "user_athlete_memberships", ["user_id"], unique=True, postgresql_where=sa.text("is_active IS TRUE AND is_default IS TRUE"))
    op.drop_constraint("uq_athlete_profiles_user_id", "athlete_profiles", type_="unique")
    op.drop_constraint("fk_athlete_user", "athlete_profiles", type_="foreignkey")
    op.drop_column("athlete_profiles", "user_id")

def downgrade() -> None:
    bind=op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("0018_athlete_onboarding requires PostgreSQL")
    op.execute(DOWNGRADE_PREFLIGHT)
    op.add_column("athlete_profiles", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.execute("""UPDATE athlete_profiles a SET user_id=m.user_id FROM user_athlete_memberships m WHERE m.athlete_profile_id=a.id AND m.role='owner' AND m.is_active IS TRUE""")
    op.alter_column("athlete_profiles", "user_id", nullable=False)
    op.create_foreign_key("fk_athlete_user", "athlete_profiles", "users", ["user_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_athlete_profiles_user_id", "athlete_profiles", ["user_id"])
    op.drop_index("uq_user_athlete_memberships_active_default_user", table_name="user_athlete_memberships")
    op.drop_constraint("display_name_valid", "athlete_profiles", type_="check")
    op.drop_column("athlete_profiles", "display_name")
