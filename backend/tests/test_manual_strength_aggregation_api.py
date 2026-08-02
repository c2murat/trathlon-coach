from datetime import date
from sqlalchemy import func, select

from app.db.models import AthleteDailyTrainingLoad, AthleteWeeklyTrainingLoad
from app.api.v1.routes.training_load_aggregation import router as aggregation_router
from test_manual_strength_api import api_context, create


def test_manual_post_patch_delete_synchronizes_aggregates(api_context):
    client, factory, _, _, _ = api_context
    created = create(client, duration_minutes=60, perceived_exertion=None).json()
    with factory() as session:
        daily = session.scalar(select(AthleteDailyTrainingLoad))
        weekly = session.scalar(select(AthleteWeeklyTrainingLoad))
        assert (float(daily.endurance_load), float(daily.strength_load), float(daily.total_load), daily.strength_session_count) == (0, 50, 50, 1)
        assert float(weekly.total_load) == 50
    client.patch(f"/manual-strength-sessions/{created['id']}", json={"duration_minutes": 30})
    with factory() as session:
        assert float(session.scalar(select(AthleteDailyTrainingLoad)).strength_load) == 25
    client.delete(f"/manual-strength-sessions/{created['id']}")
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AthleteDailyTrainingLoad)) == 0
        assert session.scalar(select(func.count()).select_from(AthleteWeeklyTrainingLoad)) == 0


def test_date_move_removes_old_day_and_adds_new_day(api_context):
    client, factory, _, _, _ = api_context
    created = create(client, started_at="2026-08-02T10:00:00+02:00").json()
    client.patch(f"/manual-strength-sessions/{created['id']}", json={"started_at": "2026-08-03T10:00:00+02:00"})
    with factory() as session:
        rows = session.scalars(select(AthleteDailyTrainingLoad)).all()
        assert [row.local_date for row in rows] == [date(2026, 8, 3)]


def test_aggregate_api_exposes_additive_fields(api_context):
    client, _, _, _, _ = api_context
    client.app.include_router(aggregation_router)
    create(client, duration_minutes=60, perceived_exertion=None)
    response = client.get("/training-load/daily", params={"start_date": "2026-08-02", "end_date": "2026-08-02", "timezone_name": "Europe/Madrid"})
    assert response.status_code == 200
    body = response.json()[0]
    assert body["total_load"] == body["endurance_load"] + body["strength_load"] == 50
    assert body["strength_session_count"] == 1
    assert body["manual_strength_algorithm_version"] == "0.7e.1"
    assert "activity_count" in body
