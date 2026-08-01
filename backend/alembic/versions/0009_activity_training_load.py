"""Persist deterministic per-activity training load (0.7B.2)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0009_activity_training_load"; down_revision="0008_performance_references"; branch_labels=None; depends_on=None
def upgrade():
 op.create_table("activity_training_loads",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.Column("completed_activity_id",sa.Uuid(),sa.ForeignKey("completed_activities.id",ondelete="CASCADE"),nullable=False),sa.Column("load_value",sa.Float()),sa.Column("method",sa.String(32),nullable=False),sa.Column("unit",sa.String(32),nullable=False),sa.Column("coverage",sa.String(24),nullable=False),sa.Column("quality",sa.String(24)),sa.Column("reason",sa.String(32)),sa.Column("algorithm_version",sa.String(32),nullable=False),sa.Column("duration_seconds",sa.Float()),sa.Column("effective_intensity",sa.Float()),sa.Column("reference_value",sa.Float()),sa.Column("reference_metric",sa.String(32)),sa.Column("source_metrics",sa.JSON(),nullable=False),sa.Column("warnings",sa.JSON(),nullable=False),sa.Column("calculated_at",sa.DateTime(timezone=True),nullable=False),sa.CheckConstraint("load_value IS NULL OR load_value >= 0",name="ck_training_load_nonnegative"),sa.UniqueConstraint("completed_activity_id","algorithm_version",name="uq_training_load_activity_algorithm"))
 op.create_index("ix_training_load_activity","activity_training_loads",["completed_activity_id"]);op.create_index("ix_training_load_algorithm","activity_training_loads",["algorithm_version"])
def downgrade():
 op.drop_index("ix_training_load_algorithm",table_name="activity_training_loads");op.drop_index("ix_training_load_activity",table_name="activity_training_loads");op.drop_table("activity_training_loads")
