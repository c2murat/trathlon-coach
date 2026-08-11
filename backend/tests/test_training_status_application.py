from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.training_status import (
    DuplicateTrainingStatusSourceDateError,
    InvalidTrainingStatusApplicationRangeError,
    InvalidTrainingStatusSourceDataError,
    InvalidTrainingStatusTimezoneError,
    InvalidTrainingStatusVersionError,
    TrainingStatusApplication,
    TrainingStatusAthleteNotFoundError,
    TrainingStatusPersistenceError,
)
from app.db.base import Base
from app.db.models import (
    AthleteDailyTrainingLoad,
    AthleteDailyTrainingStatus,
    AthleteProfile,
    User,
)
from app.domains.training_status import calculate_training_status_series, DailyTrainingLoadInput


DAY = date(2026, 1, 1)
NOW = datetime(2026, 8, 3, 10, tzinfo=timezone.utc)
LOAD_VERSION = "0.7b.1"
MANUAL_VERSION = "0.7e.1"


@pytest.fixture
def app_context():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        del record
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        athletes = []
        for number in (1, 2):
            user = User(
                email=f"status-app-{number}@example.com",
                normalized_email=f"status-app-{number}@example.com",
                auth_subject=f"status-app-{number}",
            )
            athlete = AthleteProfile(display_name="Test athlete", timezone="Europe/Madrid", unit_system="metric")
            session.add(athlete)
            athletes.append(athlete)
        session.flush()
        yield session, TrainingStatusApplication(session, clock=lambda: NOW), athletes
    engine.dispose()


def add_source(session, athlete, offset, load, **overrides):
    values = dict(
        athlete_profile_id=athlete.id,
        local_date=DAY + timedelta(days=offset),
        timezone_name="Europe/Madrid",
        source_load_algorithm_version=LOAD_VERSION,
        manual_strength_algorithm_version=MANUAL_VERSION,
        aggregation_algorithm_version="0.7c.1",
        total_load=Decimal(str(load)),
        endurance_load=Decimal("999"),
        strength_load=Decimal("999"),
        strength_session_count=1,
        activity_count=1,
        loaded_activity_count=1,
        null_load_activity_count=0,
        total_duration_seconds=Decimal("3600"),
        coverage="complete",
        quality="high",
        warnings=[],
        activity_ids=[],
        calculated_at=NOW,
    )
    values.update(overrides)
    row = AthleteDailyTrainingLoad(**values)
    session.add(row)
    session.flush()
    return row


def arguments(**overrides):
    values = dict(
        start_date=DAY,
        end_date=DAY,
        timezone_name="Europe/Madrid",
        training_load_algorithm_version=LOAD_VERSION,
        manual_strength_algorithm_version=MANUAL_VERSION,
    )
    values.update(overrides)
    return values


def recalculate(app, athlete, **overrides):
    return app.recalculate_training_status(athlete.id, **arguments(**overrides))


def test_recalculates_one_day_from_total_load_only(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 80)
    result = recalculate(app, athletes[0])
    assert len(result) == 1
    assert result[0].total_load == Decimal("80.00")
    assert result[0].total_load != Decimal("1998.00")


def test_recalculates_consecutive_days_and_persists_domain_values(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 100)
    add_source(session, athletes[0], 1, 50)
    result = recalculate(app, athletes[0], end_date=DAY + timedelta(days=1))
    expected = calculate_training_status_series(
        (DailyTrainingLoadInput(DAY, 100), DailyTrainingLoadInput(DAY + timedelta(days=1), 50))
    )
    assert [(row.fitness, row.fatigue, row.form) for row in result] == [
        (Decimal(f"{day.fitness:.2f}"), Decimal(f"{day.fatigue:.2f}"), Decimal(f"{day.form:.2f}"))
        for day in expected.days
    ]


def test_combined_source_total_is_not_recalculated_from_components(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 70, endurance_load=Decimal("40"), strength_load=Decimal("30"))
    assert recalculate(app, athletes[0])[0].total_load == Decimal("70.00")


def test_missing_intermediate_day_is_persisted_as_rest(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 40)
    add_source(session, athletes[0], 2, 60)
    result = recalculate(app, athletes[0], end_date=DAY + timedelta(days=2))
    assert [row.total_load for row in result] == [Decimal("40"), Decimal("0"), Decimal("60")]


