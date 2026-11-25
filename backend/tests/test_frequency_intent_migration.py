from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from tests.test_athlete_onboarding_migration import migrated_database


def test_0028_upgrade_downgrade_data_and_constraints(monkeypatch):
    with migrated_database(monkeypatch) as (engine, cfg):
        command.upgrade(cfg, '0027_session_reschedule_links')
        identifier = uuid4()
        with engine.begin() as db:
            # No model query against a schema preceding the new nullable column.
            athlete = uuid4()
            db.execute(text("INSERT INTO athlete_profiles (id,display_name,timezone,unit_system,created_at,updated_at) VALUES (:id,'Frequency test','Europe/Madrid','metric',now(),now())"), {'id': athlete})
            db.execute(text('INSERT INTO athlete_planning_preference_versions (id,athlete_profile_id,version_number,max_sessions_per_day,max_sessions_per_week,preferred_rest_days,strength_sessions_per_week,created_at) VALUES (:id,:a,1,2,12,\'[]\',2,now())'), {'id': identifier, 'a': athlete})
        tables = set(inspect(engine).get_table_names())
        command.upgrade(cfg, '0028_frequency_intent')
        col = next(c for c in inspect(engine).get_columns('athlete_planning_preference_versions') if c['name'] == 'target_sessions_per_week')
        assert col['nullable'] and col['default'] is None
        assert set(inspect(engine).get_table_names()) == tables
        with engine.connect() as db:
            assert db.scalar(text('SELECT target_sessions_per_week FROM athlete_planning_preference_versions WHERE id=:id'), {'id': identifier}) is None
        for bad in (0,29,13):
            with pytest.raises(IntegrityError), engine.begin() as db:
                db.execute(text('UPDATE athlete_planning_preference_versions SET target_sessions_per_week=:n WHERE id=:id'), {'n':bad,'id':identifier})
        with engine.begin() as db:
            db.execute(text('UPDATE athlete_planning_preference_versions SET target_sessions_per_week=7 WHERE id=:id'), {'id':identifier})
        command.downgrade(cfg, '0027_session_reschedule_links')
        assert 'target_sessions_per_week' not in {c['name'] for c in inspect(engine).get_columns('athlete_planning_preference_versions')}
        with engine.connect() as db:
            assert tuple(db.execute(text('SELECT max_sessions_per_day,max_sessions_per_week,strength_sessions_per_week,preferred_rest_days FROM athlete_planning_preference_versions WHERE id=:id'), {'id':identifier}).one()) == (2,12,2,[])
        command.upgrade(cfg, '0028_frequency_intent')
        engine.dispose()
