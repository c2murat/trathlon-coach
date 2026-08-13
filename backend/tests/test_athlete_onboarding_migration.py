from __future__ import annotations
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from app.core.settings import get_settings

@contextmanager
def migrated_database(monkeypatch):
 base=make_url(get_settings().database_url);name=f"tricoach_0018_test_{uuid4().hex}";admin=create_engine(base.set(database="postgres"),isolation_level="AUTOCOMMIT")
 with admin.connect() as c:c.execute(text(f'CREATE DATABASE "{name}"'))
 url=base.set(database=name);old=os.environ.get("TC_DATABASE_URL");monkeypatch.setenv("TC_DATABASE_URL",url.render_as_string(hide_password=False));get_settings.cache_clear();cfg=Config("alembic.ini");cfg.attributes["skip_logging_config"]=True
 try:
  command.upgrade(cfg,"0017_authentication_base");yield create_engine(url),cfg
 finally:
  get_settings.cache_clear()
  if old is None:monkeypatch.delenv("TC_DATABASE_URL",raising=False)
  else:monkeypatch.setenv("TC_DATABASE_URL",old)
  with admin.connect() as c:c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:n AND pid<>pg_backend_pid()"),{"n":name});c.execute(text(f'DROP DATABASE "{name}"'))
  admin.dispose()

def seed(engine,*,display="  Ana   Deportista  ",owner=True):
 uid=uuid4();aid=uuid4()
 with engine.begin() as c:
  c.execute(text("INSERT INTO users(id,email,normalized_email,auth_subject,status,timezone,display_name,created_at,updated_at) VALUES(:u,:e,:e,:s,'active','UTC',:d,now(),now())"),{"u":uid,"e":f"{uid}@invalid","s":str(uid),"d":display})
  c.execute(text("INSERT INTO athlete_profiles(id,user_id,timezone,unit_system,created_at,updated_at) VALUES(:a,:u,'UTC','metric',now(),now())"),{"a":aid,"u":uid})
  if owner:c.execute(text("INSERT INTO user_athlete_memberships(id,user_id,athlete_profile_id,role,is_active,is_default,created_at,updated_at) VALUES(:i,:u,:a,'owner',true,true,now(),now())"),{"i":uuid4(),"u":uid,"a":aid})
 return uid,aid

