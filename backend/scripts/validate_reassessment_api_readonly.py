"""Real ASGI endpoint and DB validation without creating login sessions or data.

Only authentication identity is supplied by this harness, using existing active
memberships. Athlete selection, authorization, C.7 and response serialization
run normally. Every DB statement runs in a READ ONLY transaction, rolled back.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import event, select, text

from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.db.models import AthleteProfile, UserAthleteMembership
from app.db.session import SessionLocal, get_db_session
from app.main import create_app
from scripts.audit_multi_athlete_integrity import audit


def validate(cutoff):
    report = {"cutoff": cutoff.isoformat(), "transport": "real ASGI routes via TestClient",
              "authentication": "existing membership identities supplied by read-only harness", "athletes": []}
    app = create_app()
    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            report["transaction_read_only"] = True
            members = db.scalars(select(UserAthleteMembership).join(AthleteProfile,
                AthleteProfile.id == UserAthleteMembership.athlete_profile_id).where(
                UserAthleteMembership.is_active.is_(True), AthleteProfile.deleted_at.is_(None)
            ).order_by(UserAthleteMembership.athlete_profile_id, UserAthleteMembership.id)).all()
            def database(): yield db
            app.dependency_overrides[get_db_session] = database
            seen = set()
            with TestClient(app) as client:
                for member in members:
                    if member.athlete_profile_id in seen:
                        continue
                    seen.add(member.athlete_profile_id)
                    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=member.user_id)
                    queries = []
                    def check(connection, cursor, sql, *args):
                        assert sql.lstrip().upper().startswith("SELECT"), "unexpected non-read SQL"
                        queries.append(sql)
                    event.listen(db.bind, "before_cursor_execute", check)
                    try:
                        response = client.get("/athlete/performance-profile/reassessment",
                            params={"as_of_date": cutoff.isoformat()},
                            headers={"X-TriCoach-Athlete-Id": str(member.athlete_profile_id)})
                    finally:
                        event.remove(db.bind, "before_cursor_execute", check)
                    assert response.status_code == 200
                    data = response.json()
                    assert data["athlete_profile_id"] == str(member.athlete_profile_id)
                    report["athletes"].append({"athlete_id": data["athlete_profile_id"],
                        "http_status": response.status_code, "query_count": len(queries),
                        "candidate_count": data["summary"]["candidate_count"], "sessions": data["summary"]["session_count"],
                        "capabilities": [{"kind": item["capability_kind"], "status": item["status"],
                            "reference_present": item["current_reference"] is not None,
                            "confidence": item["confidence"]} for item in data["candidates"]]})
            integrity = audit(db)
            report["integrity"] = {"checks": len(integrity["checks"]), "issues": integrity["issue_count"]}
        finally:
            app.dependency_overrides.clear()
            db.rollback()
    report["rollback"] = True
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    print(json.dumps(validate(parser.parse_args().cutoff), indent=2, sort_keys=True))
