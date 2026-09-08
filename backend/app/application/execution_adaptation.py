from __future__ import annotations

from datetime import date

from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.domains.planning.execution_adaptation import build_execution_adaptation_context


class ExecutionAdaptationContextAssembler:
    """Interpret C.1 evidence in memory; it never mutates planning or persistence."""

    def __init__(self, session):
        self.evidence = PrescribedCompletedEvidenceAssembler(session)

    def assemble(self, *, athlete_profile_id, as_of_date: date):
        evidence = self.evidence.assemble(
            athlete_profile_id=athlete_profile_id,
            as_of_date=as_of_date,
        )
        return build_execution_adaptation_context(evidence)
