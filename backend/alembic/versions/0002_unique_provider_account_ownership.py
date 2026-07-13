"""Enforce one local owner for each external provider account.

Revision ID: 0002_provider_account_owner
Revises: 0001_strava_foundation
"""
from collections.abc import Sequence

from alembic import op


revision: str = "0002_provider_account_owner"
down_revision: str | None = "0001_strava_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_integration_account_provider_external_identity",
        "integration_accounts",
        ["provider", "external_account_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_integration_account_provider_external_identity",
        "integration_accounts",
        type_="unique",
    )
