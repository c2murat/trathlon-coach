from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import ActivityTrainingLoad, CompletedActivity
from scripts.backfill_training_load import BackfillOptions, backfill_training_load
from test_activity_reads import activity_client


def _activities(session: Session) -> list[CompletedActivity]:
    return list(session.scalars(select(CompletedActivity).order_by(CompletedActivity.start_at)))


def test_skips_existing_loads_and_is_idempotent(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activities = _activities(session)
        athlete_id = activities[0].athlete_id
        first = activities[0]
        session.add(
            ActivityTrainingLoad(
                completed_activity_id=first.id,
                algorithm_version="0.7b.1",
                method="duration_only",
                unit="load_points",
                coverage="partial",
                quality="low",
                reason="calculated",
                duration_seconds=first.moving_time_s,
                load_value=10,
                source_metrics={},
                warnings=[],
                calculated_at=utc_now(),
            )
        )
        session.commit()

        result = backfill_training_load(
            session, BackfillOptions(athlete_id=athlete_id), reporter=lambda _: None
        )
        repeated = backfill_training_load(
            session, BackfillOptions(athlete_id=athlete_id), reporter=lambda _: None
        )

        assert result.already_existing == 1
        assert result.calculated == 2
        assert repeated.already_existing == 3
        assert repeated.calculated == 0
        assert session.query(ActivityTrainingLoad).count() == 3


def test_continues_after_an_individual_error(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activities = _activities(session)
        athlete_id = activities[0].athlete_id
        failing_id = activities[1].id

        class FailingApplication:
            def __init__(self, wrapped_session: Session):
                from app.application.training_load import TrainingLoadApplication

                self.wrapped = TrainingLoadApplication(wrapped_session)

            def calculate_for_activity(self, athlete, activity, version):
                if activity == failing_id:
                    raise RuntimeError("expected failure")
                return self.wrapped.calculate_for_activity(athlete, activity, version)

        result = backfill_training_load(
            session,
            BackfillOptions(athlete_id=athlete_id),
            reporter=lambda _: None,
            application_factory=FailingApplication,
        )

        assert result.calculated == 2
        assert result.errors == 1
        assert session.query(ActivityTrainingLoad).count() == 2


def test_dry_run_does_not_write(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        athlete_id = _activities(session)[0].athlete_id
        result = backfill_training_load(
            session,
            BackfillOptions(athlete_id=athlete_id, dry_run=True),
            reporter=lambda _: None,
        )
        assert result.total_considered == 3
        assert result.calculated == 0
        assert session.query(ActivityTrainingLoad).count() == 0


def test_applies_inclusive_date_limits(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activities = _activities(session)
        target = activities[1]
        target_date = target.start_at.date()
        result = backfill_training_load(
            session,
            BackfillOptions(
                athlete_id=target.athlete_id,
                start_date=target_date,
                end_date=target_date,
            ),
            reporter=lambda _: None,
        )
        rows = session.scalars(select(ActivityTrainingLoad)).all()
        assert result.total_considered == 1
        assert [row.completed_activity_id for row in rows] == [target.id]


def test_commits_once_per_batch(activity_client, monkeypatch):
    _, engine = activity_client
    commit_count = 0
    with Session(engine) as session:
        athlete_id = _activities(session)[0].athlete_id
        original_commit = session.commit

        def counted_commit():
            nonlocal commit_count
            commit_count += 1
            original_commit()

        monkeypatch.setattr(session, "commit", counted_commit)
        result = backfill_training_load(
            session,
            BackfillOptions(athlete_id=athlete_id, batch_size=2),
            reporter=lambda _: None,
        )
        assert result.calculated == 3
        assert commit_count == 2



def test_invalid_historical_data_counts_as_unavailable_not_error(activity_client):
    _, engine = activity_client
    with Session(engine) as session:
        activities = _activities(session)
        athlete_id = activities[0].athlete_id
        for activity in activities:
            if activity.athlete_id == athlete_id:
                activity.distance_m = None
        session.commit()
        first = backfill_training_load(
            session,
            BackfillOptions(athlete_id=athlete_id),
            reporter=lambda _: None,
        )
        second = backfill_training_load(
            session,
            BackfillOptions(athlete_id=athlete_id),
            reporter=lambda _: None,
        )
        assert first.unavailable == 3
        assert first.errors == 0
        assert second.calculated == 0
        assert second.already_existing == 3
