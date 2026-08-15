from alembic import command
from sqlalchemy import inspect
from test_athlete_onboarding_migration import migrated_database

def test_0022_upgrade_and_downgrade_create_planning_foundation(monkeypatch):
 with migrated_database(monkeypatch) as (engine,cfg):
  command.upgrade(cfg,"0021_user_account_plan");command.upgrade(cfg,"0022_training_planning_base");tables=set(inspect(engine).get_table_names());expected={"competition_goals","training_plans","training_plan_goals","planned_training_sessions","structured_workouts"};assert expected<=tables
  goal_checks={x["name"] for x in inspect(engine).get_check_constraints("competition_goals")};assert "ck_competition_goals_competition_goal_priority_valid" in goal_checks
  assert {x["name"] for x in inspect(engine).get_indexes("competition_goals")} >= {"ix_competition_goals_athlete_date","ix_competition_goals_creator"}
  command.downgrade(cfg,"0021_user_account_plan");assert not(expected&set(inspect(engine).get_table_names()));engine.dispose()
