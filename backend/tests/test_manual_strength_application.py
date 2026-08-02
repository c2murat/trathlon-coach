from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.manual_strength import (
    InvalidManualStrengthSessionInputError,
    InvalidManualStrengthTimezoneError,
    ManualStrengthApplication,
    ManualStrengthAthleteNotFoundError,
    ManualStrengthNotesTooLongError,
    ManualStrengthSessionNotFoundError,
    NaiveManualStrengthDatetimeError,
)
from app.db.base import Base
from app.db.models import AthleteProfile, ManualStrengthSession, ManualStrengthTrainingLoad, User
from app.domains.manual_strength import BodyRegion

NOW = datetime(2026, 8, 2, 10, tzinfo=timezone.utc)


@pytest.fixture
def app_context():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(dbapi_connection, connection_record):
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        athletes = []
        for number in (1, 2):
            user = User(email=f"app{number}@example.com", normalized_email=f"app{number}@example.com", auth_subject=f"app-{number}")
            athlete = AthleteProfile(user=user, timezone="Europe/Madrid", unit_system="metric")
            session.add(athlete)
            athletes.append(athlete)
        session.flush()
        yield session, ManualStrengthApplication(session, clock=lambda: NOW), athletes
    engine.dispose()


def create(app, athlete_id, **overrides):
    values = dict(started_at=NOW, timezone_name="Europe/Madrid", duration_minutes=60, body_regions=(BodyRegion.FULL_BODY,), perceived_exertion=8, notes=None)
    values.update(overrides)
    return app.create_manual_strength_session(athlete_id, **values)


def load_for(row):
    return next(load for load in row.training_loads if load.algorithm_version == "0.7e.1")


@pytest.mark.parametrize(
    ("rpe", "value", "method", "quality", "warnings"),
    [(8, 80, "strength_rpe", "medium", []), (None, 50, "strength_duration", "low", ["missing_perceived_exertion"])],
)
def test_create_persists_domain_load(app_context, rpe, value, method, quality, warnings):
    session, app, athletes = app_context
    row = create(app, athletes[0].id, perceived_exertion=rpe)
    session.commit()
    load = load_for(row)
    assert float(load.load_value) == value
    assert (load.method, load.unit, load.quality) == (method, "points", quality)
    assert load.warnings == warnings
    assert load.algorithm_version == "0.7e.1"
    assert all(value.utcoffset() == timedelta(0) for value in (row.started_at, row.created_at, row.updated_at, load.calculated_at))


def test_regions_are_canonical_and_do_not_multiply_load(app_context):
    session, app, athletes = app_context
    row = create(app, athletes[0].id, body_regions=(BodyRegion.GLUTES, BodyRegion.CHEST))
    single = create(app, athletes[0].id, body_regions=(BodyRegion.CHEST,))
    assert row.body_regions == ["chest", "glutes"]
    assert load_for(row).load_value == load_for(single).load_value


@pytest.mark.parametrize("regions", [(), (BodyRegion.CHEST, BodyRegion.CHEST), (BodyRegion.FULL_BODY, BodyRegion.CHEST), ("unknown",)])
def test_invalid_regions_leave_no_partial_session(app_context, regions):
    session, app, athletes = app_context
    before = session.scalar(select(func.count()).select_from(ManualStrengthSession))
    with pytest.raises(InvalidManualStrengthSessionInputError):
        create(app, athletes[0].id, body_regions=regions)
    assert session.scalar(select(func.count()).select_from(ManualStrengthSession)) == before


@pytest.mark.parametrize("overrides", [{"duration_minutes": True}, {"duration_minutes": 0}, {"perceived_exertion": True}, {"perceived_exertion": 11}])
def test_invalid_numeric_input_is_rejected(app_context, overrides):
    _, app, athletes = app_context
    with pytest.raises(InvalidManualStrengthSessionInputError):
        create(app, athletes[0].id, **overrides)


