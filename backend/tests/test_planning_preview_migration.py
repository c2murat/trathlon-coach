from alembic import command
from sqlalchemy import inspect

from test_athlete_onboarding_migration import migrated_database


def test_0025_creates_and_drops_only_planning_previews(monkeypatch):
    with migrated_database(monkeypatch) as (engine, cfg):
        command.upgrade(cfg, "0025_training_plan_previews")
        inspector = inspect(engine)
        assert "training_plan_previews" in inspector.get_table_names()
        columns = {item["name"]: item for item in inspector.get_columns("training_plan_previews")}
        assert {"artifact", "artifact_fingerprint", "created_at", "updated_at"} <= set(columns)
        assert "accepted_training_plan_id" not in columns
        assert {item["referred_table"] for item in inspector.get_foreign_keys("training_plan_previews")} == {
            "athlete_profiles", "users",
        }
        assert {item["name"] for item in inspector.get_indexes("training_plan_previews")} >= {
            "ix_training_plan_previews_athlete_created", "ix_training_plan_previews_fingerprint",
        }
        plan_columns = {item["name"] for item in inspector.get_columns("training_plans")}
        assert "source_preview_id" in plan_columns
        assert any(item["referred_table"] == "training_plan_previews" for item in inspector.get_foreign_keys("training_plans"))
        assert any(item["name"] == "uq_training_plans_source_preview" for item in inspector.get_unique_constraints("training_plans"))
        command.downgrade(cfg, "0024_planning_preferences")
        assert "training_plan_previews" not in inspect(engine).get_table_names()
        assert "source_preview_id" not in {item["name"] for item in inspect(engine).get_columns("training_plans")}
        engine.dispose()
