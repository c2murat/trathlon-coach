from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.account_permissions import require_owner_account
from app.api.dependencies.athlete_permissions import capabilities_for_role
from app.api.v1.schemas.athletes import AthleteCreateRequest, AthleteCreateResponse
from app.application.athletes import (
    AthleteAccountUnavailableError,
    AthleteApplication,
    AthleteDefaultConfigurationError,
)
from app.db.models import User
from app.db.session import get_db_session


router = APIRouter(prefix="/athletes", tags=["athletes"])
DEFAULT_INDEX = "uq_user_athlete_memberships_active_default_user"


def _default_conflict(exc: IntegrityError) -> bool:
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    return constraint_name == DEFAULT_INDEX


@router.post("", response_model=AthleteCreateResponse, status_code=status.HTTP_201_CREATED)
def create_athlete(
    payload: AthleteCreateRequest,
    current_user: User = Depends(require_owner_account),
    session: Session = Depends(get_db_session),
) -> AthleteCreateResponse:
    try:
        created = AthleteApplication(session).create_owned_athlete(
            current_user.id,
            display_name=payload.display_name,
            timezone=payload.timezone,
            unit_system=payload.unit_system,
        )
        session.commit()
    except AthleteAccountUnavailableError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
        ) from None
    except AthleteDefaultConfigurationError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "athlete_default_configuration_invalid"},
        ) from None
    except IntegrityError as exc:
        session.rollback()
        if _default_conflict(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "athlete_default_configuration_invalid"},
            ) from None
        raise
    except Exception:
        session.rollback()
        raise

    return AthleteCreateResponse(
        id=created.athlete.id,
        display_name=created.athlete.display_name,
        timezone=created.athlete.timezone,
        unit_system=created.athlete.unit_system,
        role="owner",
        is_default=created.membership.is_default,
        capabilities=[item.value for item in capabilities_for_role("owner")],
    )