def test_upgrade_preserves_identity_backfills_and_downgrades(monkeypatch):
 with migrated_database(monkeypatch) as (engine,cfg):
  uid,aid=seed(engine)
  with engine.connect() as c:before=c.scalar(text("SELECT count(*) FROM athlete_profiles"))
  command.upgrade(cfg,"0018_athlete_onboarding")
  with engine.connect() as c:
   assert c.scalar(text("SELECT count(*) FROM athlete_profiles"))==before
   assert c.scalar(text("SELECT display_name FROM athlete_profiles WHERE id=:a"),{"a":aid})=="Ana Deportista"
   assert "user_id" not in {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='athlete_profiles'"))}
   assert c.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname='uq_user_athlete_memberships_active_default_user'"))==1
  command.downgrade(cfg,"0017_authentication_base")
  with engine.connect() as c:assert c.scalar(text("SELECT user_id FROM athlete_profiles WHERE id=:a"),{"a":aid})==uid
  engine.dispose()

@pytest.mark.parametrize("corruption",["missing_owner","owner_mismatch","multiple_defaults"])
def test_upgrade_aborts_on_unsafe_ownership_or_defaults(monkeypatch,corruption):
 with migrated_database(monkeypatch) as (engine,cfg):
  uid,aid=seed(engine,owner=corruption!="missing_owner")
  with engine.begin() as c:
   if corruption=="owner_mismatch":
    other=uuid4();c.execute(text("INSERT INTO users(id,email,normalized_email,auth_subject,status,timezone,created_at,updated_at) VALUES(:u,:e,:e,:s,'active','UTC',now(),now())"),{"u":other,"e":f"{other}@invalid","s":str(other)});c.execute(text("INSERT INTO user_athlete_memberships(id,user_id,athlete_profile_id,role,is_active,is_default,created_at,updated_at) VALUES(:i,:u,:a,'owner',true,false,now(),now())"),{"i":uuid4(),"u":other,"a":aid})
   if corruption=="multiple_defaults":
    other=uuid4();aid2=uuid4();c.execute(text("INSERT INTO users(id,email,normalized_email,auth_subject,status,timezone,created_at,updated_at) VALUES(:u,:e,:e,:s,'active','UTC',now(),now())"),{"u":other,"e":f"{other}@invalid","s":str(other)});c.execute(text("INSERT INTO athlete_profiles(id,user_id,timezone,unit_system,created_at,updated_at) VALUES(:a,:u,'UTC','metric',now(),now())"),{"a":aid2,"u":other});c.execute(text("INSERT INTO user_athlete_memberships(id,user_id,athlete_profile_id,role,is_active,is_default,created_at,updated_at) VALUES(:i,:u,:a,'owner',true,true,now(),now()),(:j,:legacy,:a,'coach',true,true,now(),now())"),{"i":uuid4(),"j":uuid4(),"u":other,"legacy":uid,"a":aid2})
  with pytest.raises(Exception):command.upgrade(cfg,"0018_athlete_onboarding")
  engine.dispose()

def test_fallback_constraint_and_ambiguous_downgrade(monkeypatch):
 with migrated_database(monkeypatch) as (engine,cfg):
  uid,aid=seed(engine,display=None);command.upgrade(cfg,"0018_athlete_onboarding")
  with engine.begin() as c:
   assert c.scalar(text("SELECT display_name FROM athlete_profiles WHERE id=:a"),{"a":aid})==f"Atleta {str(aid)[:8]}"
   other=uuid4();c.execute(text("INSERT INTO users(id,email,normalized_email,auth_subject,status,timezone,created_at,updated_at) VALUES(:u,:e,:e,:s,'active','UTC',now(),now())"),{"u":other,"e":f"{other}@invalid","s":str(other)});c.execute(text("INSERT INTO user_athlete_memberships(id,user_id,athlete_profile_id,role,is_active,is_default,created_at,updated_at) VALUES(:i,:u,:a,'owner',true,false,now(),now())"),{"i":uuid4(),"u":other,"a":aid})
  with pytest.raises(Exception):command.downgrade(cfg,"0017_authentication_base")
  engine.dispose()




def _seed_sports_history(engine, athlete_id):
 ids={name:uuid4() for name in ('account','credential','activity','activity_load','daily','weekly','strength','strength_load','profile','reference','status')};now=datetime(2026,1,15,10,tzinfo=timezone.utc)
 with engine.begin() as c:
  c.execute(text("INSERT INTO integration_accounts(id,athlete_id,provider,external_account_id,status,scopes,created_at,updated_at) VALUES(:id,:a,'strava','fixture-account','active','[]'::json,:n,:n)"),{'id':ids['account'],'a':athlete_id,'n':now})
  c.execute(text("INSERT INTO oauth_credentials(id,integration_account_id,access_token,token_type,scopes,expires_at,key_version,created_at,updated_at) VALUES(:id,:account,'fixture-secret','Bearer','[]'::json,:expires,'fixture-key',:n,:n)"),{'id':ids['credential'],'account':ids['account'],'expires':datetime(2026,1,16,10,tzinfo=timezone.utc),'n':now})
  c.execute(text("INSERT INTO completed_activities(id,athlete_id,source_integration_account_id,external_activity_id,source_summary,sport,name,start_at,timezone,elapsed_time_s,created_at,updated_at) VALUES(:id,:a,:account,'fixture-activity','strava','running','Representative run',:n,'UTC',3600,:n,:n)"),{'id':ids['activity'],'a':athlete_id,'account':ids['account'],'n':now})
  c.execute(text("INSERT INTO activity_training_loads(id,created_at,updated_at,completed_activity_id,load_value,method,unit,coverage,quality,algorithm_version,source_metrics,warnings,calculated_at) VALUES(:id,:n,:n,:activity,75,'trimp','load','complete','high','fixture-v1','{}'::json,'[]'::json,:n)"),{'id':ids['activity_load'],'activity':ids['activity'],'n':now})
  common={'a':athlete_id,'n':now,'activity':str(ids['activity'])}
  c.execute(text("INSERT INTO athlete_daily_training_loads(id,created_at,updated_at,athlete_profile_id,timezone_name,source_load_algorithm_version,aggregation_algorithm_version,total_load,activity_count,loaded_activity_count,null_load_activity_count,total_duration_seconds,coverage,quality,warnings,activity_ids,calculated_at,local_date,endurance_load,strength_load,strength_session_count,manual_strength_algorithm_version) VALUES(:id,:n,:n,:a,'UTC','fixture-v1','agg-v1',95,1,1,0,3600,'complete','high','[]'::json,json_build_array(CAST(:activity AS text)),:n,DATE '2026-01-15',75,20,1,'strength-v1')"),{**common,'id':ids['daily']})
  c.execute(text("INSERT INTO athlete_weekly_training_loads(id,created_at,updated_at,athlete_profile_id,timezone_name,source_load_algorithm_version,aggregation_algorithm_version,total_load,activity_count,loaded_activity_count,null_load_activity_count,total_duration_seconds,coverage,quality,warnings,activity_ids,calculated_at,iso_year,iso_week,week_start_date,week_end_date,endurance_load,strength_load,strength_session_count,manual_strength_algorithm_version) VALUES(:id,:n,:n,:a,'UTC','fixture-v1','agg-v1',95,1,1,0,3600,'complete','high','[]'::json,json_build_array(CAST(:activity AS text)),:n,2026,3,DATE '2026-01-12',DATE '2026-01-18',75,20,1,'strength-v1')"),{**common,'id':ids['weekly']})
  c.execute(text("INSERT INTO manual_strength_sessions(id,created_at,updated_at,athlete_id,started_at,timezone_name,duration_minutes,body_regions,perceived_exertion) VALUES(:id,:n,:n,:a,:n,'UTC',30,'[\"core\"]'::json,6)"),{'id':ids['strength'],'a':athlete_id,'n':now})
  c.execute(text("INSERT INTO manual_strength_training_loads(id,session_id,load_value,method,unit,quality,warnings,algorithm_version,calculated_at) VALUES(:id,:session,20,'session_rpe','load','high','[]'::json,'strength-v1',:n)"),{'id':ids['strength_load'],'session':ids['strength'],'n':now})
  c.execute(text("INSERT INTO athlete_performance_profile_versions(id,athlete_profile_id,effective_from,data_origin,algorithm_version,resting_heart_rate_bpm,created_at,updated_at) VALUES(:id,:a,:n,'manual','profile-v1',50,:n,:n)"),{'id':ids['profile'],'a':athlete_id,'n':now})
  c.execute(text("INSERT INTO athlete_performance_references(id,athlete_profile_id,sport,metric_type,value,unit,data_origin,quality_level,effective_from,created_at,updated_at) VALUES(:id,:a,'running','threshold_pace',300,'seconds_per_km','manual','high',:n,:n,:n)"),{'id':ids['reference'],'a':athlete_id,'n':now})
  c.execute(text("INSERT INTO athlete_daily_training_statuses(id,athlete_profile_id,local_date,timezone_name,training_load_algorithm_version,manual_strength_algorithm_version,training_status_algorithm_version,total_load,fitness,fatigue,form,history_day_number,is_warmup,calculated_at,created_at,updated_at) VALUES(:id,:a,DATE '2026-01-15','UTC','fixture-v1','strength-v1','status-v1',95,60,70,-10,15,false,:n,:n,:n)"),{'id':ids['status'],'a':athlete_id,'n':now})
 return ids

def _sports_snapshot(engine, athlete_id):
 queries={'athletes':'SELECT id FROM athlete_profiles WHERE id=:a','integration_accounts':'SELECT id,athlete_id,provider,external_account_id FROM integration_accounts WHERE athlete_id=:a','oauth_credentials':'SELECT c.id,c.integration_account_id FROM oauth_credentials c JOIN integration_accounts i ON i.id=c.integration_account_id WHERE i.athlete_id=:a','activities':'SELECT id,athlete_id,source_integration_account_id FROM completed_activities WHERE athlete_id=:a','activity_loads':'SELECT l.id,l.completed_activity_id FROM activity_training_loads l JOIN completed_activities a ON a.id=l.completed_activity_id WHERE a.athlete_id=:a','daily_aggregates':'SELECT id,athlete_profile_id FROM athlete_daily_training_loads WHERE athlete_profile_id=:a','weekly_aggregates':'SELECT id,athlete_profile_id FROM athlete_weekly_training_loads WHERE athlete_profile_id=:a','strength_sessions':'SELECT id,athlete_id FROM manual_strength_sessions WHERE athlete_id=:a','strength_loads':'SELECT l.id,l.session_id FROM manual_strength_training_loads l JOIN manual_strength_sessions s ON s.id=l.session_id WHERE s.athlete_id=:a','performance_profiles':'SELECT id,athlete_profile_id FROM athlete_performance_profile_versions WHERE athlete_profile_id=:a','performance_references':'SELECT id,athlete_profile_id FROM athlete_performance_references WHERE athlete_profile_id=:a','training_status':'SELECT id,athlete_profile_id FROM athlete_daily_training_statuses WHERE athlete_profile_id=:a'}
 with engine.connect() as c:
  result={}
  for name,sql in queries.items():
   rows=c.execute(text(sql),{'a':athlete_id}).all();result[name]={'count':len(rows),'rows':[tuple(str(v) for v in row) for row in rows]}
  return result

def test_upgrade_preserves_representative_sports_history(monkeypatch):
 with migrated_database(monkeypatch) as (engine,cfg):
  uid,aid=seed(engine);ids=_seed_sports_history(engine,aid);before=_sports_snapshot(engine,aid)
  assert all(value['count']==1 for value in before.values())
  command.upgrade(cfg,'0018_athlete_onboarding');after=_sports_snapshot(engine,aid)
  assert after==before
  with engine.connect() as c:
   assert c.execute(text("SELECT user_id,athlete_profile_id,is_active,is_default,role FROM user_athlete_memberships WHERE athlete_profile_id=:a"),{'a':aid}).one()==(uid,aid,True,True,'owner')
   assert c.scalar(text("SELECT display_name FROM athlete_profiles WHERE id=:a"),{'a':aid})=='Ana Deportista'
   assert 'user_id' not in {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='athlete_profiles'"))}
   assert c.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname='uq_user_athlete_memberships_active_default_user'"))==1
  assert before['activity_loads']['rows'][0][1]==str(ids['activity'])
  assert before['strength_loads']['rows'][0][1]==str(ids['strength'])
  assert before['oauth_credentials']['rows'][0][1]==str(ids['account'])
  engine.dispose()

def test_0019_allows_athlete_without_backfill_and_blocks_unsafe_downgrade(monkeypatch):
 with migrated_database(monkeypatch) as (engine,cfg):
  uid,aid=seed(engine);command.upgrade(cfg,"0018_athlete_onboarding")
  with engine.connect() as c:before=c.execute(text("SELECT user_id,athlete_profile_id,role,is_default FROM user_athlete_memberships")).all()
  command.upgrade(cfg,"0019_athlete_membership_role")
  with engine.connect() as c:assert c.execute(text("SELECT user_id,athlete_profile_id,role,is_default FROM user_athlete_memberships")).all()==before
  with engine.begin() as c:c.execute(text("UPDATE user_athlete_memberships SET role='athlete' WHERE athlete_profile_id=:a"),{"a":aid})
  with pytest.raises(Exception):command.downgrade(cfg,"0018_athlete_onboarding")
  with engine.begin() as c:c.execute(text("UPDATE user_athlete_memberships SET role='owner' WHERE athlete_profile_id=:a"),{"a":aid})
  command.downgrade(cfg,"0018_athlete_onboarding");engine.dispose()
