"""Validate the real overview GET and integrity auditor without syncing/writing."""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event,select,text
from app.api.dependencies.auth import AuthenticatedUser,get_current_user
from app.api.v1.routes.dashboard import router
from app.db.models import AthleteProfile,UserAthleteMembership
from app.db.session import SessionLocal,get_db_session
from scripts.audit_multi_athlete_integrity import audit


def validate(cutoff):
    result={"cutoff":cutoff.isoformat(),"athletes":[]}
    app=FastAPI();app.include_router(router)
    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
            assert db.scalar(text("SHOW transaction_read_only"))=="on"
            memberships=db.scalars(select(UserAthleteMembership).join(AthleteProfile).where(
                UserAthleteMembership.is_active.is_(True),AthleteProfile.deleted_at.is_(None))
                .order_by(UserAthleteMembership.athlete_profile_id,UserAthleteMembership.id)).all()
            app.dependency_overrides[get_db_session]=lambda:db
            seen=set()
            with TestClient(app) as client:
                for member in memberships:
                    if member.athlete_profile_id in seen:continue
                    seen.add(member.athlete_profile_id)
                    app.dependency_overrides[get_current_user]=lambda:AuthenticatedUser(id=member.user_id)
                    statements=[]
                    def track(connection,cursor,sql,*args):
                        assert sql.lstrip().upper().startswith("SELECT")
                        statements.append(sql)
                    event.listen(db.bind,"before_cursor_execute",track)
                    try:
                        response=client.get("/dashboard/execution-overview",params={"as_of_date":cutoff.isoformat()},
                            headers={"X-TriCoach-Athlete-Id":str(member.athlete_profile_id)})
                    finally:event.remove(db.bind,"before_cursor_execute",track)
                    assert response.status_code==200
                    data=response.json()
                    result["athletes"].append({"athlete_id":data["athlete_id"],"queries":len(statements),
                        "latest_activity_id":data["latest_activity"]["id"] if data["latest_activity"] else None,
                        "latest_activity_linked_sessions":len(data["latest_activity_sessions"]),
                        "recent_sessions":[{"id":row["id"],"status":row["evidence"]["completion_status"]}
                            for row in data["recent_sessions"]]})
            integrity=audit(db)
            result["integrity"]={"checks":len(integrity["checks"]),"issues":integrity["issue_count"]}
        finally:db.rollback()
    result.update(readonly=True,rollback=True)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff",required=True,type=date.fromisoformat)
    print(json.dumps(validate(parser.parse_args().cutoff),indent=2))
