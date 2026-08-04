"""Record the athlete-bound Strava OAuth state rollout.

Revision ID: 0015_strava_oauth_state_athlete
Revises: 0014_user_athlete_memberships

OAuth state is intentionally stored in the dedicated SQLite state adapter,
not in the application PostgreSQL schema.  The adapter performs the real
schema migration atomically on startup and invalidates legacy pending states.
This revision advances deployment ordering without inventing a duplicate
PostgreSQL table.
"""

from collections.abc import Sequence


revision: str = "0015_strava_oauth_state_athlete"
down_revision: str | None = "0014_user_athlete_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
