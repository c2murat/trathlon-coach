from __future__ import annotations

import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.core.settings import get_settings
from app.db.models import AthleteProfile, User, UserAthleteMembership
from app.db.session import SessionLocal


DEVELOPMENT_EMAIL = "development-athlete@example.invalid"
DEVELOPMENT_AUTH_SUBJECT = "development-local-mvp-user"
DEVELOPMENT_TIMEZONE = "Europe/Madrid"


@dataclass(frozen=True, slots=True)
class DevelopmentSeedResult:
    """Describe which development-only records were created."""

    user_created: bool
    athlete_profile_created: bool
    membership_created: bool


def seed_development_user(session: Session) -> DevelopmentSeedResult:
    """Ensure the fixed local MVP user and athlete profile exist atomically."""

    user_created = False
    athlete_profile_created = False
    membership_created = False

    with session.begin():
        user = session.get(User, LOCAL_MVP_USER_ID)
        if user is None:
            user = User(
                id=LOCAL_MVP_USER_ID,
                email=DEVELOPMENT_EMAIL,
                normalized_email=DEVELOPMENT_EMAIL,
                auth_subject=DEVELOPMENT_AUTH_SUBJECT,
                timezone=DEVELOPMENT_TIMEZONE,
            )
            session.add(user)
            user_created = True

        membership = session.scalar(
            select(UserAthleteMembership)
            .where(
                UserAthleteMembership.user_id == LOCAL_MVP_USER_ID,
                UserAthleteMembership.role == "owner",
                UserAthleteMembership.is_active.is_(True),
            )
            .order_by(
                UserAthleteMembership.is_default.desc(),
                UserAthleteMembership.created_at,
                UserAthleteMembership.id,
            )
        )
        athlete_profile = membership.athlete_profile if membership is not None else None
        if athlete_profile is None:
            athlete_profile = AthleteProfile(
                display_name="Atleta de desarrollo",
                timezone=DEVELOPMENT_TIMEZONE,
                unit_system="metric",
            )
            session.add(athlete_profile)
            athlete_profile_created = True

        session.flush()
        if membership is None:
            session.add(
                UserAthleteMembership(
                    user_id=LOCAL_MVP_USER_ID,
                    athlete_profile_id=athlete_profile.id,
                    role="owner",
                    is_active=True,
                    is_default=True,
                )
            )
            membership_created = True
        else:
            membership.role = "owner"
            membership.is_active = True
            membership.is_default = True

    return DevelopmentSeedResult(
        user_created=user_created,
        athlete_profile_created=athlete_profile_created,
        membership_created=membership_created,
    )


def main() -> int:
    """Run the idempotent development seed against the configured database."""

    if get_settings().environment not in {"development", "test"}:
        print(
            "Development user seed refused outside development or test.",
            file=sys.stderr,
        )
        return 2

    try:
        with SessionLocal() as session:
            result = seed_development_user(session)
    except Exception:
        print(
            "Development user seed failed; no seed transaction was committed.",
            file=sys.stderr,
        )
        return 1

    if result.user_created or result.athlete_profile_created or result.membership_created:
        print(
            "Development user seed completed "
            f"(user_created={result.user_created}, "
            f"athlete_profile_created={result.athlete_profile_created}, "
            f"membership_created={result.membership_created})."
        )
    else:
        print("Development user, athlete profile, and membership already exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
