from __future__ import annotations

import warnings

from sqlalchemy import select
from sqlalchemy.exc import SAWarning
from sqlalchemy.orm import Session, configure_mappers

from app.application.training_load import TrainingLoadApplication
from app.db.models import ActivityTrainingLoad, CompletedActivity
from test_activity_reads import activity_client


def _owned_activity(session: Session) -> CompletedActivity:
    return session.scalar(select(CompletedActivity).where(CompletedActivity.name == "Owned 0"))


def test_invalid_distance_is_persisted_as_unavailable(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activity = _owned_activity(session)
        activity.distance_m = None
        session.commit()
        result = TrainingLoadApplication(session).calculate_for_activity(activity.athlete_id, activity.id)
        session.commit()
        row = session.scalar(select(ActivityTrainingLoad).where(ActivityTrainingLoad.completed_activity_id == activity.id))
        assert result.load is None
        assert (row.load_value, row.coverage, row.quality, row.reason) == (None, "unavailable", "none", "invalid_value")
        assert "distance_meters" in row.warnings[0]


def test_invalid_moving_time_is_persisted_as_unavailable(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activity = _owned_activity(session)
        activity.moving_time_s = None
        session.commit()
        result = TrainingLoadApplication(session).calculate_for_activity(activity.athlete_id, activity.id)
        session.commit()
        row = session.scalar(select(ActivityTrainingLoad).where(ActivityTrainingLoad.completed_activity_id == activity.id))
        assert result.load is None
        assert (row.coverage, row.quality, row.reason) == ("unavailable", "none", "missing_duration")
        assert "moving_time_seconds" in row.warnings[0]


def test_invalid_heart_rate_is_omitted_without_breaking_calculation(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activity = _owned_activity(session)
        activity.average_heart_rate_bpm = 999
        session.commit()
        result = TrainingLoadApplication(session).calculate_for_activity(activity.athlete_id, activity.id)
        assert result.load == 8.06
        assert any("average_heart_rate_bpm" in warning for warning in result.warnings)


def test_valid_activity_preserves_previous_071b1_result(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activity = _owned_activity(session)
        result = TrainingLoadApplication(session).calculate_for_activity(activity.athlete_id, activity.id)
        assert result.load == 8.06
        assert result.method.value == "duration_only"
        assert result.coverage.value == "partial"
        assert result.quality.value == "low"


def test_mapper_configuration_has_no_metrics_relationship_warning():
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=SAWarning, message=".*CompletedActivity.metrics.*")
        configure_mappers()