def test_versions_history_and_warmup_are_persisted(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    result = recalculate(app, athletes[0], end_date=DAY + timedelta(days=84))
    assert result[0].history_day_number == 1
    assert result[83].is_warmup is True
    assert result[84].is_warmup is False
    assert result[0].training_status_algorithm_version == "0.7f.1"
    assert result[0].training_load_algorithm_version == LOAD_VERSION
    assert result[0].manual_strength_algorithm_version == MANUAL_VERSION


def test_recalculation_is_idempotent_without_rounding_drift(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 1)
    first = recalculate(app, athletes[0], end_date=DAY + timedelta(days=20))
    snapshot = [(row.id, row.fitness, row.fatigue, row.form) for row in first]
    second = recalculate(app, athletes[0], end_date=DAY + timedelta(days=20))
    assert [(row.id, row.fitness, row.fatigue, row.form) for row in second] == snapshot
    assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus)) == 21


def test_historical_change_rebuilds_all_later_values(app_context):
    session, app, athletes = app_context
    source = add_source(session, athletes[0], 0, 10)
    add_source(session, athletes[0], 2, 20)
    before = recalculate(app, athletes[0], end_date=DAY + timedelta(days=2))[-1].fitness
    source.total_load = Decimal("100")
    session.flush()
    after = recalculate(app, athletes[0], end_date=DAY)[0]
    latest = app.get_latest_training_status(athletes[0].id, **{
        key: value for key, value in arguments().items() if key not in ("start_date", "end_date")
    })
    assert after.history_day_number == 1
    assert latest.local_date == DAY + timedelta(days=2)
    assert latest.fitness != before


def test_removed_intermediate_source_becomes_rest_day(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    middle = add_source(session, athletes[0], 1, 20)
    add_source(session, athletes[0], 2, 30)
    recalculate(app, athletes[0], end_date=DAY + timedelta(days=2))
    session.delete(middle)
    session.flush()
    result = recalculate(app, athletes[0], end_date=DAY + timedelta(days=2))
    assert result[1].total_load == 0


def test_removed_loaded_tail_is_deleted_when_history_is_shortened(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    tail = add_source(session, athletes[0], 2, 30)
    recalculate(app, athletes[0], end_date=DAY + timedelta(days=2))
    session.delete(tail)
    session.flush()
    result = recalculate(app, athletes[0], end_date=DAY)
    assert [row.local_date for row in result] == [DAY]
    assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus)) == 1


def test_no_sources_returns_empty_and_removes_only_matching_states(app_context):
    session, app, athletes = app_context
    source = add_source(session, athletes[0], 0, 10)
    recalculate(app, athletes[0])
    other_source = add_source(session, athletes[1], 0, 20)
    recalculate(app, athletes[1])
    session.delete(source)
    session.flush()
    assert recalculate(app, athletes[0]) == ()
    assert app.get_latest_training_status(athletes[0].id, **{
        key: value for key, value in arguments().items() if key not in ("start_date", "end_date")
    }) is None
    assert session.get(AthleteDailyTrainingLoad, other_source.id) is other_source
    assert app.get_latest_training_status(athletes[1].id, **{
        key: value for key, value in arguments().items() if key not in ("start_date", "end_date")
    }) is not None


@pytest.mark.parametrize(
    "field,other",
    [
        ("timezone_name", "UTC"),
        ("source_load_algorithm_version", "0.7b.2"),
        ("manual_strength_algorithm_version", "0.7e.2"),
    ],
)
def test_source_selection_is_isolated_by_configuration(app_context, field, other):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    add_source(session, athletes[0], 0, 90, **{field: other})
    assert recalculate(app, athletes[0])[0].total_load == 10


