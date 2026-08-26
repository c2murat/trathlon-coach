from alembic import command
from sqlalchemy import inspect

from test_athlete_onboarding_migration import migrated_database


def test_0024_creates_and_drops_only_planning_preferences(monkeypatch):
    with migrated_database(monkeypatch) as (engine, cfg):
        command.upgrade(cfg, "0024_planning_preferences")
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"athlete_planning_preference_versions", "athlete_availability_slots"} <= tables
        foreign_keys = inspector.get_foreign_keys("athlete_availability_slots")
        assert any(item["referred_table"] == "athlete_planning_preference_versions" for item in foreign_keys)
        command.downgrade(cfg, "0023_competition_catalog")
        assert not ({"athlete_planning_preference_versions", "athlete_availability_slots"} & set(inspect(engine).get_table_names()))
        engine.dispose()
