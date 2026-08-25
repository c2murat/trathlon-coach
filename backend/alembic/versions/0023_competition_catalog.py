"""Multisport competition catalog and ordered segments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0023_competition_catalog";down_revision="0022_training_planning_base";branch_labels=None;depends_on=None

def upgrade()->None:
 op.drop_constraint(op.f("ck_competition_goals_competition_goal_category_valid"),"competition_goals",type_="check")
 op.create_check_constraint("competition_goal_category_valid","competition_goals","event_category IN ('triathlon','running','cycling','swimming','duathlon','aquathlon')")
 for name,size in (("city",120),("region",120),("country",120),("source_provider",64),("source_external_id",200),("source_url",1000)):op.add_column("competition_goals",sa.Column(name,sa.String(size),nullable=True))
 op.add_column("competition_goals",sa.Column("source_retrieved_at",sa.DateTime(timezone=True),nullable=True));op.add_column("competition_goals",sa.Column("source_snapshot",sa.JSON().with_variant(postgresql.JSONB(),"postgresql"),nullable=True))
 op.create_index("uq_competition_goals_athlete_source","competition_goals",["athlete_profile_id","source_provider","source_external_id"],unique=True,postgresql_where=sa.text("source_provider IS NOT NULL AND source_external_id IS NOT NULL"))
 op.create_table("competition_goal_segments",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("competition_goal_id",sa.Uuid(),sa.ForeignKey("competition_goals.id",ondelete="CASCADE"),nullable=False),sa.Column("position",sa.Integer(),nullable=False),sa.Column("sport",sa.String(16),nullable=False),sa.Column("distance_m",sa.Integer(),nullable=False),sa.Column("label",sa.String(100)),sa.Column("elevation_gain_m",sa.Integer()),sa.CheckConstraint("position >= 1",name="competition_goal_segment_position_positive"),sa.CheckConstraint("sport IN ('swim','bike','run')",name="competition_goal_segment_sport_valid"),sa.CheckConstraint("distance_m > 0",name="competition_goal_segment_distance_positive"),sa.CheckConstraint("elevation_gain_m IS NULL OR elevation_gain_m >= 0",name="competition_goal_segment_elevation_nonnegative"),sa.UniqueConstraint("competition_goal_id","position",name="uq_competition_goal_segment_position"))
 op.create_index("ix_competition_goal_segments_goal","competition_goal_segments",["competition_goal_id"])
 op.execute("""INSERT INTO competition_goal_segments(id,competition_goal_id,position,sport,distance_m) SELECT gen_random_uuid(),id,1,CASE event_category WHEN 'swimming' THEN 'swim' WHEN 'cycling' THEN 'bike' ELSE 'run' END,distance_m FROM competition_goals WHERE event_category<>'triathlon' AND distance_m>0""")
 op.execute("""INSERT INTO competition_goal_segments(id,competition_goal_id,position,sport,distance_m) SELECT gen_random_uuid(),id,v.position,v.sport,v.distance_m FROM competition_goals CROSS JOIN LATERAL (VALUES (1,'swim',swim_distance_m),(2,'bike',bike_distance_m),(3,'run',run_distance_m)) v(position,sport,distance_m) WHERE event_category='triathlon' AND v.distance_m>0""")

def downgrade()->None:
 incompatible_category=op.get_bind().scalar(sa.text("""
  SELECT event_category
  FROM competition_goals
  WHERE event_category NOT IN ('triathlon','running','cycling','swimming')
  LIMIT 1
 """))
 if incompatible_category is not None:
  raise RuntimeError(
   "Cannot safely downgrade 0023_competition_catalog to "
   "0022_training_planning_base while competition goals use "
   "multisport categories unsupported by 0022 "
   f"(found {incompatible_category!r})."
  )
 op.drop_index("ix_competition_goal_segments_goal",table_name="competition_goal_segments");op.drop_table("competition_goal_segments");op.drop_index("uq_competition_goals_athlete_source",table_name="competition_goals")
 for name in ("source_snapshot","source_retrieved_at","source_url","source_external_id","source_provider","country","region","city"):op.drop_column("competition_goals",name)
 op.drop_constraint(op.f("ck_competition_goals_competition_goal_category_valid"),"competition_goals",type_="check");op.create_check_constraint("competition_goal_category_valid","competition_goals","event_category IN ('triathlon','running','cycling','swimming')")
