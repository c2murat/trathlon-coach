from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler

from app.api.health import router as health_router
from app.api.v1.routes.strava_integrations import router as strava_integrations_router
from app.api.v1.routes.strava_imports import router as strava_imports_router
from app.core.settings import get_settings
from app.providers.base import SQLiteOAuthStateStore


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.service_name, version="0.1.0")
    if settings.environment not in {"development", "test"}:
        raise RuntimeError(
            "A shared production OAuth state store must be configured"
        )
    default_state_path = (
        Path(__file__).resolve().parents[1]
        / ".oauth-state"
        / "oauth_state.sqlite3"
    )
    application.state.instance_id = str(uuid4())
    state_store = SQLiteOAuthStateStore(
        settings.oauth_state_sqlite_path or default_state_path,
        diagnostics_enabled=settings.oauth_state_diagnostics,
        application_instance_id=application.state.instance_id,
    )
    application.state.oauth_state_store = state_store

    @application.exception_handler(HTTPException)
    async def safe_http_exception_handler(
        request: Request, exc: HTTPException
    ):
        if request.url.path == "/integrations/strava/callback":
            detail = exc.detail
            public_code = (
                detail.get("code")
                if isinstance(detail, dict) and isinstance(detail.get("code"), str)
                else f"http_{exc.status_code}"
            )
            active_store = getattr(request.app.state, "oauth_state_store", None)
            if isinstance(active_store, SQLiteOAuthStateStore):
                active_store.log_public_error(
                    state_value=request.query_params.get("state"),
                    public_error_code=public_code,
                )
        return await http_exception_handler(request, exc)

    application.include_router(health_router)
    application.include_router(strava_integrations_router)
    application.include_router(strava_imports_router)
    return application


app = create_app()
