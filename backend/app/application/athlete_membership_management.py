from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AthleteProfile, User, UserAthleteMembership
from app.db.models.membership import ATHLETE_MEMBERSHIP_ROLES


class AthleteMembershipRoleChangeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AthleteMembershipRoleChange:
    user_id: UUID
    athlete_id: UUID
    athlete_display_name: str
    membership_id: UUID
    current_role: str
    requested_role: str
    is_active: bool
    is_default: bool
    controller_after_transition: bool

    @property
    def changed(self) -> bool:
        return self.current_role != self.requested_role


def validate_athlete_membership_role_change(session: Session, *, user_id: UUID, athlete_id: UUID, new_role: str, lock: bool = False) -> AthleteMembershipRoleChange:
    if new_role not in ATHLETE_MEMBERSHIP_ROLES:
        raise AthleteMembershipRoleChangeError("invalid_membership_role")
    if session.get(User, user_id) is None:
        raise AthleteMembershipRoleChangeError("user_not_found")
    athlete = session.get(AthleteProfile, athlete_id)
    if athlete is None:
        raise AthleteMembershipRoleChangeError("athlete_not_found")
    if athlete.deleted_at is not None:
        raise AthleteMembershipRoleChangeError("athlete_deleted")
    statement = select(UserAthleteMembership).where(
        UserAthleteMembership.user_id == user_id,
        UserAthleteMembership.athlete_profile_id == athlete_id,
    )
    if lock:
        statement = statement.with_for_update()
    membership = session.scalar(statement)
    if membership is None:
        raise AthleteMembershipRoleChangeError("membership_not_found")
    if not membership.is_active:
        raise AthleteMembershipRoleChangeError("membership_inactive")
    if new_role == "athlete" and membership.role != "athlete":
        existing_self = session.scalar(
            select(UserAthleteMembership.id).where(
                UserAthleteMembership.athlete_profile_id == athlete_id,
                UserAthleteMembership.role == "athlete",
                UserAthleteMembership.is_active.is_(True),
                UserAthleteMembership.id != membership.id,
            )
        )
        if existing_self is not None:
            raise AthleteMembershipRoleChangeError("athlete_self_membership_already_exists")
    other_controller = session.scalar(
        select(UserAthleteMembership.id).where(
            UserAthleteMembership.athlete_profile_id == athlete_id,
            UserAthleteMembership.is_active.is_(True),
            UserAthleteMembership.role.in_(("owner", "athlete")),
            UserAthleteMembership.id != membership.id,
        )
    )
    controller_after = new_role in {"owner", "athlete"} or other_controller is not None
    if not controller_after:
        raise AthleteMembershipRoleChangeError("athlete_controller_required")
    return AthleteMembershipRoleChange(
        user_id=user_id,
        athlete_id=athlete_id,
        athlete_display_name=athlete.display_name,
        membership_id=membership.id,
        current_role=membership.role,
        requested_role=new_role,
        is_active=membership.is_active,
        is_default=membership.is_default,
        controller_after_transition=controller_after,
    )


def set_athlete_membership_role(session: Session, *, user_id: UUID, athlete_id: UUID, new_role: str) -> AthleteMembershipRoleChange:
    change = validate_athlete_membership_role_change(session, user_id=user_id, athlete_id=athlete_id, new_role=new_role, lock=True)
    if not change.changed:
        return change
    membership = session.get(UserAthleteMembership, change.membership_id)
    if membership is None:
        raise AthleteMembershipRoleChangeError("membership_not_found")
    membership.role = new_role
    session.flush()
    return change
@dataclass(frozen=True, slots=True)
class AthleteMembershipRevocation:
    user_id: UUID
    athlete_id: UUID
    athlete_display_name: str
    membership_id: UUID
    role: str
    was_active: bool
    was_default: bool
    controller_after_transition: bool

    @property
    def changed(self) -> bool:
        return self.was_active


def validate_athlete_membership_revocation(
    session: Session, *, user_id: UUID, athlete_id: UUID, lock: bool = False
) -> AthleteMembershipRevocation:
    if session.get(User, user_id) is None:
        raise AthleteMembershipRoleChangeError("user_not_found")
    athlete = session.get(AthleteProfile, athlete_id)
    if athlete is None:
        raise AthleteMembershipRoleChangeError("athlete_not_found")
    if athlete.deleted_at is not None:
        raise AthleteMembershipRoleChangeError("athlete_deleted")
    statement = select(UserAthleteMembership).where(
        UserAthleteMembership.user_id == user_id,
        UserAthleteMembership.athlete_profile_id == athlete_id,
    )
    if lock:
        statement = statement.with_for_update()
    membership = session.scalar(statement)
    if membership is None:
        raise AthleteMembershipRoleChangeError("membership_not_found")
    other_controller = session.scalar(
        select(UserAthleteMembership.id).where(
            UserAthleteMembership.athlete_profile_id == athlete_id,
            UserAthleteMembership.is_active.is_(True),
            UserAthleteMembership.role.in_(("owner", "athlete")),
            UserAthleteMembership.id != membership.id,
        )
    )
    controller_after = other_controller is not None
    if membership.is_active and not controller_after:
        raise AthleteMembershipRoleChangeError("athlete_controller_required")
    return AthleteMembershipRevocation(
        user_id=user_id,
        athlete_id=athlete_id,
        athlete_display_name=athlete.display_name,
        membership_id=membership.id,
        role=membership.role,
        was_active=membership.is_active,
        was_default=membership.is_default,
        controller_after_transition=controller_after,
    )


def revoke_athlete_membership(
    session: Session, *, user_id: UUID, athlete_id: UUID
) -> AthleteMembershipRevocation:
    change = validate_athlete_membership_revocation(
        session, user_id=user_id, athlete_id=athlete_id, lock=True
    )
    if not change.changed:
        return change
    membership = session.get(UserAthleteMembership, change.membership_id)
    if membership is None:
        raise AthleteMembershipRoleChangeError("membership_not_found")
    membership.is_active = False
    membership.is_default = False
    session.flush()
    return change
