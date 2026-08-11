from datetime import timezone
import warnings

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base, utc_now
from app.db.models import AthleteProfile, ManualStrengthSession, ManualStrengthTrainingLoad, User


@pytest.fixture
def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_connection, connection_record):
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="model@example.com", normalized_email="model@example.com", auth_subject="model")
        athlete = AthleteProfile(display_name="Test athlete", timezone="UTC", unit_system="metric")
        session.add(athlete)
        session.flush()
        yield session, athlete
    engine.dispose()


def make_rows(session, athlete, *, duration=60, rpe=8, version="0.7e.1"):
    now = utc_now()
    strength = ManualStrengthSession(athlete_id=athlete.id, started_at=now, timezone_name="UTC", duration_minutes=duration, body_regions=["full_body"], perceived_exertion=rpe)
    load = ManualStrengthTrainingLoad(session=strength, load_value=80, method="strength_rpe", unit="points", quality="medium", warnings=[], algorithm_version=version, calculated_at=now)
    session.add(strength)
    return strength, load


def test_models_are_registered_and_relationship_round_trips(database_session):
    session, athlete = database_session
    strength, load = make_rows(session, athlete)
    session.commit()
    assert Base.metadata.tables["manual_strength_sessions"] is ManualStrengthSession.__table__
    assert Base.metadata.tables["manual_strength_training_loads"] is ManualStrengthTrainingLoad.__table__
    assert strength.training_loads == [load]
    assert load.session is strength
    assert strength.started_at.tzinfo is timezone.utc
    assert load.calculated_at.tzinfo is timezone.utc


def test_session_algorithm_version_is_unique(database_session):
    session, athlete = database_session
    strength, _ = make_rows(session, athlete)
    session.commit()
    session.add(ManualStrengthTrainingLoad(session_id=strength.id, load_value=80, method="strength_rpe", unit="points", quality="medium", warnings=[], algorithm_version="0.7e.1", calculated_at=utc_now()))
    with pytest.raises(IntegrityError):
        session.commit()


def test_delete_session_cascades_to_load(database_session):
    session, athlete = database_session
    strength, load = make_rows(session, athlete)
    session.commit()
    load_id = load.id
    session.delete(strength)
    session.commit()
    assert session.get(ManualStrengthTrainingLoad, load_id) is None


@pytest.mark.parametrize(("duration", "rpe"), [(0, 5), (1441, 5), (60, 0), (60, 11)])
def test_database_constraints_reject_invalid_values(database_session, duration, rpe):
    session, athlete = database_session
    make_rows(session, athlete, duration=duration, rpe=rpe)
    with pytest.raises(IntegrityError):
        session.commit()


def test_mapping_configuration_emits_no_sawarnings(database_session):
    session, athlete = database_session
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always', SAWarning)
        make_rows(session, athlete)
        session.flush()
    assert not [warning for warning in captured if issubclass(warning.category, SAWarning)]
