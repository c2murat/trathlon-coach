from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IntegrationAccount, SyncJob, UserAthleteMembership


class StravaAccountConfigurationError(Exception):
    """An athlete has more than one active Strava account."""


def active_strava_account(
    session: Session,
    *,
    athlete_id: UUID,
) -> IntegrationAccount | None:
    accounts = list(
        session.scalars(
            select(IntegrationAccount)
            .where(
                IntegrationAccount.athlete_id == athlete_id,
                IntegrationAccount.provider == "strava",
                IntegrationAccount.status == "active",
                IntegrationAccount.deleted_at.is_(None),
            )
            .order_by(IntegrationAccount.id)
        ).all()
    )
    if len(accounts) > 1:
        raise StravaAccountConfigurationError
    return accounts[0] if accounts else None


def strava_account_for_status(
    session: Session, *, athlete_id: UUID
) -> IntegrationAccount | None:
    accounts = list(
        session.scalars(
            select(IntegrationAccount)
            .where(
                IntegrationAccount.athlete_id == athlete_id,
                IntegrationAccount.provider == "strava",
                IntegrationAccount.deleted_at.is_(None),
            )
            .order_by(IntegrationAccount.updated_at.desc(), IntegrationAccount.id)
        ).all()
    )
    active = [account for account in accounts if account.status == "active"]
    if len(active) > 1:
        raise StravaAccountConfigurationError
    if active:
        return active[0]
    if len(accounts) > 1:
        raise StravaAccountConfigurationError
    return accounts[0] if accounts else None


def compatible_athlete_id(
    session: Session, *, user_id: UUID, athlete_id: UUID | None
) -> UUID:
    """Support the legacy single-membership service API without using ownership."""
    if athlete_id is not None:
        return athlete_id
    memberships = list(
        session.scalars(
            select(UserAthleteMembership)
            .where(
                UserAthleteMembership.user_id == user_id,
                UserAthleteMembership.is_active.is_(True),
            )
            .order_by(
                UserAthleteMembership.is_default.desc(),
                UserAthleteMembership.created_at,
            )
        ).all()
    )
    if not memberships:
        return UUID(int=0)
    if len(memberships) != 1 and not (
        memberships and memberships[0].is_default
    ):
        raise StravaAccountConfigurationError
    return memberships[0].athlete_profile_id


def scoped_strava_job(
    session: Session, *, job_id: UUID, athlete_id: UUID | None = None
) -> SyncJob | None:
    statement = (
        select(SyncJob)
        .join(IntegrationAccount, SyncJob.integration_account_id == IntegrationAccount.id)
        .where(
            SyncJob.id == job_id,
            IntegrationAccount.provider == "strava",
            IntegrationAccount.athlete_id == SyncJob.athlete_id,
            IntegrationAccount.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if athlete_id is not None:
        statement = statement.where(SyncJob.athlete_id == athlete_id)
    return session.scalar(statement)
