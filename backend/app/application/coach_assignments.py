from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import AthleteProfile, User, UserAthleteMembership


class CoachAssignmentError(ValueError):
    pass


@dataclass(frozen=True)
class CoachAssignment:
    membership: UserAthleteMembership
    coach: User
    athlete: AthleteProfile


class CoachAssignmentApplication:
    def __init__(self, session: Session) -> None:
        self.session = session

    def coach_candidates(self) -> list[User]:
        return list(self.session.scalars(select(User).where(User.account_plan == "coach", User.status == "active", User.deleted_at.is_(None)).order_by(User.display_name, User.email)).all())

    def athlete_candidates(self) -> list[AthleteProfile]:
        return list(self.session.scalars(select(AthleteProfile).where(AthleteProfile.deleted_at.is_(None)).order_by(AthleteProfile.display_name, AthleteProfile.id)).all())

    def active_assignments(self) -> list[CoachAssignment]:
        rows = self.session.scalars(select(UserAthleteMembership).options(joinedload(UserAthleteMembership.user), joinedload(UserAthleteMembership.athlete_profile)).where(UserAthleteMembership.role == "coach", UserAthleteMembership.is_active.is_(True)).order_by(UserAthleteMembership.created_at, UserAthleteMembership.id)).all()
        return [CoachAssignment(row, row.user, row.athlete_profile) for row in rows if row.user.account_plan == "coach" and row.user.status == "active" and row.user.deleted_at is None and row.athlete_profile.deleted_at is None]

    def assign(self, coach_user_id: UUID, athlete_profile_id: UUID) -> CoachAssignment:
        coach = self.session.get(User, coach_user_id)
        if coach is None:
            raise CoachAssignmentError("coach_not_found")
        if coach.account_plan != "coach":
            raise CoachAssignmentError("coach_plan_required")
        if coach.status != "active" or coach.deleted_at is not None:
            raise CoachAssignmentError("coach_unavailable")
        athlete = self.session.get(AthleteProfile, athlete_profile_id)
        if athlete is None or athlete.deleted_at is not None:
            raise CoachAssignmentError("athlete_not_found")
        membership = self.session.scalar(select(UserAthleteMembership).where(UserAthleteMembership.user_id == coach.id, UserAthleteMembership.athlete_profile_id == athlete.id).with_for_update())
        active_count = len(list(self.session.scalars(select(UserAthleteMembership.id).where(UserAthleteMembership.user_id == coach.id, UserAthleteMembership.is_active.is_(True))).all()))
        if membership is not None:
            if membership.role != "coach":
                raise CoachAssignmentError("membership_role_conflict")
            membership.is_active = True
            if active_count == 0:
                membership.is_default = True
        else:
            membership = UserAthleteMembership(user_id=coach.id, athlete_profile_id=athlete.id, role="coach", is_active=True, is_default=active_count == 0)
            self.session.add(membership)
        self.session.flush()
        return CoachAssignment(membership, coach, athlete)

    def revoke(self, membership_id: UUID) -> CoachAssignment:
        membership = self.session.scalar(select(UserAthleteMembership).options(joinedload(UserAthleteMembership.user), joinedload(UserAthleteMembership.athlete_profile)).where(UserAthleteMembership.id == membership_id, UserAthleteMembership.role == "coach").with_for_update())
        if membership is None:
            raise CoachAssignmentError("assignment_not_found")
        membership.is_active = False
        membership.is_default = False
        self.session.flush()
        return CoachAssignment(membership, membership.user, membership.athlete_profile)
