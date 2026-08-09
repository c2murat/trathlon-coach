"""Add the server-side authentication session foundation.

Revision ID: 0017_authentication_base
Revises: 0016_multi_athlete_integrity
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_authentication_base"
down_revision = "0016_multi_athlete_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.create_table(
        "user_auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_user_auth_sessions_user_id_users",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_auth_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_user_auth_sessions_token_hash"),
    )
    op.create_index(
        "ix_user_auth_sessions_user_id", "user_auth_sessions", ["user_id"]
    )
    op.create_index(
        "ix_user_auth_sessions_expires_at", "user_auth_sessions", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_auth_sessions_expires_at", table_name="user_auth_sessions")
    op.drop_index("ix_user_auth_sessions_user_id", table_name="user_auth_sessions")
    op.drop_table("user_auth_sessions")
    op.drop_column("users", "password_hash")
