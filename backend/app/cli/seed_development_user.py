from __future__ import annotations

import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import LOCAL_MVP_USER_ID
from app.core.settings import get_settings
from app.db.models import AthleteProfile, User
from app.db.session import SessionLocal


DEVELOPMENT_EMAIL = "development-athlete@example.invalid"
DEVELOPMENT_AUTH_SUBJECT = "development-local-mvp-user"
DEVELOPMENT_TIMEZONE = "Europe/Madrid"


@dataclass(frozen=True, slots=True)
class DevelopmentSeedResult:
    """Describe which development-only records were created."""

    user_created: bool
    athlete_profile_created: bool


def seed_development_user(session: Session) -> DevelopmentSeedResult:
    """Ensure the fixed local MVP user and athlete profile exist atomically."""

    user_created = False
    athlete_profile_created = False

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

        athlete_profile = session.scalar(
            select(AthleteProfile).where(
                AthleteProfile.user_id == LOCAL_MVP_USER_ID
            )
        )
        if athlete_profile is None:
            session.add(
                AthleteProfile(
                    user_id=LOCAL_MVP_USER_ID,
                    timezone=DEVELOPMENT_TIMEZONE,
                    unit_system="metric",
                )
            )
            athlete_profile_created = True

    return DevelopmentSeedResult(
        user_created=user_created,
        athlete_profile_created=athlete_profile_created,
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

    if result.user_created or result.athlete_profile_created:
        print(
            "Development user seed completed "
            f"(user_created={result.user_created}, "
            f"athlete_profile_created={result.athlete_profile_created})."
        )
    else:
        print("Development user and athlete profile already exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
