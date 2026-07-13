from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import AthleteProfile, AuditEvent, IntegrationAccount, OAuthCredential


REQUIRED_SCOPES = frozenset({"read", "activity:read_all"})


@dataclass(frozen=True, slots=True)
class StravaConnectionStatus:
    provider: str
    connection_status: str
    connected: bool
    external_athlete_id: str | None
    granted_scopes: tuple[str, ...]
    connected_at: datetime | None
    updated_at: datetime | None
    token_expires_at: datetime | None
    requires_reconnect: bool
    last_sync_at: datetime | None
    message: str


@dataclass(frozen=True, slots=True)
class DisconnectTarget:
    account_id: UUID
    athlete_id: UUID
    user_id: UUID
    external_athlete_id: str
    access_token: SecretStr | None
    already_disconnected: bool

    def __repr__(self) -> str:
        return (
            f"<DisconnectTarget account_id={self.account_id!r} "
            "access_token=<redacted>>"
        )


class StravaConnectionService:
    """Read safe connection state and apply transactional local disconnects."""

    provider_name = "strava"

    def __init__(self, session: Session) -> None:
        self._session = session

    def status_for_user(self, user_id: UUID) -> StravaConnectionStatus:
        account = self._account_for_user(user_id)
        if account is None:
            return StravaConnectionStatus(
                provider=self.provider_name,
                connection_status="not_connected",
                connected=False,
                external_athlete_id=None,
                granted_scopes=(),
                connected_at=None,
                updated_at=None,
                token_expires_at=None,
                requires_reconnect=False,
                last_sync_at=None,
                message="Strava is not connected.",
            )

        credential = account.oauth_credential
        scopes = tuple(sorted(set(account.scopes or ())))
        has_required_scopes = REQUIRED_SCOPES.issubset(scopes) and not any(
            "write" in scope for scope in scopes
        )

        if account.status in {"disconnected", "revoked"}:
            connection_status = account.status
            connected = False
            requires_reconnect = True
        elif account.status in {"error", "refresh_required"}:
            connection_status = "temporarily_unavailable"
            connected = False
            requires_reconnect = account.status == "refresh_required"
        elif not has_required_scopes:
            connection_status = "scope_insufficient"
            connected = False
            requires_reconnect = True
        elif credential is None:
            connection_status = "revoked"
            connected = False
            requires_reconnect = True
        else:
            connection_status = "connected"
            connected = True
            requires_reconnect = False

        messages = {
            "connected": "Strava is connected.",
            "scope_insufficient": "Reconnect Strava to grant the required read access.",
            "revoked": "Strava authorization has been revoked.",
            "disconnected": "Strava is disconnected.",
            "temporarily_unavailable": "Strava is temporarily unavailable.",
        }
        return StravaConnectionStatus(
            provider=self.provider_name,
            connection_status=connection_status,
            connected=connected,
            external_athlete_id=account.external_account_id,
            granted_scopes=scopes,
            connected_at=account.connected_at,
            updated_at=account.updated_at,
            token_expires_at=credential.expires_at if credential else None,
            requires_reconnect=requires_reconnect,
            last_sync_at=account.last_synced_at,
            message=messages[connection_status],
        )

    def begin_disconnect(self, user_id: UUID) -> DisconnectTarget | None:
        account = self._account_for_user(user_id)
        if account is None:
            return None
        credential = account.oauth_credential
        target = DisconnectTarget(
            account_id=account.id,
            athlete_id=account.athlete_id,
            user_id=user_id,
            external_athlete_id=account.external_account_id,
            access_token=SecretStr(credential.access_token) if credential else None,
            already_disconnected=(
                account.status in {"disconnected", "revoked"} and credential is None
            ),
        )
        self._commit_audit(
            target,
            action="strava.disconnect_requested",
            outcome="accepted",
        )
        return target

    def record_revocation_failure(self, target: DisconnectTarget, category: str) -> None:
        action = (
            "strava.revocation_temporarily_failed"
            if category == "temporary"
            else "strava.revocation_authentication_failed"
        )
        self._commit_audit(
            target,
            action=action,
            outcome="failure",
            error_category=category,
        )

    def complete_disconnect(
        self, target: DisconnectTarget, *, remote_revocation_performed: bool
    ) -> None:
        try:
            account = self._session.scalar(
                select(IntegrationAccount).where(IntegrationAccount.id == target.account_id)
            )
            if account is None or account.athlete_id != target.athlete_id:
                raise RuntimeError("Owned integration account disappeared")

            credential = account.oauth_credential
            if credential is not None:
                self._session.delete(credential)
            account.status = "disconnected"
            account.disconnected_at = utc_now()

            if remote_revocation_performed:
                self._session.add(
                    self._audit(target, "strava.remote_revocation_succeeded", "success")
                )
            self._session.add(
                self._audit(target, "strava.disconnect_completed", "success")
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def _account_for_user(self, user_id: UUID) -> IntegrationAccount | None:
        return self._session.scalar(
            select(IntegrationAccount)
            .join(AthleteProfile, IntegrationAccount.athlete_id == AthleteProfile.id)
            .where(
                AthleteProfile.user_id == user_id,
                IntegrationAccount.provider == self.provider_name,
                IntegrationAccount.deleted_at.is_(None),
            )
            .order_by(IntegrationAccount.updated_at.desc())
        )

    def _commit_audit(
        self,
        target: DisconnectTarget,
        *,
        action: str,
        outcome: str,
        error_category: str | None = None,
    ) -> None:
        try:
            self._session.add(
                self._audit(target, action, outcome, error_category=error_category)
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    @staticmethod
    def _audit(
        target: DisconnectTarget,
        action: str,
        outcome: str,
        *,
        error_category: str | None = None,
    ) -> AuditEvent:
        metadata: dict[str, object] = {
            "provider": "strava",
            "local_user_id": str(target.user_id),
            "external_athlete_id": target.external_athlete_id,
            "outcome": outcome,
        }
        if error_category is not None:
            metadata["error_category"] = error_category
        return AuditEvent(
            actor_user_id=target.user_id,
            athlete_id=target.athlete_id,
            action=action,
            outcome=outcome,
            request_id=str(uuid4()),
            entity_type="integration_account",
            entity_id=target.account_id,
            occurred_at=utc_now(),
            event_metadata=metadata,
        )
