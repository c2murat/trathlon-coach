"""Persist account plan separately from athlete membership roles."""
from alembic import op
import sqlalchemy as sa
revision="0021_user_account_plan"
down_revision="0020_unique_active_self_athlete"
branch_labels=None
depends_on=None
def upgrade()->None:
 op.add_column("users",sa.Column("account_plan",sa.String(16),nullable=True))
 op.execute("""UPDATE users u SET account_plan=CASE WHEN EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.user_id=u.id AND m.role='athlete' AND m.is_active IS TRUE) THEN 'athlete' WHEN EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.user_id=u.id AND m.role='owner' AND m.is_active IS TRUE) THEN 'owner' WHEN EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.user_id=u.id AND m.role='coach' AND m.is_active IS TRUE) THEN 'coach' ELSE 'owner' END""")
 op.alter_column("users","account_plan",nullable=False)
 op.create_check_constraint("account_plan_valid","users","account_plan IN ('owner','athlete','coach')")
def downgrade()->None:
 op.drop_constraint("account_plan_valid","users",type_="check")
 op.drop_column("users","account_plan")