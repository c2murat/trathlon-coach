from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.account_permissions import require_owner_account
from app.api.v1.schemas.coach_assignments import AthleteCandidateResponse, CoachAssignmentCandidatesResponse, CoachAssignmentCreateRequest, CoachAssignmentResponse, CoachCandidateResponse
from app.application.coach_assignments import CoachAssignment, CoachAssignmentApplication, CoachAssignmentError
from app.db.models import User
from app.db.session import get_db_session

router = APIRouter(prefix="/coach-assignments", tags=["coach assignments"])


def output(item: CoachAssignment) -> CoachAssignmentResponse:
    return CoachAssignmentResponse(membership_id=item.membership.id, coach_user_id=item.coach.id, coach_display_name=(item.coach.display_name or "").strip() or item.coach.email, coach_email=item.coach.email, athlete_profile_id=item.athlete.id, athlete_display_name=item.athlete.display_name, is_active=item.membership.is_active, is_default=item.membership.is_default)


@router.get("/candidates", response_model=CoachAssignmentCandidatesResponse)
def candidates(_: User = Depends(require_owner_account), session: Session = Depends(get_db_session)):
    app = CoachAssignmentApplication(session)
    return CoachAssignmentCandidatesResponse(coaches=[CoachCandidateResponse(user_id=u.id, display_name=(u.display_name or "").strip() or u.email, email=u.email) for u in app.coach_candidates()], athletes=[AthleteCandidateResponse(athlete_profile_id=a.id, display_name=a.display_name) for a in app.athlete_candidates()])


@router.get("", response_model=list[CoachAssignmentResponse])
def list_assignments(_: User = Depends(require_owner_account), session: Session = Depends(get_db_session)):
    return [output(item) for item in CoachAssignmentApplication(session).active_assignments()]


@router.post("", response_model=CoachAssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(payload: CoachAssignmentCreateRequest, _: User = Depends(require_owner_account), session: Session = Depends(get_db_session)):
    try:
        item = CoachAssignmentApplication(session).assign(payload.coach_user_id, payload.athlete_profile_id)
        session.commit()
        return output(item)
    except CoachAssignmentError as exc:
        session.rollback()
        code = str(exc)
        raise HTTPException(404 if code in {"coach_not_found", "athlete_not_found"} else 409, detail={"code": code}) from None
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, detail={"code": "assignment_conflict"}) from None
    except Exception:
        session.rollback()
        raise


@router.delete("/{membership_id}", response_model=CoachAssignmentResponse)
def revoke_assignment(membership_id: UUID, _: User = Depends(require_owner_account), session: Session = Depends(get_db_session)):
    try:
        item = CoachAssignmentApplication(session).revoke(membership_id)
        session.commit()
        return output(item)
    except CoachAssignmentError as exc:
        session.rollback()
        raise HTTPException(404, detail={"code": str(exc)}) from None
    except Exception:
        session.rollback()
        raise
