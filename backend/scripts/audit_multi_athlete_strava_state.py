from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

BACKEND_ROOT=Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:sys.path.insert(0,str(BACKEND_ROOT))

from app.db.session import SessionLocal

COUNT_COLUMNS=(
    "integration_accounts","active_strava_accounts","oauth_credentials","sync_jobs",
    "completed_activities","strava_activities","activity_training_loads",
    "daily_training_loads","weekly_training_loads","manual_strength_sessions",
    "performance_profile_versions","performance_references","training_status_rows",
)
CHECK_NAMES=(
    "credential_without_account","job_account_athlete_mismatch",
    "activity_account_athlete_mismatch","load_activity_athlete_mismatch",
    "daily_aggregate_activity_mismatch","weekly_aggregate_activity_mismatch",
    "integration_account_deleted_athlete","duplicate_strava_external_identity",
)

def _count(session,sql:str,athlete_id:UUID)->int:
    value=athlete_id.hex if session.bind.dialect.name=="sqlite" else str(athlete_id)
    return int(session.execute(text(sql),{"athlete_id":value}).scalar_one())

def audit(session,*,all_athletes:bool=False,athlete_id:UUID|None=None)->dict:
    if all_athletes==(athlete_id is not None):raise ValueError("select exactly one scope")
    where="WHERE a.id=:athlete_id" if athlete_id else ""
    scope_value=(athlete_id.hex if session.bind.dialect.name=="sqlite" else str(athlete_id)) if athlete_id else None
    athletes=session.execute(text(f"SELECT a.id,a.display_name FROM athlete_profiles a {where} ORDER BY a.display_name,a.id"),{"athlete_id":scope_value}).all()
    rows=[]
    for raw_id,name in athletes:
        aid=UUID(str(raw_id));counts={
            "integration_accounts":_count(session,"SELECT count(*) FROM integration_accounts WHERE athlete_id=:athlete_id",aid),
            "active_strava_accounts":_count(session,"SELECT count(*) FROM integration_accounts WHERE athlete_id=:athlete_id AND provider='strava' AND status='active' AND deleted_at IS NULL",aid),
            "oauth_credentials":_count(session,"SELECT count(*) FROM oauth_credentials c JOIN integration_accounts i ON i.id=c.integration_account_id WHERE i.athlete_id=:athlete_id",aid),
            "sync_jobs":_count(session,"SELECT count(*) FROM sync_jobs WHERE athlete_id=:athlete_id",aid),
            "completed_activities":_count(session,"SELECT count(*) FROM completed_activities WHERE athlete_id=:athlete_id AND deleted_at IS NULL",aid),
            "strava_activities":_count(session,"SELECT count(*) FROM completed_activities WHERE athlete_id=:athlete_id AND source_summary='strava' AND deleted_at IS NULL",aid),
            "activity_training_loads":_count(session,"SELECT count(*) FROM activity_training_loads l JOIN completed_activities a ON a.id=l.completed_activity_id WHERE a.athlete_id=:athlete_id",aid),
            "daily_training_loads":_count(session,"SELECT count(*) FROM athlete_daily_training_loads WHERE athlete_profile_id=:athlete_id",aid),
            "weekly_training_loads":_count(session,"SELECT count(*) FROM athlete_weekly_training_loads WHERE athlete_profile_id=:athlete_id",aid),
            "manual_strength_sessions":_count(session,"SELECT count(*) FROM manual_strength_sessions WHERE athlete_id=:athlete_id",aid),
            "performance_profile_versions":_count(session,"SELECT count(*) FROM athlete_performance_profile_versions WHERE athlete_profile_id=:athlete_id",aid),
            "performance_references":_count(session,"SELECT count(*) FROM athlete_performance_references WHERE athlete_profile_id=:athlete_id",aid),
            "training_status_rows":_count(session,"SELECT count(*) FROM athlete_daily_training_statuses WHERE athlete_profile_id=:athlete_id",aid),
        };rows.append({"athlete_id":str(aid),"display_name":name,**counts})
    checks={name:[] for name in CHECK_NAMES}
    queries={
        "credential_without_account":"SELECT c.id FROM oauth_credentials c LEFT JOIN integration_accounts i ON i.id=c.integration_account_id WHERE i.id IS NULL",
        "job_account_athlete_mismatch":"SELECT j.id FROM sync_jobs j JOIN integration_accounts i ON i.id=j.integration_account_id WHERE j.athlete_id<>i.athlete_id",
        "activity_account_athlete_mismatch":"SELECT c.id FROM completed_activities c JOIN integration_accounts i ON i.id=c.source_integration_account_id WHERE c.athlete_id<>i.athlete_id",
        "load_activity_athlete_mismatch":"SELECT l.id FROM activity_training_loads l JOIN completed_activities c ON c.id=l.completed_activity_id JOIN integration_accounts i ON i.id=c.source_integration_account_id WHERE c.athlete_id<>i.athlete_id",
        "integration_account_deleted_athlete":"SELECT i.id FROM integration_accounts i JOIN athlete_profiles a ON a.id=i.athlete_id WHERE a.deleted_at IS NOT NULL",
        "duplicate_strava_external_identity":"SELECT min(CAST(i.id AS VARCHAR)) FROM integration_accounts i WHERE i.provider='strava' GROUP BY i.external_account_id HAVING count(DISTINCT i.athlete_id)>1",
    }
    for name,sql in queries.items():checks[name]=[{"row_id":str(UUID(str(row[0])))} for row in session.execute(text(sql))]
    for aggregate,table in (("daily","athlete_daily_training_loads"),("weekly","athlete_weekly_training_loads")):
        key=f"{aggregate}_aggregate_activity_mismatch";bad=[]
        for aggregate_id,owner,activity_ids in session.execute(text(f"SELECT id,athlete_profile_id,activity_ids FROM {table}")):
            values=activity_ids if isinstance(activity_ids,list) else json.loads(activity_ids or "[]")
            for value in values:
                activity_owner=session.execute(text("SELECT athlete_id FROM completed_activities WHERE id=:id"),{"id":str(value)}).scalar_one_or_none()
                if activity_owner is None or UUID(str(activity_owner))!=UUID(str(owner)):bad.append({"row_id":str(UUID(str(aggregate_id)))}) ;break
        checks[key]=bad
    identities=session.execute(text("SELECT count(DISTINCT external_account_id) FROM integration_accounts WHERE provider='strava' AND deleted_at IS NULL")).scalar_one()
    return {"scope":{"all_athletes":all_athletes,"athlete_id":str(athlete_id) if athlete_id else None},"athletes":rows,"strava":{"accounts":sum(row["active_strava_accounts"] for row in rows),"distinct_external_identities":int(identities)},"issue_count":sum(len(value) for value in checks.values()),"checks":checks}

def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only multi-athlete Strava state audit");scope=parser.add_mutually_exclusive_group(required=True);scope.add_argument("--all-athletes",action="store_true");scope.add_argument("--athlete-id",type=UUID);parser.add_argument("--format",choices=("json","text"),default="text");args=parser.parse_args(argv)
    with SessionLocal() as session:result=audit(session,all_athletes=args.all_athletes,athlete_id=args.athlete_id);session.rollback()
    if args.format=="json":print(json.dumps(result,sort_keys=True,separators=(",",":")))
    else:
        print(f"Athletes: {len(result['athletes'])}; Strava accounts: {result['strava']['accounts']}; issues: {result['issue_count']}")
        for row in result["athletes"]:print(f"{row['display_name']}: "+", ".join(f"{key}={row[key]}" for key in COUNT_COLUMNS))
    return 1 if result["issue_count"] else 0

if __name__=="__main__":raise SystemExit(main())
