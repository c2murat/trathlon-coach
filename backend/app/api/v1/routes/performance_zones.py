from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies.current_athlete import CurrentAthleteContext, get_current_athlete
from app.application.performance_zones import resolve_zone_sets
from app.db.session import get_db_session
router=APIRouter(prefix="/athlete",tags=["performance-zones"])
@router.get("/performance-zones",response_model=list[dict])
def zones(effective_at:datetime|None=None,current_athlete:CurrentAthleteContext=Depends(get_current_athlete),session:Session=Depends(get_db_session)):
 return resolve_zone_sets(session,current_athlete.athlete_id,effective_at)
