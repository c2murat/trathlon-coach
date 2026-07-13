from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import IntegrationAccount, OAuthCredential
from app.providers.base import AuthenticationError
from app.providers.strava import (
    StravaOAuthClient,
    StravaRefreshCredential,
    StravaRefreshResult,
)


SessionFactory = Callable[[], Session]


class StravaTokenService:
    """Return a usable token and atomically rotate expired credentials."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        oauth_client: StravaOAuthClient,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session_factory = session_factory
        self._oauth_client = oauth_client
        self._clock = clock
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def access_token(self, integration_account_id: UUID) -> SecretStr:
        lock = self._locks.setdefault(integration_account_id, asyncio.Lock())
        async with lock:
            with self._session_factory() as session:
                credential = session.scalar(
                    select(OAuthCredential)
                    .where(
                        OAuthCredential.integration_account_id
                        == integration_account_id
                    )
                    .with_for_update()
                )
                account = session.get(IntegrationAccount, integration_account_id)
                if (
                    account is None
                    or account.status != "active"
                    or credential is None
                    or credential.revoked_at is not None
                ):
                    raise AuthenticationError("Strava reconnect is required")

                now = self._clock()
                if credential.expires_at > now + timedelta(seconds=30):
                    return SecretStr(credential.access_token)
                if not credential.refresh_token:
                    account.status = "refresh_required"
                    session.commit()
                    raise AuthenticationError("Strava reconnect is required")

                refresh_credential = StravaRefreshCredential(
                    refresh_token=SecretStr(credential.refresh_token)
                )
                try:
                    result = await self._oauth_client.refresh_authorization(
                        refresh_credential
                    )
                except AuthenticationError:
                    account.status = "refresh_required"
                    session.commit()
                    raise
                except Exception:
                    session.rollback()
                    raise
                if not isinstance(result, StravaRefreshResult):
                    session.rollback()
                    raise AuthenticationError("Strava refresh result is invalid")

                credential.access_token = result.access_token.get_secret_value()
                credential.refresh_token = result.refresh_token.get_secret_value()
                credential.expires_at = result.expires_at
                credential.token_type = result.token_type
                credential.last_refreshed_at = now
                account.status = "active"
                session.commit()
                return SecretStr(result.access_token.get_secret_value())
