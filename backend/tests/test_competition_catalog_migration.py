from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, text

from test_athlete_onboarding_migration import migrated_database, seed


def insert_goal(engine, user_id, athlete_id, category):
 goal_id = uuid4()
 with engine.begin() as connection:
  connection.execute(
   text("""
    INSERT INTO competition_goals(
     id, athlete_profile_id, name, event_date, timezone, event_category,
     event_format, priority, status, created_by_user_id, source_provider,
     source_external_id, source_snapshot, created_at, updated_at
    ) VALUES (
     :id, :athlete, 'Migration fixture', DATE '2027-05-01', 'UTC',
     :category, 'custom', 'B', 'active', :user, 'fixture', :external,
     '{"fixture": true}'::jsonb, now(), now()
    )
   """),
   {"id": goal_id, "athlete": athlete_id, "category": category,
    "user": user_id, "external": f"event-{category}"},
  )
  connection.execute(
   text("""
    INSERT INTO competition_goal_segments(
     id, competition_goal_id, position, sport, distance_m
    ) VALUES (:id, :goal, 1, 'run', 5000)
   """),
   {"id": uuid4(), "goal": goal_id},
  )
 return goal_id


def test_0023_upgrade_and_compatible_downgrade(monkeypatch):
 with migrated_database(monkeypatch) as (engine, cfg):
  user_id, athlete_id = seed(engine)
  command.upgrade(cfg, "0023_competition_catalog")
  insert_goal(engine, user_id, athlete_id, "running")

  inspector = inspect(engine)
  assert "competition_goal_segments" in inspector.get_table_names()
  columns = {item["name"] for item in inspector.get_columns("competition_goals")}
  assert {"source_provider", "source_external_id", "source_snapshot",
          "source_retrieved_at", "city", "region", "country"} <= columns
  assert "uq_competition_goals_athlete_source" in {
   item["name"] for item in inspector.get_indexes("competition_goals")
  }

  command.downgrade(cfg, "0022_training_planning_base")
  inspector = inspect(engine)
  assert "competition_goal_segments" not in inspector.get_table_names()
  assert "source_provider" not in {
   item["name"] for item in inspector.get_columns("competition_goals")
  }
  with engine.connect() as connection:
   assert connection.scalar(text("SELECT event_category FROM competition_goals")) == "running"
  engine.dispose()


@pytest.mark.parametrize("category", ["duathlon", "aquathlon"])
def test_0023_downgrade_fails_before_destructive_changes(monkeypatch, category):
 with migrated_database(monkeypatch) as (engine, cfg):
  user_id, athlete_id = seed(engine)
  command.upgrade(cfg, "0023_competition_catalog")
  goal_id = insert_goal(engine, user_id, athlete_id, category)

  with pytest.raises(RuntimeError, match="Cannot safely downgrade 0023_competition_catalog"):
   command.downgrade(cfg, "0022_training_planning_base")

  inspector = inspect(engine)
  assert "competition_goal_segments" in inspector.get_table_names()
  assert {"source_provider", "source_external_id", "source_snapshot"} <= {
   item["name"] for item in inspector.get_columns("competition_goals")
  }
  assert "uq_competition_goals_athlete_source" in {
   item["name"] for item in inspector.get_indexes("competition_goals")
  }
  with engine.connect() as connection:
   row = connection.execute(
    text("""
     SELECT event_category, source_provider, source_external_id,
            source_snapshot
     FROM competition_goals WHERE id=:id
    """),
    {"id": goal_id},
   ).one()
   assert row.event_category == category
   assert row.source_provider == "fixture"
   assert row.source_external_id == f"event-{category}"
   assert row.source_snapshot == {"fixture": True}
   assert connection.scalar(
    text("SELECT count(*) FROM competition_goal_segments WHERE competition_goal_id=:id"),
    {"id": goal_id},
   ) == 1
  engine.dispose()
