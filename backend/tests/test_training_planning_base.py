from datetime import date,timedelta
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.application.planning import PlanningError,TrainingPlanningApplication
from app.db.base import Base
from app.db.models import AthleteProfile,CompetitionGoal,User

def test_plan_multiple_goals_sessions_and_provider_neutral_workout():
 engine=create_engine("sqlite+pysqlite:///:memory:",poolclass=StaticPool);Base.metadata.create_all(engine);s=Session(engine);user=User(email="p@test",normalized_email="p@test",auth_subject="p",account_plan="athlete");a=AthleteProfile(display_name="A",timezone="UTC",unit_system="metric");s.add_all([user,a]);s.flush();service=TrainingPlanningApplication(s);plan=service.create_plan(athlete_id=a.id,title="Season",start_date=date.today(),end_date=date.today()+timedelta(days=90),origin="human",creator_id=user.id,created_via_role="athlete")
 goals=[]
 for priority in "ABC":
  goal=CompetitionGoal(athlete_profile_id=a.id,name=f"Goal {priority}",event_date=date.today()+timedelta(days=30+len(goals)),timezone="UTC",event_category="running",event_format="10k",priority=priority,distance_m=10000,status="active",created_by_user_id=user.id);s.add(goal);s.flush();goals.append(goal);service.associate_goal(plan,goal,"primary" if priority=="A" else "supporting")
 planned=service.create_session(athlete_id=a.id,plan=plan,scheduled_date=date.today()+timedelta(days=1),sport="cycling",title="FTP",timezone="UTC",origin="human",creator_id=user.id,created_via_role="athlete");standalone=service.create_session(athlete_id=a.id,plan=None,scheduled_date=date.today()+timedelta(days=2),sport="running",title="Easy",timezone="UTC",origin="ai",creator_id=None,created_via_role=None);workout=service.attach_workout(planned,{"schema_version":1,"sport":"cycling","steps":[{"kind":"repeat","repetitions":3,"steps":[{"kind":"step","phase":"work","duration":{"mode":"time","seconds":720},"target":{"metric":"power","mode":"percent_reference","reference":"FTP","minimum":.9,"maximum":.95}}]}]});s.commit();assert len(goals)==3 and standalone.training_plan_id is None and workout.parsed_definition().steps[0].repetitions==3;assert "garmin" not in str(workout.definition).lower();s.close();engine.dispose()
def test_cross_athlete_associations_dates_and_ai_attribution_rejected():
 engine=create_engine("sqlite+pysqlite:///:memory:",poolclass=StaticPool);Base.metadata.create_all(engine);s=Session(engine);u=User(email="x@test",normalized_email="x@test",auth_subject="x",account_plan="owner");a=AthleteProfile(display_name="A");b=AthleteProfile(display_name="B");s.add_all([u,a,b]);s.flush();service=TrainingPlanningApplication(s)
 with pytest.raises(PlanningError):service.create_plan(athlete_id=a.id,title="bad",start_date=date.today()+timedelta(days=1),end_date=date.today(),origin="human",creator_id=u.id,created_via_role="owner")
 plan=service.create_plan(athlete_id=a.id,title="ok",start_date=date.today(),end_date=date.today(),origin="human",creator_id=u.id,created_via_role="owner");goal=CompetitionGoal(athlete_profile_id=b.id,name="B",event_date=date.today(),timezone="UTC",event_category="running",event_format="5k",priority="C",distance_m=5000,status="active",created_by_user_id=u.id);s.add(goal);s.flush()
 with pytest.raises(PlanningError):service.associate_goal(plan,goal,"supporting")
 with pytest.raises(PlanningError):service.create_session(athlete_id=b.id,plan=plan,scheduled_date=date.today(),sport="running",title="bad",timezone="UTC",origin="human",creator_id=u.id,created_via_role="owner")
 with pytest.raises(PlanningError):service.create_session(athlete_id=a.id,plan=None,scheduled_date=date.today(),sport="running",title="AI",timezone="UTC",origin="ai",creator_id=u.id,created_via_role=None)
 s.close();engine.dispose()
