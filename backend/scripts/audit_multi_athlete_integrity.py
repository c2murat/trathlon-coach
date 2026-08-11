from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, inspect, select, text

BACKEND_ROOT=Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:sys.path.insert(0,str(BACKEND_ROOT))

from app.db.models import (AthleteDailyTrainingLoad,AthleteProfile,AthleteWeeklyTrainingLoad,CompletedActivity,IntegrationAccount,OAuthCredential,SyncJob,User,UserAthleteMembership)
from app.db.session import SessionLocal


CHECK_NAMES=("duplicate_active_accounts","activity_tenant_mismatch","job_tenant_mismatch","orphan_credentials","orphan_activity_accounts","orphan_job_accounts","aggregate_missing_activity","aggregate_tenant_mismatch","aggregate_duplicate_activity","users_without_memberships","athletes_without_memberships","athletes_without_active_owner","multiple_active_defaults","inactive_defaults","deleted_athlete_defaults","active_memberships_deleted_athlete","invalid_athlete_display_names","legacy_athlete_user_id_present","active_strava_without_credential","invalid_job_minimums")


def audit(session,*,athlete_id:UUID|None=None)->dict:
    issues={name:[] for name in CHECK_NAMES}
    accounts=list(session.scalars(select(IntegrationAccount).where(IntegrationAccount.athlete_id==athlete_id) if athlete_id else select(IntegrationAccount)).all());account_by_id={x.id:x for x in accounts}
    active=Counter((x.athlete_id,x.provider) for x in accounts if x.status=="active" and x.deleted_at is None)
    issues["duplicate_active_accounts"]=[{"athlete_id":str(a),"provider":p,"count":n} for (a,p),n in active.items() if n>1]
    activities=list(session.scalars(select(CompletedActivity).where(CompletedActivity.athlete_id==athlete_id) if athlete_id else select(CompletedActivity)).all());activity_by_id={x.id:x for x in activities}
    for row in activities:
        if row.source_integration_account_id is not None:
            account=session.get(IntegrationAccount,row.source_integration_account_id)
            if account is None:issues["orphan_activity_accounts"].append({"activity_id":str(row.id)})
            elif account.athlete_id!=row.athlete_id:issues["activity_tenant_mismatch"].append({"activity_id":str(row.id)})
    jobs=list(session.scalars(select(SyncJob).where(SyncJob.athlete_id==athlete_id) if athlete_id else select(SyncJob)).all())
    for row in jobs:
        account=session.get(IntegrationAccount,row.integration_account_id)
        if account is None:issues["orphan_job_accounts"].append({"job_id":str(row.id)})
        elif account.athlete_id!=row.athlete_id:issues["job_tenant_mismatch"].append({"job_id":str(row.id)})
        if not row.job_type or not row.idempotency_key:issues["invalid_job_minimums"].append({"job_id":str(row.id)})
    credentials=list(session.scalars(select(OAuthCredential)).all())
    for row in credentials:
        if session.get(IntegrationAccount,row.integration_account_id) is None:issues["orphan_credentials"].append({"credential_id":str(row.id)})
    aggregates=[]
    for model in (AthleteDailyTrainingLoad,AthleteWeeklyTrainingLoad):
        statement=select(model).where(model.athlete_profile_id==athlete_id) if athlete_id else select(model);aggregates.extend(session.scalars(statement).all())
    for row in aggregates:
        ids=[UUID(str(value)) for value in row.activity_ids]
        if len(ids)!=len(set(ids)):issues["aggregate_duplicate_activity"].append({"aggregate_id":str(row.id)})
        for value in set(ids):
            activity=session.get(CompletedActivity,value)
            if activity is None:issues["aggregate_missing_activity"].append({"aggregate_id":str(row.id),"activity_id":str(value)})
            elif activity.athlete_id!=row.athlete_profile_id:issues["aggregate_tenant_mismatch"].append({"aggregate_id":str(row.id),"activity_id":str(value)})
    if athlete_id is None:
        for user in session.scalars(select(User)).all():
            if not session.scalar(select(UserAthleteMembership.id).where(UserAthleteMembership.user_id==user.id,UserAthleteMembership.is_active.is_(True))):issues["users_without_memberships"].append({"user_id":str(user.id)})
        athlete_ids=[row[0] for row in session.execute(text("SELECT id FROM athlete_profiles ORDER BY id"))]
        for athlete_id_value in athlete_ids:
            if not session.scalar(select(UserAthleteMembership.id).where(UserAthleteMembership.athlete_profile_id==athlete_id_value,UserAthleteMembership.is_active.is_(True))):issues["athletes_without_memberships"].append({"athlete_id":str(athlete_id_value)})
        defaults=session.execute(select(UserAthleteMembership.user_id,func.count()).where(UserAthleteMembership.is_active.is_(True),UserAthleteMembership.is_default.is_(True)).group_by(UserAthleteMembership.user_id).having(func.count()>1)).all();issues["multiple_active_defaults"]=[{"user_id":str(x),"count":n} for x,n in defaults]
        issues["athletes_without_active_owner"]=[{"athlete_id":str(row[0])} for row in session.execute(text("SELECT a.id FROM athlete_profiles a WHERE NOT EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.athlete_profile_id=a.id AND m.role='owner' AND m.is_active IS TRUE) ORDER BY a.id"))]
        issues["inactive_defaults"]=[{"membership_id":str(row[0])} for row in session.execute(text("SELECT id FROM user_athlete_memberships WHERE is_active IS FALSE AND is_default IS TRUE ORDER BY id"))]
        issues["deleted_athlete_defaults"]=[{"membership_id":str(row[0])} for row in session.execute(text("SELECT m.id FROM user_athlete_memberships m JOIN athlete_profiles a ON a.id=m.athlete_profile_id WHERE m.is_default IS TRUE AND a.deleted_at IS NOT NULL ORDER BY m.id"))]
        issues["active_memberships_deleted_athlete"]=[{"membership_id":str(row[0])} for row in session.execute(text("SELECT m.id FROM user_athlete_memberships m JOIN athlete_profiles a ON a.id=m.athlete_profile_id WHERE m.is_active IS TRUE AND a.deleted_at IS NOT NULL ORDER BY m.id"))]
        columns={column["name"] for column in inspect(session.bind).get_columns("athlete_profiles")}
        if "display_name" in columns: issues["invalid_athlete_display_names"]=[{"athlete_id":str(row[0])} for row in session.execute(text("SELECT id FROM athlete_profiles WHERE display_name IS NULL OR char_length(btrim(display_name)) NOT BETWEEN 1 AND 200 ORDER BY id"))]
        issues["legacy_athlete_user_id_present"]=[]
    credential_accounts={x.integration_account_id for x in credentials};issues["active_strava_without_credential"]=[{"account_id":str(x.id)} for x in accounts if x.provider=="strava" and x.status=="active" and x.id not in credential_accounts]
    return {"scope":{"athlete_id":str(athlete_id) if athlete_id else None,"all_athletes":athlete_id is None},"issue_count":sum(map(len,issues.values())),"checks":issues}


def build_parser():
    parser=argparse.ArgumentParser(description="Auditoría de integridad multiatleta de solo lectura");scope=parser.add_mutually_exclusive_group(required=True);scope.add_argument("--athlete-id",type=UUID);scope.add_argument("--all-athletes",action="store_true");parser.add_argument("--format",choices=("text","json"),default="text");return parser


def main(argv=None):
    try:args=build_parser().parse_args(argv)
    except SystemExit as error:return int(error.code)
    try:
        with SessionLocal() as session:
            result=audit(session,athlete_id=args.athlete_id);session.rollback()
        if args.format=="json":print(json.dumps(result,sort_keys=True,separators=(",",":")))
        else:
            print(f"Alcance: {result['scope']}");print(f"Errores de integridad: {result['issue_count']}")
            for name,rows in result["checks"].items():print(f"{name}: {len(rows)}")
        return 1 if result["issue_count"] else 0
    except Exception as error:
        print(f"Error de auditoría: {type(error).__name__}: {error}",file=sys.stderr);return 3


if __name__=="__main__":raise SystemExit(main())