def test_status_queries_are_isolated_by_status_version(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    current = recalculate(app, athletes[0])[0]
    alternate = AthleteDailyTrainingStatus(
        athlete_profile_id=athletes[0].id,
        local_date=DAY,
        timezone_name="Europe/Madrid",
        training_load_algorithm_version=LOAD_VERSION,
        manual_strength_algorithm_version=MANUAL_VERSION,
        training_status_algorithm_version="legacy",
        total_load=1,
        fitness=1,
        fatigue=1,
        form=0,
        history_day_number=1,
        is_warmup=False,
        calculated_at=NOW,
    )
    session.add(alternate)
    session.flush()
    legacy_args = arguments(training_status_algorithm_version="legacy")
    assert app.list_training_status(athletes[0].id, **legacy_args) == (alternate,)
    assert current.training_status_algorithm_version == "0.7f.1"


def test_list_is_ascending_and_interval_is_inclusive(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    add_source(session, athletes[0], 2, 30)
    recalculate(app, athletes[0], end_date=DAY + timedelta(days=2))
    result = app.list_training_status(
        athletes[0].id,
        **arguments(start_date=DAY + timedelta(days=1), end_date=DAY + timedelta(days=2)),
    )
    assert [row.local_date for row in result] == [DAY + timedelta(days=1), DAY + timedelta(days=2)]


def test_latest_returns_most_recent_or_none(app_context):
    session, app, athletes = app_context
    latest_args = {key: value for key, value in arguments().items() if key not in ("start_date", "end_date")}
    assert app.get_latest_training_status(athletes[0].id, **latest_args) is None
    add_source(session, athletes[0], 0, 10)
    recalculate(app, athletes[0], end_date=DAY + timedelta(days=2))
    assert app.get_latest_training_status(athletes[0].id, **latest_args).local_date == DAY + timedelta(days=2)


def test_unknown_athlete_is_rejected(app_context):
    _, app, _ = app_context
    with pytest.raises(TrainingStatusAthleteNotFoundError):
        app.recalculate_training_status(uuid4(), **arguments())


def test_reversed_and_non_date_ranges_are_rejected(app_context):
    _, app, athletes = app_context
    with pytest.raises(InvalidTrainingStatusApplicationRangeError):
        recalculate(app, athletes[0], start_date=DAY + timedelta(days=1))
    with pytest.raises(InvalidTrainingStatusApplicationRangeError):
        recalculate(app, athletes[0], start_date=True)


@pytest.mark.parametrize("timezone_name", ["", "Unknown/Zone"])
def test_invalid_timezone_is_rejected(app_context, timezone_name):
    _, app, athletes = app_context
    with pytest.raises(InvalidTrainingStatusTimezoneError):
        recalculate(app, athletes[0], timezone_name=timezone_name)


@pytest.mark.parametrize(
    "field",
    [
        "training_load_algorithm_version",
        "manual_strength_algorithm_version",
        "training_status_algorithm_version",
    ],
)
def test_empty_versions_are_rejected(app_context, field):
    _, app, athletes = app_context
    with pytest.raises(InvalidTrainingStatusVersionError):
        recalculate(app, athletes[0], **{field: " "})


@pytest.mark.parametrize("value", [-1, Decimal("NaN"), Decimal("Infinity")])
def test_invalid_source_numeric_values_are_rejected(value):
    with pytest.raises(InvalidTrainingStatusSourceDataError):
        TrainingStatusApplication._source_load(SimpleNamespace(total_load=value))


def test_duplicate_source_date_is_rejected(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    add_source(session, athletes[0], 0, 20, aggregation_algorithm_version="other")
    with pytest.raises(DuplicateTrainingStatusSourceDateError):
        recalculate(app, athletes[0])


def test_service_does_not_modify_source_aggregates(app_context):
    session, app, athletes = app_context
    source = add_source(session, athletes[0], 0, 10)
    snapshot = (source.id, source.total_load, source.endurance_load, source.strength_load, source.calculated_at)
    recalculate(app, athletes[0])
    assert (source.id, source.total_load, source.endurance_load, source.strength_load, source.calculated_at) == snapshot


def test_service_flushes_without_committing(app_context, monkeypatch):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    flush = Mock(wraps=session.flush)
    commit = Mock(side_effect=AssertionError("commit must remain caller-owned"))
    monkeypatch.setattr(session, "flush", flush)
    monkeypatch.setattr(session, "commit", commit)
    recalculate(app, athletes[0])
    assert flush.called
    commit.assert_not_called()


def test_persistence_failure_is_public_and_caller_can_rollback(app_context, monkeypatch):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    original_flush = session.flush

    def fail_flush(*args, **kwargs):
        if session.new:
            raise SQLAlchemyError("synthetic failure")
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", fail_flush)
    with pytest.raises(TrainingStatusPersistenceError):
        recalculate(app, athletes[0])
    session.rollback()
    assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus)) == 0


def test_partial_request_reconstructs_from_first_source_with_historical_number(app_context):
    session, app, athletes = app_context
    add_source(session, athletes[0], 0, 10)
    add_source(session, athletes[0], 4, 20)
    result = recalculate(
        app,
        athletes[0],
        start_date=DAY + timedelta(days=3),
        end_date=DAY + timedelta(days=4),
    )
    assert [row.history_day_number for row in result] == [4, 5]
    assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingStatus)) == 5


def test_disordered_source_query_still_produces_deterministic_result(app_context, monkeypatch):
    session, app, athletes = app_context
    first = add_source(session, athletes[0], 0, 10)
    second = add_source(session, athletes[0], 1, 20)
    monkeypatch.setattr(app, "_source_rows", lambda *args: (second, first))
    first_result = recalculate(app, athletes[0], end_date=DAY + timedelta(days=1))
    snapshot = [(row.local_date, row.fitness, row.fatigue, row.form) for row in first_result]
    second_result = recalculate(app, athletes[0], end_date=DAY + timedelta(days=1))
    assert [(row.local_date, row.fitness, row.fatigue, row.form) for row in second_result] == snapshot
