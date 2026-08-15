from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import CompetitionGoal
from app.domains.planning.models import CompetitionGoalInput

class CompetitionGoalError(ValueError):
    def __init__(self,code:str):self.code=code
class CompetitionGoalApplication:
    def __init__(self,session:Session):self.session=session
    def list(self,athlete_id:UUID,include_cancelled:bool=False):
        statement=select(CompetitionGoal).where(CompetitionGoal.athlete_profile_id==athlete_id)
        if not include_cancelled:statement=statement.where(CompetitionGoal.status!="cancelled")
        return list(self.session.scalars(statement.order_by(CompetitionGoal.event_date,CompetitionGoal.created_at,CompetitionGoal.id)).all())
    def get(self,athlete_id:UUID,goal_id:UUID):
        goal=self.session.scalar(select(CompetitionGoal).where(CompetitionGoal.id==goal_id,CompetitionGoal.athlete_profile_id==athlete_id))
        if goal is None:raise CompetitionGoalError("competition_goal_not_found")
        return goal
    def create(self,athlete_id:UUID,user_id:UUID,timezone:str,data:dict):
        values={**data,"timezone":timezone,"status":"active"};validated=CompetitionGoalInput.model_validate(values)
        self._future(validated.event_date,timezone)
        goal=CompetitionGoal(athlete_profile_id=athlete_id,created_by_user_id=user_id,**validated.model_dump())
        self.session.add(goal);self.session.flush();return goal
    def update(self,athlete_id:UUID,goal_id:UUID,timezone:str,data:dict):
        if not data:raise CompetitionGoalError("competition_goal_update_empty")
        goal=self.get(athlete_id,goal_id)
        current={key:getattr(goal,key) for key in CompetitionGoalInput.model_fields};current.update(data);current["timezone"]=timezone
        validated=CompetitionGoalInput.model_validate(current)
        if validated.status=="active":self._future(validated.event_date,timezone)
        for key,value in validated.model_dump().items():setattr(goal,key,value)
        self.session.flush();return goal
    def cancel(self,athlete_id:UUID,goal_id:UUID):
        goal=self.get(athlete_id,goal_id);goal.status="cancelled";self.session.flush();return goal
    @staticmethod
    def _future(event_date:date,timezone:str):
        today = datetime.now(ZoneInfo(timezone)).date()
        if event_date < today:
            raise CompetitionGoalError("competition_goal_date_in_past")