def test_datetime_timezone_and_notes_validation(app_context):
    _, app, athletes = app_context
    with pytest.raises(NaiveManualStrengthDatetimeError):
        create(app, athletes[0].id, started_at=datetime(2026, 1, 1))
    for zone in ("", "Not/A_Zone"):
        with pytest.raises(InvalidManualStrengthTimezoneError):
            create(app, athletes[0].id, timezone_name=zone)
    assert create(app, athletes[0].id, notes="  useful note  ").notes == "useful note"
    assert create(app, athletes[0].id, notes="   ").notes is None
    with pytest.raises(ManualStrengthNotesTooLongError):
        create(app, athletes[0].id, notes="x" * 2001)


def test_athlete_validation_and_owned_get(app_context):
    _, app, athletes = app_context
    row = create(app, athletes[0].id)
    assert app.get_manual_strength_session(athletes[0].id, row.id) is row
    with pytest.raises(ManualStrengthSessionNotFoundError):
        app.get_manual_strength_session(athletes[1].id, row.id)
    from uuid import uuid4
    with pytest.raises(ManualStrengthAthleteNotFoundError):
        create(app, uuid4())


def test_listing_is_isolated_and_deterministic(app_context):
    _, app, athletes = app_context
    older = create(app, athletes[0].id, started_at=NOW - timedelta(days=1))
    newer = create(app, athletes[0].id, started_at=NOW)
    create(app, athletes[1].id, started_at=NOW + timedelta(days=1))
    assert app.list_manual_strength_sessions(athletes[0].id) == (newer, older)


def test_updates_recalculate_one_current_load(app_context):
    session, app, athletes = app_context
    row = create(app, athletes[0].id)
    load_id = load_for(row).id
    session.add(
        ManualStrengthTrainingLoad(
            session_id=row.id, load_value=1, method='legacy', unit='points',
            quality='low', warnings=[], algorithm_version='legacy', calculated_at=NOW
        )
    )
    session.flush()
    app.update_manual_strength_session(athletes[0].id, row.id, duration_minutes=30)
    assert float(load_for(row).load_value) == 40
    app.update_manual_strength_session(athletes[0].id, row.id, perceived_exertion=None)
    assert float(load_for(row).load_value) == 25
    app.update_manual_strength_session(athletes[0].id, row.id, body_regions=(BodyRegion.BACK,))
    assert float(load_for(row).load_value) == 25
    assert load_for(row).id == load_id
    assert session.scalar(select(func.count()).select_from(ManualStrengthTrainingLoad)) == 1
    assert {load.algorithm_version for load in row.training_loads} == {'0.7e.1'}


def test_invalid_update_does_not_mutate_previous_state(app_context):
    _, app, athletes = app_context
    row = create(app, athletes[0].id)
    before = (row.duration_minutes, list(row.body_regions), float(load_for(row).load_value))
    with pytest.raises(InvalidManualStrengthSessionInputError):
        app.update_manual_strength_session(athletes[0].id, row.id, duration_minutes=0)
    assert (row.duration_minutes, row.body_regions, float(load_for(row).load_value)) == before


def test_recalculation_is_idempotent(app_context):
    session, app, athletes = app_context
    row = create(app, athletes[0].id)
    first = app.recalculate_manual_strength_load(athletes[0].id, row.id)
    second = app.recalculate_manual_strength_load(athletes[0].id, row.id)
    assert (first.id, first.load_value) == (second.id, second.load_value)
    assert session.scalar(select(func.count()).select_from(ManualStrengthTrainingLoad)) == 1


def test_delete_is_owned_and_cascades_without_affecting_other_athletes(app_context):
    session, app, athletes = app_context
    first = create(app, athletes[0].id)
    second = create(app, athletes[1].id)
    with pytest.raises(ManualStrengthSessionNotFoundError):
        app.delete_manual_strength_session(athletes[1].id, first.id)
    app.delete_manual_strength_session(athletes[0].id, first.id)
    assert session.get(ManualStrengthSession, first.id) is None
    assert session.get(ManualStrengthSession, second.id) is second
    assert session.scalar(select(func.count()).select_from(ManualStrengthTrainingLoad)) == 1
