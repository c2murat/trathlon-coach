from test_activity_reads import activity_client


def test_get_daily_returns_empty_when_no_aggregates(activity_client):
    client, _ = activity_client

    response = client.get(
        "/training-load/daily",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_weekly_returns_empty_when_no_aggregates(activity_client):
    client, _ = activity_client

    response = client.get(
        "/training-load/weekly",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_daily_rejects_invalid_date_range(activity_client):
    client, _ = activity_client

    response = client.get(
        "/training-load/daily",
        params={
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_aggregation_range"


def test_get_weekly_rejects_invalid_date_range(activity_client):
    client, _ = activity_client

    response = client.get(
        "/training-load/weekly",
        params={
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_aggregation_range"


def test_recalculate_daily_rejects_invalid_date_range(activity_client):
    client, _ = activity_client

    response = client.post(
        "/training-load/daily/recalculate",
        params={
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_aggregation_range"


def test_recalculate_weekly_rejects_invalid_date_range(activity_client):
    client, _ = activity_client

    response = client.post(
        "/training-load/weekly/recalculate",
        params={
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_aggregation_range"


def test_recalculate_all_rejects_invalid_date_range(activity_client):
    client, _ = activity_client

    response = client.post(
        "/training-load/recalculate",
        params={
            "start_date": "2026-12-31",
            "end_date": "2026-01-01",
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_aggregation_range"

def test_recalculate_daily_returns_persisted_aggregates(activity_client):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.base import utc_now
    from app.db.models import CompletedActivity
    from app.db.models.training_load import ActivityTrainingLoad

    client, engine = activity_client

    with Session(engine) as session:
        activities = session.scalars(
            select(CompletedActivity)
            .where(CompletedActivity.name.like("Owned %"))
            .order_by(CompletedActivity.start_at)
        ).all()

        from datetime import datetime, timezone

        fixed_starts = [
            datetime(2026, 7, 19, 10, tzinfo=timezone.utc),
            datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
            datetime(2026, 7, 21, 10, tzinfo=timezone.utc),
        ]
        for activity, fixed_start in zip(activities, fixed_starts):
            activity.start_at = fixed_start

        load_values = [10.0, 20.0, None]

        for activity, load_value in zip(activities, load_values):
            session.add(
                ActivityTrainingLoad(
                    completed_activity_id=activity.id,
                    load_value=load_value,
                    method="duration_fallback",
                    unit="points",
                    coverage=(
                        "available"
                        if load_value is not None
                        else "unavailable"
                    ),
                    quality=(
                        "medium"
                        if load_value is not None
                        else "unavailable"
                    ),
                    reason=(
                        None
                        if load_value is not None
                        else "missing_metrics"
                    ),
                    algorithm_version="0.7b.1",
                    duration_seconds=activity.moving_time_s,
                    effective_intensity=None,
                    reference_value=None,
                    reference_metric=None,
                    source_metrics={},
                    warnings=[],
                    calculated_at=utc_now(),
                )
            )

        session.commit()

        start_date = activities[0].start_at.date().isoformat()
        end_date = activities[-1].start_at.date().isoformat()

    response = client.post(
        "/training-load/daily/recalculate",
        params={
            "start_date": start_date,
            "end_date": end_date,
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert len(body) == 3
    assert [row["local_date"] for row in body] == sorted(
        row["local_date"] for row in body
    )

    assert sum(row["activity_count"] for row in body) == 3
    assert sum(row["loaded_activity_count"] for row in body) == 2
    assert sum(row["null_load_activity_count"] for row in body) == 1
    assert sum(row["total_load"] for row in body) == 30.0

    for row in body:
        assert row["timezone_name"] == "Europe/Madrid"
        assert row["source_load_algorithm_version"] == "0.7b.1"
        assert row["aggregation_algorithm_version"] == "0.7c.1"
        assert row["activity_count"] == 1
        assert len(row["activity_ids"]) == 1

    persisted_response = client.get(
        "/training-load/daily",
        params={
            "start_date": start_date,
            "end_date": end_date,
            "timezone_name": "Europe/Madrid",
        },
    )

    assert persisted_response.status_code == 200
    assert persisted_response.json() == body



def test_recalculate_weekly_returns_persisted_aggregates(activity_client):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.base import utc_now
    from app.db.models import CompletedActivity
    from app.db.models.training_load import ActivityTrainingLoad

    client, engine = activity_client

    with Session(engine) as session:
        activities = session.scalars(
            select(CompletedActivity)
            .where(CompletedActivity.name.like("Owned %"))
            .order_by(CompletedActivity.start_at)
        ).all()

        from datetime import datetime, timezone

        fixed_starts = [
            datetime(2026, 7, 19, 10, tzinfo=timezone.utc),
            datetime(2026, 7, 20, 10, tzinfo=timezone.utc),
            datetime(2026, 7, 21, 10, tzinfo=timezone.utc),
        ]
        for activity, fixed_start in zip(activities, fixed_starts):
            activity.start_at = fixed_start

        load_values = [10.0, 20.0, None]

        for activity, load_value in zip(activities, load_values):
            session.add(
                ActivityTrainingLoad(
                    completed_activity_id=activity.id,
                    load_value=load_value,
                    method="duration_fallback",
                    unit="points",
                    coverage=(
                        "available"
                        if load_value is not None
                        else "unavailable"
                    ),
                    quality=(
                        "medium"
                        if load_value is not None
                        else "unavailable"
                    ),
                    reason=(
                        None
                        if load_value is not None
                        else "missing_metrics"
                    ),
                    algorithm_version="0.7b.1",
                    duration_seconds=activity.moving_time_s,
                    effective_intensity=None,
                    reference_value=None,
                    reference_metric=None,
                    source_metrics={},
                    warnings=[],
                    calculated_at=utc_now(),
                )
            )

        session.commit()

        start_date = activities[0].start_at.date().isoformat()
        end_date = activities[-1].start_at.date().isoformat()

    response = client.post(
        "/training-load/weekly/recalculate",
        params={
            "start_date": start_date,
            "end_date": end_date,
            "timezone_name": "Europe/Madrid",
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert len(body) == 2

    assert sum(row["activity_count"] for row in body) == 3
    assert sum(row["loaded_activity_count"] for row in body) == 2
    assert sum(row["null_load_activity_count"] for row in body) == 1
    assert sum(row["total_load"] for row in body) == 30.0

    for row in body:
        assert row["timezone_name"] == "Europe/Madrid"
        assert row["source_load_algorithm_version"] == "0.7b.1"
        assert row["aggregation_algorithm_version"] == "0.7c.1"

    persisted_response = client.get(
        "/training-load/weekly",
        params={
            "start_date": start_date,
            "end_date": end_date,
            "timezone_name": "Europe/Madrid",
        },
    )

    assert persisted_response.status_code == 200
    assert persisted_response.json() == body

