from __future__ import annotations

from datetime import date

from app.application.execution_adaptation import ExecutionAdaptationContextAssembler
from app.domains.planning.execution_proposals import build_execution_adaptation_proposal_context


class ExecutionAdaptationProposalAssembler:
    """Build direction-only proposals from C.2 without querying or mutating planning."""

    def __init__(self, session):
        self.adaptation = ExecutionAdaptationContextAssembler(session)

    def assemble(self, *, athlete_profile_id, as_of_date: date):
        adaptation = self.adaptation.assemble(
            athlete_profile_id=athlete_profile_id,
            as_of_date=as_of_date,
        )
        return build_execution_adaptation_proposal_context(
            adaptation,
            athlete_profile_id=athlete_profile_id,
        )
