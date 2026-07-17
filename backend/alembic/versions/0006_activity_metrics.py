"""Add deterministic factual activity metrics."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0006_activity_metrics";down_revision="0005_activity_evidence";branch_labels=None;depends_on=None
json_type=sa.JSON().with_variant(postgresql.JSONB(),"postgresql")
def upgrade():
 op.create_table("activity_metrics",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("completed_activity_id",sa.Uuid(),sa.ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False),sa.Column("metric_key",sa.String(64),nullable=False),sa.Column("algorithm_version",sa.String(32),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.Column("value",sa.Float()),sa.Column("unit",sa.String(24)),sa.Column("source",sa.String(64)),sa.Column("sample_count",sa.Integer()),sa.Column("coverage_ratio",sa.Float()),sa.Column("quality_notes",json_type,nullable=False),sa.Column("unavailable_reason",sa.String(64)),sa.Column("calculated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("completed_activity_id","metric_key","algorithm_version",name="uq_activity_metric_activity_key_version"))
 op.create_index("ix_activity_metrics_completed_activity_id","activity_metrics",["completed_activity_id"])
def downgrade():
 op.drop_index("ix_activity_metrics_completed_activity_id",table_name="activity_metrics");op.drop_table("activity_metrics")