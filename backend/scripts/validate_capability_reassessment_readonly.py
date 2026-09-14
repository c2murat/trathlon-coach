"""Validate C.1 -> C.2 -> C.7 against real data in a read-only transaction."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import event, select, text

from app.application.capability_reassessment import CapabilityReassessmentAssembler
from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.db.models import AthleteProfile
from app.db.session import SessionLocal
from app.domains.capability.reassessment import CAPABILITY_REASSESSMENT_VERSION
from app.domains.planning.execution_adaptation import build_execution_adaptation_context
from scripts.audit_multi_athlete_integrity import audit


def validate(cutoff):
    report = {"version": CAPABILITY_REASSESSMENT_VERSION, "cutoff": cutoff.isoformat(),
              "window_start": (cutoff-timedelta(days=84)).isoformat(), "athletes": []}
    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            report["transaction_read_only"] = True
            athletes = db.scalars(select(AthleteProfile).where(AthleteProfile.deleted_at.is_(None))
                                  .order_by(AthleteProfile.id)).all()
            for athlete in athletes:
                queries = []
                def count(*args): queries.append(args[2])
                event.listen(db.bind, "before_cursor_execute", count)
                try:
                    evidence = PrescribedCompletedEvidenceAssembler(db).assemble(
                        athlete_profile_id=athlete.id, as_of_date=cutoff)
                    c1_queries = len(queries)
                    adaptation = build_execution_adaptation_context(evidence)
                    assert len(queries) == c1_queries <= 3
                    result = CapabilityReassessmentAssembler(db).assemble(athlete_profile_id=athlete.id,
                        as_of_date=cutoff, evidence=evidence, adaptation=adaptation)
                    assert len(queries)-c1_queries == 1
                    assert all(sql.lstrip().upper().startswith("SELECT") for sql in queries)
                finally:
                    event.remove(db.bind, "before_cursor_execute", count)
                report["athletes"].append({"athlete_id": str(athlete.id), "sessions": len(evidence.sessions),
                    "evaluable_sessions": adaptation.global_summary.evaluable_sessions,
                    "c1_queries": c1_queries, "c2_queries": 0, "c7_queries": len(queries)-c1_queries,
                    "candidate_count": result.summary.candidate_count,
                    "capabilities": [{"kind": item.capability_kind.value,
                        "reference_available": item.current_reference is not None,
                        "status": item.status.value, "confidence": item.confidence.value,
                        "reason_codes": [reason.value for reason in item.reason_codes],
                        "evidence": item.evidence.model_dump(mode="json")} for item in result.candidates]})
            integrity = audit(db)
            report["multiathlete_integrity"] = {"issue_count": integrity["issue_count"],
                "checks": {key: len(value) for key, value in integrity["checks"].items()}}
        finally:
            db.rollback()
    report["rollback"] = True
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    print(json.dumps(validate(parser.parse_args().cutoff), sort_keys=True, indent=2))
