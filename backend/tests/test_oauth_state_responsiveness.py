import asyncio
from datetime import timedelta
from threading import Event, Timer
from uuid import UUID

import httpx

from app.api.dependencies.providers import get_oauth_state_store
from app.core.settings import get_settings
from app.main import app
from app.providers.base import OAuthState, OAuthStateStore, utc_now
from tests.test_strava_connect import configured_settings


class BlockingConsumeStateStore(OAuthStateStore):
    """Test double that models SQLite waiting for a write lock."""

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()

    def save(self, state: OAuthState) -> None:
        raise NotImplementedError

    def consume(self, state_value: str, *, user_id: UUID) -> OAuthState:
        self.entered.set()
        if not self.release.wait(timeout=2):
            raise TimeoutError("test state-store wait was not released")
        return OAuthState(
            value=state_value,
            user_id=user_id,
            expires_at=utc_now() + timedelta(minutes=10),
        )


def test_health_remains_responsive_while_async_callback_waits_on_state_store() -> None:
    async def exercise() -> None:
        store = BlockingConsumeStateStore()
        app.dependency_overrides[get_settings] = lambda: configured_settings()
        app.dependency_overrides[get_oauth_state_store] = lambda: store
        transport = httpx.ASGITransport(app=app)
        timer = Timer(1.0, store.release.set)
        timer.start()

        try:
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                loop = asyncio.get_running_loop()
                callback_started = loop.time()
                callback = asyncio.create_task(
                    client.get(
                        "/integrations/strava/callback",
                        params={"state": "test-state", "error": "provider_error"},
                    )
                )
                entered = await asyncio.to_thread(store.entered.wait, 0.5)
                assert entered
                assert loop.time() - callback_started < 0.5

                started = loop.time()
                health = await client.get("/health")
                elapsed = loop.time() - started

                assert health.status_code == 200
                assert elapsed < 0.5
                assert (await callback).status_code == 400
        finally:
            store.release.set()
            timer.cancel()
            app.dependency_overrides.clear()

    asyncio.run(exercise())
