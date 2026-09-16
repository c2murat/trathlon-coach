from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.api.v1.routes import training_status
from app.db.models import AthleteDailyTrainingStatus
from tests.test_training_status_api import api_context, TrackingSession
from tests.test_training_status_interpretation import CUTOFF, observations, long_history

PARAMS = {"start_date":"2026-08-20", "end_date":CUTOFF.isoformat(), "timezone_name":"UTC"}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(training_status, "utc_now", lambda: datetime(2026,9,16,12,tzinfo=timezone.utc))


def seed(factory, athlete_id, rows=None, **kwargs):
    with factory() as db:
        for index, item in enumerate(observations(**kwargs) if rows is None else rows):
            db.add(AthleteDailyTrainingStatus(athlete_profile_id=athlete_id, local_date=item.date,
                timezone_name="UTC", total_load=50, fitness=item.fitness, fatigue=item.fatigue, form=item.form,
                history_day_number=90+index, is_warmup=False, calculated_at=datetime(2026,9,16,tzinfo=timezone.utc),
                training_load_algorithm_version="0.7b.1", manual_strength_algorithm_version="0.7e.1", training_status_algorithm_version="0.7f.1"))
        db.commit()


def test_overview_reuses_data_and_is_readonly_and_scoped(api_context):
    client, factory, active, users, athletes = api_context
    seed(factory, athletes[0], fitness_delta=3, fatigue_delta=12, form=-25)
    seed(factory, athletes[1], fitness_delta=-3, fatigue_delta=-5, form=0)
    statements = []
    def check(connection, cursor, sql, *args):
        assert sql.lstrip().upper().startswith("SELECT")
        statements.append(sql)
    engine = factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", check)
    before = TrackingSession.commits
    try:
        first = client.get("/training-status/overview", params=PARAMS)
        assert first.status_code == 200
        assert len(statements) == 3  # one membership + two existing status reads
        data = first.json()
        assert data["interpretation"]["athlete_id"] == str(athletes[0])
        assert data["interpretation"]["overall_state"] == "HIGH_LOAD"
        assert len(data["series"]) == 8
        assert data["latest"]["form"] == -25
        assert client.get("/training-status/overview", params=PARAMS).json() == data
        assert client.get("/training-status/overview", params=PARAMS,
            headers={"X-TriCoach-Athlete-Id":str(athletes[1])}).status_code == 403
        active["user_id"] = users[1]
        second = client.get("/training-status/overview", params=PARAMS).json()
        assert second["interpretation"]["overall_state"] == "REDUCED_LOAD"
        assert TrackingSession.commits == before
    finally:
        event.remove(engine, "before_cursor_execute", check)


def test_empty_stale_future_and_narrow_chart(api_context):
    client, factory, _, _, athletes = api_context
    assert client.get("/training-status/overview", params=PARAMS).json()["interpretation"]["overall_state"] == "INSUFFICIENT_DATA"
    seed(factory, athletes[0], age=2)
    result = client.get("/training-status/overview", params=PARAMS).json()
    assert "STALE_STATUS" in result["interpretation"]["reason_codes"]
    assert result["latest"]["date"] == (CUTOFF-timedelta(days=2)).isoformat()
    # Earlier cutoff reuses the same history; chart slicing cannot remove trend evidence.
    day = (CUTOFF-timedelta(days=2)).isoformat()
    result = client.get("/training-status/overview", params={**PARAMS,"start_date":day,"end_date":day}).json()
    assert len(result["series"]) == 1
    assert result["interpretation"]["overall_state"] == "BALANCED"
    result = client.get("/training-status/overview", params={**PARAMS,"start_date":"2026-09-01","end_date":"2026-09-13"}).json()
    assert result["latest"]["date"] == "2026-09-13"
    assert all(row["date"] <= "2026-09-13" for row in result["series"])


@pytest.mark.parametrize("changes", [{"end_date":"2026-09-17"},{"end_date":"bad"},{"start_date":"2027-01-01"},
    {"start_date":"2020-01-01"},{"timezone_name":"invalid"}])
def test_invalid_cutoff_range_timezone(api_context, changes):
    assert api_context[0].get("/training-status/overview", params={**PARAMS,**changes}).status_code == 422


def test_get_leaves_planning_fingerprints_unchanged(api_context):
    from tests.test_planning_preview_artifact import artifact
    before = artifact().model_dump_json()
    assert api_context[0].get("/training-status/overview", params=PARAMS).status_code == 200
    assert artifact().model_dump_json() == before


def test_narrow_chart_retrieves_three_week_context_without_extra_queries(api_context):
    client, factory, _, _, athletes = api_context
    seed(factory, athletes[0], rows=long_history())
    statements = []
    engine = factory.kw["bind"]
    def track(connection, cursor, sql, *args):
        assert sql.lstrip().upper().startswith("SELECT")
        statements.append(sql)
    event.listen(engine,"before_cursor_execute",track)
    try:
        response = client.get("/training-status/overview",params={**PARAMS,"start_date":CUTOFF.isoformat()})
        assert response.status_code == 200
        assert len(statements) == 3
        data = response.json()
        assert len(data["series"]) == 1
        assert data["interpretation"]["broader_context"]["fatigue_trend"] == "RISING_FAST"
        assert data["interpretation"]["recent"]["recovery_turn"]
    finally:
        event.remove(engine,"before_cursor_execute",track)
