from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AthleteProfile, User, UserAthleteMembership


def normalize_athlete_display_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 200:
        raise ValueError("invalid athlete display name")
    return normalized


class AthleteAccountUnavailableError(Exception):
    pass


class AthleteDefaultConfigurationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class CreatedAthlete:
    athlete: AthleteProfile
    membership: UserAthleteMembership


class AthleteApplication:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_owned_athlete(
        self,
        user_id: UUID,
        *,
        display_name: str,
        timezone: str,
        unit_system: str,
    ) -> CreatedAthlete:
        user = self._session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        if user is None or user.status != "active" or user.deleted_at is not None:
            raise AthleteAccountUnavailableError

        active_memberships = list(
            self._session.scalars(
                select(UserAthleteMembership)
                .join(UserAthleteMembership.athlete_profile)
                .where(
                    UserAthleteMembership.user_id == user_id,
                    UserAthleteMembership.is_active.is_(True),
                )
            ).all()
        )
        if any(item.athlete_profile.deleted_at is not None for item in active_memberships):
            raise AthleteDefaultConfigurationError
        active_defaults = [item for item in active_memberships if item.is_default]
        if active_memberships and len(active_defaults) != 1:
            raise AthleteDefaultConfigurationError

        athlete = AthleteProfile(
            display_name=normalize_athlete_display_name(display_name),
            timezone=timezone,
            unit_system=unit_system,
        )
        membership = UserAthleteMembership(
            user_id=user.id,
            athlete_profile=athlete,
            role="owner",
            is_active=True,
            is_default=not active_memberships,
        )
        self._session.add_all([athlete, membership])
        self._session.flush()
        return CreatedAthlete(athlete=athlete, membership=membership)
