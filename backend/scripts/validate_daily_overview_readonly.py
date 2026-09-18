"""Read real daily overviews through the authorized GET, without sync or writes."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from app.api.dependencies.auth import AuthenticatedUser, get_current_user
from app.api.v1.routes.dashboard import router
from app.db.models import AthleteProfile, UserAthleteMembership
from app.db.session import SessionLocal, get_db_session


def validate():
    result = []
    app = FastAPI()
    app.include_router(router)
    with SessionLocal() as session:
        try:
            session.execute(text("SET TRANSACTION READ ONLY"))
            memberships = session.scalars(select(UserAthleteMembership).join(AthleteProfile).where(
                UserAthleteMembership.is_active.is_(True), AthleteProfile.deleted_at.is_(None))
                .order_by(UserAthleteMembership.athlete_profile_id, UserAthleteMembership.id)).all()
            app.dependency_overrides[get_db_session] = lambda: session
            seen = set()
            with TestClient(app) as client:
                for member in memberships:
                    if member.athlete_profile_id in seen:
                        continue
                    seen.add(member.athlete_profile_id)
                    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=member.user_id)
                    statements = []
                    def track(connection, cursor, sql, *args):
                        assert sql.lstrip().upper().startswith("SELECT")
                        statements.append(sql)
                    event.listen(session.bind, "before_cursor_execute", track)
                    try:
                        response = client.get("/dashboard/daily-overview", headers={
                            "X-TriCoach-Athlete-Id": str(member.athlete_profile_id)})
                    finally:
                        event.remove(session.bind, "before_cursor_execute", track)
                    assert response.status_code == 200, response.text
                    data = response.json()
                    assert data["athlete_id"] == str(member.athlete_profile_id)
                    assert data["as_of_date"] == data["interpretation"]["as_of_date"] == data["execution"]["as_of_date"]
                    result.append({"athlete_id":data["athlete_id"], "selects":len(statements),
                        "as_of_date":data["as_of_date"], "timezone":data["timezone"],
                        "state":data["interpretation"]["overall_state"],
                        "fitness":data["interpretation"]["fitness"], "fatigue":data["interpretation"]["fatigue"],
                        "form":data["interpretation"]["form"], "today":data["today_sessions"],
                        "next_session":data["next_session"], "next_goal":data["next_goal"],
                        "latest_activity":data["execution"]["latest_activity"],
                        "consistency_last_activity_at":data["consistency"]["last_activity_at"],
                        "recent_statuses":[x["evidence"]["completion_status"] for x in data["execution"]["recent_sessions"]]})
        finally:
            session.rollback()
    return {"readonly":True, "athletes":result}


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
