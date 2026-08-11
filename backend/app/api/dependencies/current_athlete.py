from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.db.models import AthleteProfile, UserAthleteMembership
from app.db.session import get_db_session


@dataclass(frozen=True, slots=True)
class CurrentAthleteContext:
    user_id: UUID
    athlete_id: UUID
    role: str
    athlete_profile: AthleteProfile
    membership: UserAthleteMembership


def resolve_current_athlete(
    session: Session,
    current_user: AuthenticatedUser,
    requested_athlete_id: str | None = None,
) -> CurrentAthleteContext:
    selected_id: UUID | None = None
    if requested_athlete_id is not None:
        try:
            selected_id = UUID(requested_athlete_id)
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_athlete_id"},
            ) from None

    statement = (
        select(UserAthleteMembership)
        .options(joinedload(UserAthleteMembership.athlete_profile))
        .where(
            UserAthleteMembership.user_id == current_user.id,
            UserAthleteMembership.is_active.is_(True),
            UserAthleteMembership.athlete_profile.has(AthleteProfile.deleted_at.is_(None)),
        )
        .order_by(
            UserAthleteMembership.is_default.desc(),
            UserAthleteMembership.created_at,
            UserAthleteMembership.id,
        )
    )

    if selected_id is not None:
        membership = session.scalar(
            statement.where(UserAthleteMembership.athlete_profile_id == selected_id)
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "athlete_not_authorized"},
            )
        return _context(current_user, membership)

    memberships = list(session.scalars(statement).all())
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "athlete_profile_not_found"},
        )
    if len(memberships) == 1:
        return _context(current_user, memberships[0])

    defaults = [membership for membership in memberships if membership.is_default]
    if len(defaults) == 1:
        return _context(current_user, defaults[0])
    if len(defaults) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "athlete_default_configuration_invalid"},
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "athlete_selection_required"},
    )


def get_current_athlete(
    current_user: AuthenticatedUser = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    requested_athlete_id: str | None = Header(
        default=None,
        alias="X-TriCoach-Athlete-Id",
    ),
) -> CurrentAthleteContext:
    return resolve_current_athlete(session, current_user, requested_athlete_id)


def _context(
    current_user: AuthenticatedUser,
    membership: UserAthleteMembership,
) -> CurrentAthleteContext:
    return CurrentAthleteContext(
        user_id=current_user.id,
        athlete_id=membership.athlete_profile_id,
        role=membership.role,
        athlete_profile=membership.athlete_profile,
        membership=membership,
    )
