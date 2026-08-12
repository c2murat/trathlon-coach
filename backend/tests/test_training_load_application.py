from test_activity_reads import activity_client
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.base import utc_now
from app.db.models import ActivityTrainingLoad, AthletePerformanceProfileVersion, AthleteProfile, CompletedActivity
from app.application.training_load import TrainingLoadApplication
ALGORITHM_VERSION="0.7b.1"

def test_training_load_persistence_and_idempotence(activity_client):
 _,engine=activity_client
 with Session(engine) as s:
  a=s.query(CompletedActivity).first(); p=AthletePerformanceProfileVersion(athlete_profile_id=a.athlete_id,effective_from=a.start_at-timedelta(days=1),data_origin="manual",algorithm_version="p",cycling_ftp_watts=250); s.add(p); s.commit()
  app=TrainingLoadApplication(s); first=app.calculate_for_activity(a.athlete_id,a.id); s.commit(); second=app.calculate_for_activity(a.athlete_id,a.id); s.commit(); rows=s.query(ActivityTrainingLoad).filter_by(completed_activity_id=a.id,algorithm_version=ALGORITHM_VERSION).all(); assert len(rows)==1 and first.load==second.load and rows[0].warnings

def test_future_profile_is_not_used(activity_client):
 _,engine=activity_client
 with Session(engine) as s:
  a=s.query(CompletedActivity).first(); s.add(AthletePerformanceProfileVersion(athlete_profile_id=a.athlete_id,effective_from=a.start_at+timedelta(days=1),data_origin="manual",algorithm_version="p",cycling_ftp_watts=100)); s.commit(); result=TrainingLoadApplication(s).calculate_for_activity(a.athlete_id,a.id); assert result.method.value=="duration_only"

def test_training_load_never_falls_back_to_another_athletes_profile(activity_client):
 _,engine=activity_client
 with Session(engine) as s:
  activity=s.query(CompletedActivity).first();activity.sport="cycling";activity.average_power_w=220;activity.weighted_average_power_w=230
  other=AthleteProfile(display_name="Athlete A",timezone="UTC",unit_system="metric");s.add(other);s.flush();s.add(AthletePerformanceProfileVersion(athlete_profile_id=other.id,effective_from=activity.start_at-timedelta(days=1),data_origin="manual",algorithm_version="p",cycling_ftp_watts=250));s.commit()
  result=TrainingLoadApplication(s).calculate_for_activity(activity.athlete_id,activity.id);assert result.method.value=="duration_only"

def test_null_load_and_json_roundtrip(activity_client):
 _,engine=activity_client
 with Session(engine) as s:
  a=s.query(CompletedActivity).first(); row=ActivityTrainingLoad(completed_activity_id=a.id,algorithm_version="x",method="duration_only",unit="load_points",coverage="unavailable",quality=None,reason="missing_duration",duration_seconds=None,load_value=None,source_metrics={"ok":True},warnings=["aviso"],calculated_at=utc_now()); s.add(row); s.commit(); got=s.get(ActivityTrainingLoad,row.id); assert got.load_value is None and got.source_metrics=={"ok":True} and got.warnings==["aviso"]

def test_negative_load_rejected(activity_client):
 _,engine=activity_client
 with Session(engine) as s:
  a=s.query(CompletedActivity).first(); s.add(ActivityTrainingLoad(completed_activity_id=a.id,algorithm_version="negative",method="duration_only",unit="load_points",coverage="partial",quality="low",duration_seconds=1,load_value=-1,source_metrics={},warnings=[],calculated_at=utc_now()));
  try: s.commit(); assert False
  except IntegrityError: s.rollback()



