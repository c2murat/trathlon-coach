from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies.providers import get_strava_import_manager
from app.db.base import utc_now
from app.integrations.strava.activity_import import (
    ActiveStravaConnectionRequiredError,
    ImportJobNotFoundError,
    StravaImportJobView,
)
from app.main import create_app


class FakeManager:
    def __init__(self, *, start_error=None, status_error=None) -> None:
        self.job_id = uuid4()
        self.start_error = start_error
        self.status_error = status_error
        self.scheduled = []

    def create_or_resume_job(self, user_id):
        del user_id
        if self.start_error:
            raise self.start_error
        return self.view("queued")

    def schedule(self, job_id):
        self.scheduled.append(job_id)

    def job_for_user(self, user_id, job_id):
        del user_id
        if self.status_error or job_id != self.job_id:
            raise self.status_error or ImportJobNotFoundError()
        return self.view("running")

    def view(self, status):
        now = utc_now()
        return StravaImportJobView(
            job_id=self.job_id,
            provider="strava",
            status=status,
            imported_count=12,
            updated_count=2,
            skipped_count=3,
            failed_count=1,
            page=4,
            last_external_activity_id="12345",
            started_at=now - timedelta(minutes=2),
            updated_at=now,
            completed_at=None,
            next_resume_at=None,
            error_category=None,
        )


def client_with(manager):
    app = create_app()
    app.dependency_overrides[get_strava_import_manager] = lambda: manager
    return TestClient(app)


def test_start_returns_202_immediately_and_schedules_background_work():
    manager = FakeManager()
    with client_with(manager) as client:
        response = client.post("/integrations/strava/imports")
    assert response.status_code == 202
    assert response.json() == {"job_id": str(manager.job_id), "status": "queued"}
    assert manager.scheduled == [manager.job_id]
    assert response.headers["cache-control"] == "no-store"


def test_status_response_is_allow_listed_and_secret_free(caplog):
    manager = FakeManager()
    with client_with(manager) as client:
        response = client.get(f"/integrations/strava/imports/{manager.job_id}")
    assert response.status_code == 200
    assert set(response.json()) == {
        "job_id",
        "provider",
        "status",
        "imported_count",
        "updated_count",
        "skipped_count",
        "failed_count",
        "page",
        "last_external_activity_id",
        "started_at",
        "updated_at",
        "completed_at",
        "next_resume_at",
        "error_category",
    }
    rendered = response.text + caplog.text
    assert "access_token" not in rendered
    assert "refresh_token" not in rendered
    assert "secret" not in rendered


def test_start_requires_active_connection_and_status_is_owner_scoped():
    with client_with(
        FakeManager(start_error=ActiveStravaConnectionRequiredError())
    ) as client:
        response = client.post("/integrations/strava/imports")
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "strava_connection_required"}}

    manager = FakeManager(status_error=ImportJobNotFoundError())
    with client_with(manager) as client:
        response = client.get(f"/integrations/strava/imports/{manager.job_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "strava_import_not_found"}}
