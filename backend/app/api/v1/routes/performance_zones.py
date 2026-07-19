from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.application.performance_references import PerformanceReferenceRepository
from app.application.performance_zones import resolve_zone_sets
from app.db.models import AthleteProfile
from app.db.session import get_db_session
from sqlalchemy import select
router=APIRouter(prefix="/athlete",tags=["performance-zones"])
@router.get("/performance-zones",response_model=list[dict])
def zones(effective_at:datetime|None=None,user:AuthenticatedUser=Depends(get_current_user),session:Session=Depends(get_db_session)):
 a=session.scalar(select(AthleteProfile).where(AthleteProfile.user_id==user.id)); return [] if not a else resolve_zone_sets(session,a.id,effective_at)
