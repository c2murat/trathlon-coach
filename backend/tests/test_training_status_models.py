from datetime import date
from decimal import Decimal
import warnings

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError, SAWarning
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base, utc_now
from app.db.models import AthleteDailyTrainingStatus, AthleteProfile, User


@pytest.fixture
def database_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        del record
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="status@example.com", normalized_email="status@example.com", auth_subject="status")
        athlete = AthleteProfile(display_name="Test athlete", timezone="Europe/Madrid", unit_system="metric")
        session.add(athlete)
        session.flush()
        yield session, athlete
    engine.dispose()


def make_status(athlete, **overrides):
    values = dict(
        athlete_profile_id=athlete.id,
        local_date=date(2026, 1, 1),
        timezone_name="Europe/Madrid",
        training_load_algorithm_version="0.7b.1",
        manual_strength_algorithm_version="0.7e.1",
        training_status_algorithm_version="0.7f.1",
        total_load=Decimal("100.00"),
        fitness=Decimal("20.00"),
        fatigue=Decimal("30.00"),
        form=Decimal("-10.00"),
        history_day_number=1,
        is_warmup=True,
        calculated_at=utc_now(),
    )
    values.update(overrides)
    return AthleteDailyTrainingStatus(**values)


def test_table_is_registered():
    assert Base.metadata.tables["athlete_daily_training_statuses"] is AthleteDailyTrainingStatus.__table__


def test_valid_row_can_be_created(database_session):
    session, athlete = database_session
    row = make_status(athlete)
    session.add(row)
    session.commit()
    assert session.get(AthleteDailyTrainingStatus, row.id) is row


def test_form_accepts_negative_values(database_session):
    session, athlete = database_session
    row = make_status(athlete, form=Decimal("-999.99"))
    session.add(row)
    session.commit()
    assert row.form == Decimal("-999.99")


@pytest.mark.parametrize(
    "overrides",
    [
        {"total_load": -1},
        {"fitness": -1},
        {"fatigue": -1},
        {"history_day_number": 0},
    ],
)
def test_nonnegative_and_history_constraints(database_session, overrides):
    session, athlete = database_session
    session.add(make_status(athlete, **overrides))
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "field",
    [
        "training_load_algorithm_version",
        "manual_strength_algorithm_version",
        "training_status_algorithm_version",
    ],
)
def test_algorithm_versions_must_not_be_empty(database_session, field):
    session, athlete = database_session
    session.add(make_status(athlete, **{field: "  "}))
    with pytest.raises(IntegrityError):
        session.commit()


def test_timezone_must_not_be_empty(database_session):
    session, athlete = database_session
    session.add(make_status(athlete, timezone_name=" "))
    with pytest.raises(IntegrityError):
        session.commit()


def test_complete_configuration_is_unique(database_session):
    session, athlete = database_session
    session.add_all([make_status(athlete), make_status(athlete)])
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    "field,value",
    [
        ("training_status_algorithm_version", "0.7f.2"),
        ("training_load_algorithm_version", "0.7b.2"),
        ("manual_strength_algorithm_version", "0.7e.2"),
        ("timezone_name", "UTC"),
    ],
)
def test_distinct_configurations_can_coexist(database_session, field, value):
    session, athlete = database_session
    session.add_all([make_status(athlete), make_status(athlete, **{field: value})])
    session.commit()
    assert len(session.query(AthleteDailyTrainingStatus).all()) == 2


def test_mapping_emits_no_new_sawarnings(database_session):
    session, athlete = database_session
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", SAWarning)
        session.add(make_status(athlete))
        session.flush()
    assert not [item for item in captured if issubclass(item.category, SAWarning)]
