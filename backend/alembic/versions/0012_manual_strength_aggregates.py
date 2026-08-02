"""Add manual strength components to training load aggregates."""

from alembic import op
import sqlalchemy as sa

revision = "0012_manual_strength_aggregates"
down_revision = "0011_manual_strength_sessions"
branch_labels = None
depends_on = None

DAILY = "athlete_daily_training_loads"
WEEKLY = "athlete_weekly_training_loads"


def _add_components(table_name: str) -> None:
    op.add_column(table_name, sa.Column("endurance_load", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column(table_name, sa.Column("strength_load", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column(table_name, sa.Column("strength_session_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(table_name, sa.Column("manual_strength_algorithm_version", sa.String(32), nullable=False, server_default="0.7e.1"))
    op.execute(sa.text(f"UPDATE {table_name} SET endurance_load = total_load"))
    for column in ("endurance_load", "strength_load", "strength_session_count", "manual_strength_algorithm_version"):
        op.alter_column(table_name, column, server_default=None)


def upgrade():
    _add_components(DAILY)
    _add_components(WEEKLY)
    op.drop_constraint("uq_daily_load_configuration", DAILY, type_="unique")
    op.create_unique_constraint("uq_daily_load_configuration", DAILY, ["athlete_profile_id", "local_date", "timezone_name", "source_load_algorithm_version", "manual_strength_algorithm_version", "aggregation_algorithm_version"])
    op.drop_constraint("uq_weekly_load_configuration", WEEKLY, type_="unique")
    op.create_unique_constraint("uq_weekly_load_configuration", WEEKLY, ["athlete_profile_id", "iso_year", "iso_week", "timezone_name", "source_load_algorithm_version", "manual_strength_algorithm_version", "aggregation_algorithm_version"])
    for table_name, prefix in ((DAILY, "daily"), (WEEKLY, "weekly")):
        op.create_check_constraint(f"ck_{prefix}_endurance_load_nonnegative", table_name, "endurance_load >= 0")
        op.create_check_constraint(f"ck_{prefix}_strength_load_nonnegative", table_name, "strength_load >= 0")
        op.create_check_constraint(f"ck_{prefix}_strength_count_nonnegative", table_name, "strength_session_count >= 0")
        op.create_check_constraint(f"ck_{prefix}_manual_version_not_empty", table_name, "length(trim(manual_strength_algorithm_version)) > 0")


def downgrade():
    for table_name, prefix in ((WEEKLY, "weekly"), (DAILY, "daily")):
        op.drop_constraint(f"ck_{prefix}_manual_version_not_empty", table_name, type_="check")
        op.drop_constraint(f"ck_{prefix}_strength_count_nonnegative", table_name, type_="check")
        op.drop_constraint(f"ck_{prefix}_strength_load_nonnegative", table_name, type_="check")
        op.drop_constraint(f"ck_{prefix}_endurance_load_nonnegative", table_name, type_="check")
    op.drop_constraint("uq_weekly_load_configuration", WEEKLY, type_="unique")
    op.create_unique_constraint("uq_weekly_load_configuration", WEEKLY, ["athlete_profile_id", "iso_year", "iso_week", "timezone_name", "source_load_algorithm_version", "aggregation_algorithm_version"])
    op.drop_constraint("uq_daily_load_configuration", DAILY, type_="unique")
    op.create_unique_constraint("uq_daily_load_configuration", DAILY, ["athlete_profile_id", "local_date", "timezone_name", "source_load_algorithm_version", "aggregation_algorithm_version"])
    for table_name in (WEEKLY, DAILY):
        op.drop_column(table_name, "manual_strength_algorithm_version")
        op.drop_column(table_name, "strength_session_count")
        op.drop_column(table_name, "strength_load")
        op.drop_column(table_name, "endurance_load")
