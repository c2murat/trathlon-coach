from app.api.dependencies.providers import get_strava_http_transport
from app.main import app
from app.providers.base import AsyncHttpTransport, HttpResponse


class MockTokenTransport(AsyncHttpTransport):
    async def post_form(self, url, *, data, timeout, basic_auth=None):
        return HttpResponse(
            status_code=200,
            json_body={
                "access_token": "real-process-access-token",
                "refresh_token": "real-process-refresh-token",
                "expires_at": 1893456000,
                "expires_in": 21600,
                "token_type": "Bearer",
                "scope": "read,activity:read_all",
                "athlete": {
                    "id": 987654321,
                    "firstname": "Process",
                    "lastname": "Test",
                },
            },
        )


app.dependency_overrides[get_strava_http_transport] = MockTokenTransport
