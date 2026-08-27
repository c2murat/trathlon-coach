"""Server-side immutable planning previews."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_training_plan_previews"
down_revision = "0024_planning_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "training_plan_previews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("athlete_profile_id", sa.Uuid(), sa.ForeignKey("athlete_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("accepted_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("artifact", json_document, nullable=False),
        sa.Column("artifact_fingerprint", sa.String(64), nullable=False),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column("configuration_version", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending','accepted')", name="training_plan_preview_status_valid"),
    )
    op.create_index("ix_training_plan_previews_athlete_created", "training_plan_previews", ["athlete_profile_id", "created_at"])
    op.create_index("ix_training_plan_previews_fingerprint", "training_plan_previews", ["artifact_fingerprint"])
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.add_column(sa.Column("source_preview_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key("fk_training_plans_source_preview_id_training_plan_previews", "training_plan_previews", ["source_preview_id"], ["id"], ondelete="RESTRICT")
        batch_op.create_unique_constraint("uq_training_plans_source_preview", ["source_preview_id"])


def downgrade() -> None:
    with op.batch_alter_table("training_plans") as batch_op:
        batch_op.drop_constraint("uq_training_plans_source_preview", type_="unique")
        batch_op.drop_constraint("fk_training_plans_source_preview_id_training_plan_previews", type_="foreignkey")
        batch_op.drop_column("source_preview_id")
    op.drop_index("ix_training_plan_previews_fingerprint", table_name="training_plan_previews")
    op.drop_index("ix_training_plan_previews_athlete_created", table_name="training_plan_previews")
    op.drop_table("training_plan_previews")
