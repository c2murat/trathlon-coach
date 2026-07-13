from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import (
    AthleteProfile,
    AuditEvent,
    IntegrationAccount,
    OAuthCredential,
)
from app.providers.strava.oauth_types import GrantedScopes, StravaTokenResult


class OAuthOwnershipConflictError(Exception):
    """A local or external athlete is already linked to a different owner."""


class LocalAthleteMissingError(Exception):
    """The authenticated local user has no persisted athlete profile."""


@dataclass(frozen=True, slots=True)
class ConnectionResult:
    status: str
    integration_account_id: UUID


class StravaOAuthPersistenceService:
    """Persist one validated Strava authorization in a single transaction."""

    provider_name = "strava"

    def __init__(self, session: Session) -> None:
        self._session = session

    def athlete_for_user(self, user_id: UUID) -> AthleteProfile:
        athlete = self._session.scalar(
            select(AthleteProfile).where(AthleteProfile.user_id == user_id)
        )
        if athlete is None:
            raise LocalAthleteMissingError
        return athlete

    def persist_connection(
        self,
        *,
        user_id: UUID,
        token_result: StravaTokenResult,
        scopes: GrantedScopes,
    ) -> ConnectionResult:
        now = utc_now()
        try:
            athlete = self.athlete_for_user(user_id)
            external_id = token_result.athlete.external_id

            externally_owned = self._session.scalar(
                select(IntegrationAccount).where(
                    IntegrationAccount.provider == self.provider_name,
                    IntegrationAccount.external_account_id == external_id,
                )
            )
            if externally_owned is not None and externally_owned.athlete_id != athlete.id:
                raise OAuthOwnershipConflictError

            local_accounts = list(
                self._session.scalars(
                    select(IntegrationAccount).where(
                        IntegrationAccount.athlete_id == athlete.id,
                        IntegrationAccount.provider == self.provider_name,
                    )
                )
            )
            different_local_account = next(
                (
                    account
                    for account in local_accounts
                    if account.external_account_id != external_id
                    and account.status != "revoked"
                ),
                None,
            )
            if different_local_account is not None:
                raise OAuthOwnershipConflictError

            account = externally_owned or next(
                (
                    candidate
                    for candidate in local_accounts
                    if candidate.external_account_id == external_id
                ),
                None,
            )
            connection_status = "reconnected" if account is not None else "connected"

            if account is None:
                account = IntegrationAccount(
                    athlete_id=athlete.id,
                    provider=self.provider_name,
                    external_account_id=external_id,
                )
                self._session.add(account)

            account.status = "active"
            account.scopes = list(scopes.values)
            account.display_name = token_result.athlete.display_name
            account.connected_at = now
            account.disconnected_at = None
            account.deleted_at = None
            self._session.flush()

            credential = account.oauth_credential
            if credential is None:
                credential = OAuthCredential(integration_account=account)
                self._session.add(credential)

            credential.access_token = token_result.access_token.get_secret_value()
            credential.refresh_token = token_result.refresh_token.get_secret_value()
            credential.expires_at = token_result.expires_at
            credential.token_type = token_result.token_type
            credential.scopes = list(scopes.values)
            credential.key_version = "plaintext-dev"
            credential.revoked_at = None

            self._session.add(
                self._audit_event(
                    action=f"strava.connection_{connection_status}",
                    outcome="success",
                    user_id=user_id,
                    athlete_id=athlete.id,
                    entity_id=account.id,
                    metadata={
                        "provider": self.provider_name,
                        "local_user_id": str(user_id),
                        "external_athlete_id": external_id,
                        "scopes": list(scopes.values),
                        "outcome": "success",
                    },
                )
            )
            self._session.commit()
            return ConnectionResult(
                status=connection_status, integration_account_id=account.id
            )
        except OAuthOwnershipConflictError:
            self._session.rollback()
            raise
        except IntegrityError as exc:
            self._session.rollback()
            raise OAuthOwnershipConflictError from exc
        except Exception:
            self._session.rollback()
            raise

    def record_audit(
        self,
        *,
        action: str,
        outcome: str,
        user_id: UUID,
        metadata: dict[str, object],
    ) -> None:
        try:
            athlete = self.athlete_for_user(user_id)
            self._session.add(
                self._audit_event(
                    action=action,
                    outcome=outcome,
                    user_id=user_id,
                    athlete_id=athlete.id,
                    metadata=metadata,
                )
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    @staticmethod
    def _audit_event(
        *,
        action: str,
        outcome: str,
        user_id: UUID,
        athlete_id: UUID,
        metadata: dict[str, object],
        entity_id: UUID | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            actor_user_id=user_id,
            athlete_id=athlete_id,
            action=action,
            outcome=outcome,
            request_id=str(uuid4()),
            entity_type="integration_account" if entity_id else None,
            entity_id=entity_id,
            occurred_at=utc_now(),
            event_metadata=metadata,
        )
