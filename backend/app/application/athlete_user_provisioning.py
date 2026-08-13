from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AthleteProfile, User, UserAthleteMembership
from app.security.identity import normalize_email
from app.security.passwords import hash_password


class AthleteUserProvisioningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AthleteUserProvisioningPreview:
    athlete_id: UUID
    athlete_display_name: str
    normalized_email: str
    display_name: str
    timezone: str


def validate_athlete_user_provisioning(session: Session, *, athlete_id: UUID, email: str, display_name: str, timezone: str) -> AthleteUserProvisioningPreview:
    normalized = normalize_email(email)
    clean_name = " ".join(display_name.split())
    clean_timezone = timezone.strip()
    if len(normalized) < 3 or len(normalized) > 320:
        raise AthleteUserProvisioningError("invalid_email")
    if not clean_name or len(clean_name) > 200:
        raise AthleteUserProvisioningError("invalid_display_name")
    if not clean_timezone or len(clean_timezone) > 64:
        raise AthleteUserProvisioningError("invalid_timezone")
    try:
        ZoneInfo(clean_timezone)
    except ZoneInfoNotFoundError as error:
        raise AthleteUserProvisioningError("invalid_timezone") from error
    athlete = session.get(AthleteProfile, athlete_id)
    if athlete is None:
        raise AthleteUserProvisioningError("athlete_not_found")
    if athlete.deleted_at is not None:
        raise AthleteUserProvisioningError("athlete_deleted")
    if session.scalar(select(User.id).where(User.normalized_email == normalized)):
        raise AthleteUserProvisioningError("user_email_already_exists")
    if session.scalar(select(UserAthleteMembership.id).where(UserAthleteMembership.athlete_profile_id == athlete_id, UserAthleteMembership.role == "athlete", UserAthleteMembership.is_active.is_(True))):
        raise AthleteUserProvisioningError("active_athlete_membership_already_exists")
    return AthleteUserProvisioningPreview(athlete.id, athlete.display_name, normalized, clean_name, clean_timezone)


def provision_athlete_user(session: Session, *, athlete_id: UUID, email: str, display_name: str, timezone: str, password: str) -> tuple[User, UserAthleteMembership]:
    preview = validate_athlete_user_provisioning(session, athlete_id=athlete_id, email=email, display_name=display_name, timezone=timezone)
    user = User(email=preview.normalized_email, normalized_email=preview.normalized_email, auth_subject=f"provisioned-athlete-{uuid4()}", password_hash=hash_password(password), status="active", timezone=preview.timezone, display_name=preview.display_name)
    session.add(user)
    session.flush()
    membership = UserAthleteMembership(user_id=user.id, athlete_profile_id=preview.athlete_id, role="athlete", is_active=True, is_default=True)
    session.add(membership)
    session.flush()
    return user, membership
