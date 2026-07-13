from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.routes.strava_integrations import router as strava_integrations_router
from app.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.service_name, version="0.1.0")
    application.include_router(health_router)
    application.include_router(strava_integrations_router)
    return application


app = create_app()