"""Add explicit user-athlete memberships and backfill legacy owners."""

from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa


revision = "0014_user_athlete_memberships"
down_revision = "0013_training_status"
branch_labels = None
depends_on = None

TABLE = "user_athlete_memberships"
USER_INDEX = "ix_user_athlete_memberships_user_id"
ATHLETE_INDEX = "ix_user_athlete_memberships_athlete_profile_id"
MEMBERSHIP_NAMESPACE = UUID("d28ac60a-1db2-4cd2-9c5d-458903922c61")


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("athlete_profile_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'coach', 'editor', 'viewer')",
            name="ck_user_athlete_memberships_role_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["athlete_profile_id"], ["athlete_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "athlete_profile_id",
            name="uq_user_athlete_memberships_user_athlete",
        ),
    )
    op.create_index(USER_INDEX, TABLE, ["user_id"], unique=False)
    op.create_index(ATHLETE_INDEX, TABLE, ["athlete_profile_id"], unique=False)

    connection = op.get_bind()
    athlete_profiles = sa.table(
        "athlete_profiles",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    memberships = sa.table(
        TABLE,
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("athlete_profile_id", sa.Uuid()),
        sa.column("role", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_default", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = connection.execute(
        sa.select(
            athlete_profiles.c.id,
            athlete_profiles.c.user_id,
            athlete_profiles.c.created_at,
            athlete_profiles.c.updated_at,
        ).order_by(athlete_profiles.c.id)
    ).mappings()
    for row in rows:
        athlete_id = row["id"]
        connection.execute(
            memberships.insert().values(
                id=uuid5(MEMBERSHIP_NAMESPACE, str(athlete_id)),
                user_id=row["user_id"],
                athlete_profile_id=athlete_id,
                role="owner",
                is_active=True,
                is_default=True,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )


def downgrade():
    op.drop_index(ATHLETE_INDEX, table_name=TABLE)
    op.drop_index(USER_INDEX, table_name=TABLE)
    op.drop_table(TABLE)
