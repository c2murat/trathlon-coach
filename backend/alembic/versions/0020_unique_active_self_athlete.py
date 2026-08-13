"""Enforce one active self-athlete identity per AthleteProfile.

Revision ID: 0020_unique_active_self_athlete
Revises: 0019_athlete_membership_role
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_unique_active_self_athlete"
down_revision = "0019_athlete_membership_role"
branch_labels = None
depends_on = None

INDEX = "uq_user_athlete_memberships_active_self_athlete"


def upgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (
            SELECT athlete_profile_id FROM user_athlete_memberships
            WHERE role='athlete' AND is_active IS TRUE
            GROUP BY athlete_profile_id HAVING count(*) > 1
        ) THEN
            RAISE EXCEPTION '0020 preflight: multiple active athlete memberships';
        END IF;
    END $$;""")
    op.create_index(INDEX, "user_athlete_memberships", ["athlete_profile_id"], unique=True, postgresql_where=sa.text("role = 'athlete' AND is_active IS TRUE"))


def downgrade() -> None:
    op.drop_index(INDEX, table_name="user_athlete_memberships")
