"""Allow the explicit self-service athlete membership role.

Revision ID: 0019_athlete_membership_role
Revises: 0018_athlete_onboarding
"""
from alembic import op

revision = "0019_athlete_membership_role"
down_revision = "0018_athlete_onboarding"
branch_labels = None
depends_on = None

OLD = "role IN ('owner', 'coach', 'editor', 'viewer')"
NEW = "role IN ('owner', 'athlete', 'coach', 'editor', 'viewer')"
LEGACY_CONSTRAINT = "ck_user_athlete_memberships_ck_user_athlete_memberships_558c"
CURRENT_CONSTRAINT = "ck_user_athlete_memberships_role_valid"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE user_athlete_memberships "
        f"DROP CONSTRAINT {LEGACY_CONSTRAINT}"
    )
    op.execute(
        f"ALTER TABLE user_athlete_memberships "
        f"ADD CONSTRAINT {CURRENT_CONSTRAINT} CHECK ({NEW})"
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (
            SELECT 1 FROM user_athlete_memberships WHERE role='athlete'
        ) THEN
            RAISE EXCEPTION '0019 downgrade blocked: athlete memberships exist';
        END IF;
        END $$;"""
    )
    op.execute(
        f"ALTER TABLE user_athlete_memberships "
        f"DROP CONSTRAINT {CURRENT_CONSTRAINT}"
    )
    op.execute(
        f"ALTER TABLE user_athlete_memberships "
        f"ADD CONSTRAINT {LEGACY_CONSTRAINT} CHECK ({OLD})"
    )
