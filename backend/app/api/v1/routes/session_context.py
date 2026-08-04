from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies.athlete_permissions import capabilities_for_role
from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.schemas.session_context import AthleteMembershipResponse,CurrentUserResponse,SessionContextResponse
from app.db.models import User,UserAthleteMembership
from app.db.session import get_db_session
router=APIRouter(tags=["session"])
@router.get("/session/context",response_model=SessionContextResponse)
def get_session_context(current_user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session),requested_athlete_id:str|None=Header(default=None,alias="X-TriCoach-Athlete-Id"))->SessionContextResponse:
 user=session.get(User,current_user.id)
 if user is None:raise HTTPException(404,detail={"code":"user_not_found"})
 memberships=list(session.scalars(select(UserAthleteMembership).where(UserAthleteMembership.user_id==current_user.id,UserAthleteMembership.is_active.is_(True))).all())
 views=[AthleteMembershipResponse(athlete_id=m.athlete_profile_id,label="Mi atleta" if len(memberships)==1 else f"Atleta · {str(m.athlete_profile_id)[:4]}",role=m.role,is_default=m.is_default,capabilities=[c.value for c in capabilities_for_role(m.role)]) for m in memberships]
 views.sort(key=lambda x:(not x.is_default,x.label.casefold(),str(x.athlete_id)));selected=None;required=False
 if requested_athlete_id is not None:
  try:requested=UUID(requested_athlete_id)
  except (ValueError,TypeError,AttributeError):raise HTTPException(422,detail={"code":"invalid_athlete_id"}) from None
  if not any(x.athlete_id==requested for x in views):raise HTTPException(403,detail={"code":"athlete_not_authorized"})
  selected=requested
 elif len(views)==1:selected=views[0].athlete_id
 elif len(views)>1:
  defaults=[x for x in views if x.is_default]
  if len(defaults)>1:raise HTTPException(409,detail={"code":"athlete_default_configuration_invalid"})
  if defaults:selected=defaults[0].athlete_id
  else:required=True
 name=(user.display_name or "").strip() or user.email or "Usuario"
 return SessionContextResponse(user=CurrentUserResponse(id=user.id,display_name=name,email=user.email),athletes=views,selected_athlete_id=selected,selection_required=required)
