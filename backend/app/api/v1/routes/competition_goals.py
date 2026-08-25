from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Response,status
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.api.dependencies.athlete_permissions import AthleteCapability,require_athlete_capability
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.schemas.competition_goals import CompetitionGoalCreateRequest,CompetitionGoalResponse,CompetitionGoalUpdateRequest
from app.application.competition_goals import CompetitionGoalApplication,CompetitionGoalError
from app.db.session import get_db_session
router=APIRouter(prefix="/competition-goals",tags=["competition-goals"])
read=require_athlete_capability(AthleteCapability.READ_TRAINING_PLANNING);manage=require_athlete_capability(AthleteCapability.MANAGE_COMPETITION_GOALS)
def response(goal):return CompetitionGoalResponse.model_validate(goal,from_attributes=True)
def execute(session,operation):
 try:
  value=operation();session.commit();return value
 except CompetitionGoalError as exc:
  session.rollback();code=404 if exc.code=="competition_goal_not_found" else 422;raise HTTPException(status_code=code,detail={"code":exc.code}) from None
 except ValidationError as exc:
  session.rollback();raise HTTPException(status_code=422,detail={"code":"competition_goal_invalid","errors":exc.errors(include_url=False)}) from None
 except Exception:session.rollback();raise
@router.get("",response_model=list[CompetitionGoalResponse])
def list_goals(current:CurrentAthleteContext=Depends(read),session:Session=Depends(get_db_session)):return [response(x) for x in CompetitionGoalApplication(session).list(current.athlete_id)]
@router.post("",response_model=CompetitionGoalResponse,status_code=201)
def create_goal(payload:CompetitionGoalCreateRequest,current:CurrentAthleteContext=Depends(manage),session:Session=Depends(get_db_session)):
 data=payload.model_dump(exclude_unset=True);provider=data.pop("source_provider",None);url=data.pop("source_url",None);source={"source_provider":provider,"source_url":str(url)} if provider and url else None
 return response(execute(session,lambda:CompetitionGoalApplication(session).create(current.athlete_id,current.user_id,current.athlete_profile.timezone,data,source)))
@router.get("/{goal_id}",response_model=CompetitionGoalResponse)
def get_goal(goal_id:UUID,current:CurrentAthleteContext=Depends(read),session:Session=Depends(get_db_session)):return response(execute(session,lambda:CompetitionGoalApplication(session).get(current.athlete_id,goal_id)))
@router.patch("/{goal_id}",response_model=CompetitionGoalResponse)
def update_goal(goal_id:UUID,payload:CompetitionGoalUpdateRequest,current:CurrentAthleteContext=Depends(manage),session:Session=Depends(get_db_session)):
 data=payload.model_dump(exclude_unset=True);data.pop("source_provider",None);data.pop("source_url",None)
 return response(execute(session,lambda:CompetitionGoalApplication(session).update(current.athlete_id,goal_id,current.athlete_profile.timezone,data)))
@router.delete("/{goal_id}",status_code=204)
def cancel_goal(goal_id:UUID,current:CurrentAthleteContext=Depends(manage),session:Session=Depends(get_db_session)):execute(session,lambda:CompetitionGoalApplication(session).cancel(current.athlete_id,goal_id));return Response(status_code=204)
