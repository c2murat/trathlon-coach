from datetime import date
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.models import CompetitionGoal,PlannedTrainingSession,StructuredWorkout,TrainingPlan,TrainingPlanGoal
from app.domains.planning.models import StructuredWorkoutDefinition
class PlanningError(ValueError):pass
class TrainingPlanningApplication:
 def __init__(self,session:Session):self.session=session
 def create_plan(self,*,athlete_id:UUID,title:str,start_date:date,end_date:date,origin:str,creator_id:UUID|None,created_via_role:str|None,algorithm_version:str|None=None):
  if start_date>end_date or origin not in {"human","ai"} or (origin=="ai" and creator_id is not None):raise PlanningError("invalid_training_plan")
  plan=TrainingPlan(athlete_profile_id=athlete_id,title=title,start_date=start_date,end_date=end_date,status="draft",origin=origin,created_by_user_id=creator_id,created_via_role=created_via_role,algorithm_version=algorithm_version);self.session.add(plan);self.session.flush();return plan
 def associate_goal(self,plan:TrainingPlan,goal:CompetitionGoal,relationship:str):
  if plan.athlete_profile_id!=goal.athlete_profile_id:raise PlanningError("cross_athlete_goal")
  item=TrainingPlanGoal(training_plan_id=plan.id,competition_goal_id=goal.id,relationship=relationship);self.session.add(item);self.session.flush();return item
 def create_session(self,*,athlete_id:UUID,plan:TrainingPlan|None,scheduled_date:date,sport:str,title:str,timezone:str,origin:str,creator_id:UUID|None,created_via_role:str|None):
  if plan is not None and plan.athlete_profile_id!=athlete_id:raise PlanningError("cross_athlete_plan")
  if origin=="ai" and creator_id is not None:raise PlanningError("ai_creator_must_be_null")
  item=PlannedTrainingSession(athlete_profile_id=athlete_id,training_plan_id=plan.id if plan else None,scheduled_date=scheduled_date,timezone=timezone,sport=sport,title=title,status="planned",origin=origin,created_by_user_id=creator_id,created_via_role=created_via_role);self.session.add(item);self.session.flush();return item
 def attach_workout(self,session:PlannedTrainingSession,definition:dict):
  parsed=StructuredWorkoutDefinition.model_validate(definition);item=StructuredWorkout(planned_training_session_id=session.id,schema_version=parsed.schema_version,definition=parsed.model_dump(mode="json",exclude_none=True));self.session.add(item);self.session.flush();return item
