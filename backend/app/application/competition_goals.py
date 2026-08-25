from datetime import date,datetime
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.orm import Session,selectinload
from app.db.models import CompetitionGoal,CompetitionGoalSegment
from app.domains.planning.models import CompetitionGoalInput
class CompetitionGoalError(ValueError):
 def __init__(self,code:str):self.code=code
class CompetitionGoalApplication:
 def __init__(self,session:Session):self.session=session
 def list(self,athlete_id:UUID,include_cancelled:bool=False):
  statement=select(CompetitionGoal).options(selectinload(CompetitionGoal.segments)).where(CompetitionGoal.athlete_profile_id==athlete_id)
  if not include_cancelled:statement=statement.where(CompetitionGoal.status!="cancelled")
  return list(self.session.scalars(statement.order_by(CompetitionGoal.event_date,CompetitionGoal.created_at,CompetitionGoal.id)).all())
 def get(self,athlete_id:UUID,goal_id:UUID):
  goal=self.session.scalar(select(CompetitionGoal).options(selectinload(CompetitionGoal.segments)).where(CompetitionGoal.id==goal_id,CompetitionGoal.athlete_profile_id==athlete_id))
  if goal is None:raise CompetitionGoalError("competition_goal_not_found")
  return goal
 def create(self,athlete_id:UUID,user_id:UUID,timezone:str,data:dict,source:dict|None=None):
  values=self._normalize({**data,"timezone":timezone,"status":"active"});validated=CompetitionGoalInput.model_validate(values);self._future(validated.event_date,timezone)
  goal=CompetitionGoal(athlete_profile_id=athlete_id,created_by_user_id=user_id,**validated.model_dump(exclude={"segments"}),**(source or {}));self.session.add(goal);self.session.flush();self._segments(goal,validated.segments);self._legacy(goal);return goal
 def update(self,athlete_id:UUID,goal_id:UUID,timezone:str,data:dict):
  if not data:raise CompetitionGoalError("competition_goal_update_empty")
  goal=self.get(athlete_id,goal_id);current={key:getattr(goal,key) for key in CompetitionGoalInput.model_fields if key!="segments"};current["segments"]=[{"position":x.position,"sport":x.sport,"distance_m":x.distance_m,"label":x.label,"elevation_gain_m":x.elevation_gain_m} for x in goal.segments];current.update(data);current["timezone"]=timezone;validated=CompetitionGoalInput.model_validate(self._normalize(current))
  if validated.status=="active":self._future(validated.event_date,timezone)
  for key,value in validated.model_dump(exclude={"segments"}).items():setattr(goal,key,value)
  self._segments(goal,validated.segments);self._legacy(goal);self.session.flush();return goal
 def cancel(self,athlete_id:UUID,goal_id:UUID):goal=self.get(athlete_id,goal_id);goal.status="cancelled";self.session.flush();return goal
 def imported(self,athlete_id:UUID,provider:str,external_id:str):return self.session.scalar(select(CompetitionGoal).where(CompetitionGoal.athlete_profile_id==athlete_id,CompetitionGoal.source_provider==provider,CompetitionGoal.source_external_id==external_id))
 @staticmethod
 def _normalize(data):
  legacy_fields={"distance_m","swim_distance_m","bike_distance_m","run_distance_m"}
  clean={key:value for key,value in data.items() if key not in legacy_fields}
  if data.get("segments") is not None:
   clean["segments"]=[{**x,"position":i+1} for i,x in enumerate(data["segments"])];return clean
  segments=[]
  if data.get("event_category")=="triathlon":
   for sport,key in (("swim","swim_distance_m"),("bike","bike_distance_m"),("run","run_distance_m")):
    if data.get(key,0)>0:segments.append({"position":len(segments)+1,"sport":sport,"distance_m":data[key]})
  elif data.get("distance_m",0)>0:segments=[{"position":1,"sport":{"swimming":"swim","cycling":"bike"}.get(data.get("event_category"),"run"),"distance_m":data["distance_m"]}]
  clean["segments"]=segments;return clean
 def _segments(self,goal,segments):
  goal.segments.clear();self.session.flush()
  for item in segments:goal.segments.append(CompetitionGoalSegment(position=item.position,sport=item.sport,distance_m=item.distance_m,label=item.label,elevation_gain_m=item.elevation_gain_m))
 def _legacy(self,goal):
  goal.distance_m=goal.swim_distance_m=goal.bike_distance_m=goal.run_distance_m=None
  if len(goal.segments)==1:goal.distance_m=goal.segments[0].distance_m
  for item in goal.segments:
   key={"swim":"swim_distance_m","bike":"bike_distance_m","run":"run_distance_m"}[item.sport]
   if getattr(goal,key) is None:setattr(goal,key,item.distance_m)
 @staticmethod
 def _future(event_date:date,timezone:str):
  if event_date<datetime.now(ZoneInfo(timezone)).date():raise CompetitionGoalError("competition_goal_date_in_past")
