"""Read actual Training Status through the overview route without recalculation."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app.api.dependencies.auth import AuthenticatedUser, get_current_user, LOCAL_MVP_USER_ID
from app.api.v1.routes.training_status import router
from app.db.models import AthleteProfile, UserAthleteMembership
from app.db.session import SessionLocal, get_db_session
from scripts.audit_multi_athlete_integrity import audit


def validate(cutoff):
    report = {"cutoff": cutoff.isoformat(), "athletes": [],
        "transport": "real training-status router through ASGI; existing membership identities supplied",
        "browser_selected_athlete": "not observable without browser"}
    app = FastAPI()
    app.include_router(router)
    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            members = db.execute(select(UserAthleteMembership, AthleteProfile).join(AthleteProfile,
                UserAthleteMembership.athlete_profile_id == AthleteProfile.id).where(
                UserAthleteMembership.is_active.is_(True), AthleteProfile.deleted_at.is_(None)
            ).order_by(AthleteProfile.id, UserAthleteMembership.id)).all()
            report["development_default_athlete"] = next((str(member.athlete_profile_id)
                for member, _ in members if member.user_id == LOCAL_MVP_USER_ID and member.is_default), None)
            def database(): yield db
            app.dependency_overrides[get_db_session] = database
            seen = set()
            with TestClient(app) as client:
                for member, athlete in members:
                    if athlete.id in seen: continue
                    seen.add(athlete.id)
                    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=member.user_id)
                    queries = []
                    def check(connection, cursor, sql, *args):
                        assert sql.lstrip().upper().startswith("SELECT")
                        queries.append(sql)
                    event.listen(db.bind, "before_cursor_execute", check)
                    try:
                        response = client.get("/training-status/overview", params={
                            "start_date": (cutoff-timedelta(days=27)).isoformat(), "end_date": cutoff.isoformat(),
                            "timezone_name": athlete.timezone}, headers={"X-TriCoach-Athlete-Id":str(athlete.id)})
                    finally:
                        event.remove(db.bind, "before_cursor_execute", check)
                    assert response.status_code == 200
                    report["athletes"].append({"athlete_id":str(athlete.id), "http_status":response.status_code,
                        "query_count":len(queries), "interpretation":response.json()["interpretation"]})
            integrity = audit(db)
            report["integrity"] = {"checks":len(integrity["checks"]), "issues":integrity["issue_count"]}
        finally:
            db.rollback()
    report.update(transaction_read_only=True, rollback=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", required=True, type=date.fromisoformat)
    print(json.dumps(validate(parser.parse_args().cutoff), indent=2, sort_keys=True))
