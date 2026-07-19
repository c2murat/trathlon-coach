"""Add granular historical performance references."""
from alembic import op
import sqlalchemy as sa
revision="0008_performance_references";down_revision="0007_performance_profiles";branch_labels=None;depends_on=None
def upgrade():
 op.create_table("athlete_performance_references",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("athlete_profile_id",sa.Uuid(),sa.ForeignKey("athlete_profiles.id",ondelete="CASCADE"),nullable=False),sa.Column("sport",sa.String(32),nullable=False),sa.Column("metric_type",sa.String(32),nullable=False),sa.Column("value",sa.Numeric(10,3),nullable=False),sa.Column("unit",sa.String(24),nullable=False),sa.Column("data_origin",sa.String(16),nullable=False),sa.Column("quality_level",sa.String(16),nullable=False),sa.Column("effective_from",sa.DateTime(timezone=True),nullable=False),sa.Column("measured_at",sa.DateTime(timezone=True)),sa.Column("calculation_method",sa.String(64)),sa.Column("algorithm_version",sa.String(32)),sa.Column("source_note",sa.String(500)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("athlete_profile_id","sport","metric_type","effective_from",name="uq_performance_reference_effective"))
 op.create_index("ix_performance_reference_athlete_sport_metric_date","athlete_performance_references",["athlete_profile_id","sport","metric_type","effective_from"])
def downgrade():
 op.drop_index("ix_performance_reference_athlete_sport_metric_date",table_name="athlete_performance_references");op.drop_table("athlete_performance_references")