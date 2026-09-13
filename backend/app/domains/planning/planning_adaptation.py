from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from app.domains.planning.contracts import (
    FrozenModel, PlanningAdaptationInput, PlanningAdaptationItem, PlanningContext,
    context_fingerprint,
)
from app.domains.planning.execution_proposals import (
    AdaptationProposal, ExecutionAdaptationProposalContext, ProposalDirection,
    ProposalKind,
)
from app.domains.planning.models import WorkoutTarget, WorkoutTargetPlanningAdaptation


PLANNING_ADAPTATION_VERSION = "0.8G.2C.4"


class PlanningAdaptationDecisionStatus(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_CHANGE = "NO_CHANGE"
    APPLIED = "APPLIED"
    SKIPPED_LOW_CONFIDENCE = "SKIPPED_LOW_CONFIDENCE"
    SKIPPED_NO_SAFE_STEP = "SKIPPED_NO_SAFE_STEP"
    SKIPPED_GUARD = "SKIPPED_GUARD"
    SKIPPED_CONFLICT = "SKIPPED_CONFLICT"


class PlanningAdaptationDecisionReason(StrEnum):
    SOURCE_NO_CHANGE = "SOURCE_NO_CHANGE"
    SOURCE_NOT_ACTIONABLE = "SOURCE_NOT_ACTIONABLE"
    LOW_PROPOSAL_CONFIDENCE = "LOW_PROPOSAL_CONFIDENCE"
    NUMERIC_RANGE_UNAVAILABLE = "NUMERIC_RANGE_UNAVAILABLE"
    PROPOSAL_GUARD_PRESENT = "PROPOSAL_GUARD_PRESENT"
    CONFLICTING_PROPOSALS = "CONFLICTING_PROPOSALS"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    CURRENT_TARGET_MISMATCH = "CURRENT_TARGET_MISMATCH"
    TARGET_APPLIED = "TARGET_APPLIED"


class PlanningAdaptationDecision(FrozenModel):
    sport: str | None = None
    session_type: str | None = None
    target_kind: str | None = None
    source_proposal: ProposalKind
    direction: ProposalDirection
    confidence: str
    status: PlanningAdaptationDecisionStatus
    reason: PlanningAdaptationDecisionReason
    before_minimum: Decimal | None = Field(default=None, gt=0)
    before_maximum: Decimal | None = Field(default=None, gt=0)
    after_minimum: Decimal | None = Field(default=None, gt=0)
    after_maximum: Decimal | None = Field(default=None, gt=0)
    proposal_version: str


class PlanningAdaptationProjection(FrozenModel):
    planning_input: PlanningAdaptationInput | None = None
    decisions: tuple[PlanningAdaptationDecision, ...] = ()


class PlanningAdaptationAthleteMismatchError(ValueError):
    pass


class PlanningAdaptationCutoffMismatchError(ValueError):
    pass


def normalize_numeric_planning_adaptation(resolutions) -> PlanningAdaptationProjection:
    """Project C.5 results without calculating targets or reinterpreting evidence."""
    from app.domains.planning.numeric_adaptation import project_resolved_adaptations

    statuses = {
        "NO_SAFE_STEP": (PlanningAdaptationDecisionStatus.SKIPPED_NO_SAFE_STEP, PlanningAdaptationDecisionReason.NUMERIC_RANGE_UNAVAILABLE),
        "NOT_APPLICABLE": (PlanningAdaptationDecisionStatus.NOT_APPLICABLE, PlanningAdaptationDecisionReason.SOURCE_NOT_ACTIONABLE),
        "GUARDED": (PlanningAdaptationDecisionStatus.SKIPPED_GUARD, PlanningAdaptationDecisionReason.PROPOSAL_GUARD_PRESENT),
        "UNSUPPORTED": (PlanningAdaptationDecisionStatus.SKIPPED_GUARD, PlanningAdaptationDecisionReason.PROPOSAL_GUARD_PRESENT),
        "CONFLICT": (PlanningAdaptationDecisionStatus.SKIPPED_CONFLICT, PlanningAdaptationDecisionReason.CONFLICTING_PROPOSALS),
    }
    decisions = []
    for item in resolutions.resolutions:
        if item.status == "RESOLVED":
            continue  # Only target application can report APPLIED.
        status, reason = statuses[item.status]
        if "LOW_CONFIDENCE" in item.reason_codes:
            status = PlanningAdaptationDecisionStatus.SKIPPED_LOW_CONFIDENCE
            reason = PlanningAdaptationDecisionReason.LOW_PROPOSAL_CONFIDENCE
        decisions.append(PlanningAdaptationDecision(
            sport=item.sport, session_type=item.session_type, target_kind=item.target_kind,
            source_proposal=item.source_proposal_kind, direction=item.direction,
            confidence=item.confidence.value, status=status, reason=reason,
            before_minimum=item.current_range.minimum if item.current_range else None,
            before_maximum=item.current_range.maximum if item.current_range else None,
            proposal_version=item.source_proposal_version,
        ))
    return PlanningAdaptationProjection(
        planning_input=project_resolved_adaptations(resolutions), decisions=tuple(decisions),
    )


def _decision(proposal: AdaptationProposal, status, reason, *, proposal_version: str) -> PlanningAdaptationDecision:
    return PlanningAdaptationDecision(
        sport=proposal.sport, session_type=proposal.session_type,
        target_kind=proposal.target_kind, source_proposal=proposal.proposal_kind,
        direction=proposal.proposed_direction, confidence=proposal.confidence.value,
        status=status, reason=reason, proposal_version=proposal_version,
    )


def _semantic_signature(proposal: AdaptationProposal):
    current = proposal.current_prescription
    proposed = proposal.proposed_range
    return (
        proposal.proposal_kind.value, proposal.proposed_direction.value,
        proposal.confidence.value,
        None if current is None else (current.minimum, current.maximum, current.unit),
        None if proposed is None else (proposed.minimum, proposed.maximum, proposed.unit),
        tuple(item.value for item in proposal.applied_guards),
    )


def normalize_planning_adaptation(*, proposals: ExecutionAdaptationProposalContext, athlete_id, cutoff_date) -> PlanningAdaptationProjection:
    if proposals.athlete_profile_id != athlete_id:
        raise PlanningAdaptationAthleteMismatchError("proposal context athlete does not match planning athlete")
    if proposals.as_of_date != cutoff_date:
        raise PlanningAdaptationCutoffMismatchError("proposal cutoff does not match planning cutoff")
    grouped = defaultdict(list)
    for proposal in proposals.proposals:
        grouped[(proposal.sport or "", proposal.session_type or "", proposal.target_kind or "")].append(proposal)
    decisions = []
    items = []
    for key, group in sorted(grouped.items()):
        unique = {_semantic_signature(item) for item in group}
        if len(unique) > 1:
            decisions.extend(_decision(item, PlanningAdaptationDecisionStatus.SKIPPED_CONFLICT, PlanningAdaptationDecisionReason.CONFLICTING_PROPOSALS, proposal_version=proposals.algorithm_version) for item in sorted(group, key=lambda value: repr(_semantic_signature(value))))
            continue
        proposal = group[0]
        if proposal.proposal_kind == ProposalKind.NO_CHANGE:
            decisions.append(_decision(proposal, PlanningAdaptationDecisionStatus.NO_CHANGE, PlanningAdaptationDecisionReason.SOURCE_NO_CHANGE, proposal_version=proposals.algorithm_version)); continue
        if proposal.proposal_kind in {ProposalKind.INSUFFICIENT_EVIDENCE, ProposalKind.REVIEW_EXECUTION}:
            decisions.append(_decision(proposal, PlanningAdaptationDecisionStatus.NOT_APPLICABLE, PlanningAdaptationDecisionReason.SOURCE_NOT_ACTIONABLE, proposal_version=proposals.algorithm_version)); continue
        if proposal.confidence.value not in {"HIGH", "MEDIUM"}:
            decisions.append(_decision(proposal, PlanningAdaptationDecisionStatus.SKIPPED_LOW_CONFIDENCE, PlanningAdaptationDecisionReason.LOW_PROPOSAL_CONFIDENCE, proposal_version=proposals.algorithm_version)); continue
        if proposal.applied_guards:
            no_step = proposal.current_prescription is None or proposal.proposed_range is None
            status = PlanningAdaptationDecisionStatus.SKIPPED_NO_SAFE_STEP if no_step else PlanningAdaptationDecisionStatus.SKIPPED_GUARD
            reason = PlanningAdaptationDecisionReason.NUMERIC_RANGE_UNAVAILABLE if no_step else PlanningAdaptationDecisionReason.PROPOSAL_GUARD_PRESENT
            decisions.append(_decision(proposal, status, reason, proposal_version=proposals.algorithm_version)); continue
        current = proposal.current_prescription
        proposed = proposal.proposed_range
        if current is None or proposed is None:
            decisions.append(_decision(proposal, PlanningAdaptationDecisionStatus.SKIPPED_NO_SAFE_STEP, PlanningAdaptationDecisionReason.NUMERIC_RANGE_UNAVAILABLE, proposal_version=proposals.algorithm_version)); continue
        try:
            items.append(PlanningAdaptationItem(
                proposal_version=proposals.algorithm_version, cutoff_date=cutoff_date,
                sport=proposal.sport, session_type=proposal.session_type,
                target_kind=proposal.target_kind, proposal_kind=proposal.proposal_kind.value,
                direction=proposal.proposed_direction.value, confidence=proposal.confidence.value,
                current_minimum=Decimal(str(current.minimum)), current_maximum=Decimal(str(current.maximum)),
                proposed_minimum=Decimal(str(proposed.minimum)), proposed_maximum=Decimal(str(proposed.maximum)),
                unit=proposed.unit,
            ))
        except (TypeError, ValueError):
            decisions.append(_decision(proposal, PlanningAdaptationDecisionStatus.SKIPPED_GUARD, PlanningAdaptationDecisionReason.PROPOSAL_GUARD_PRESENT, proposal_version=proposals.algorithm_version))
    items.sort(key=lambda item: (item.sport, item.session_type, item.target_kind))
    planning_input = PlanningAdaptationInput(
        athlete_id=athlete_id, proposal_version=proposals.algorithm_version,
        cutoff_date=cutoff_date, items=tuple(items),
    ) if items else None
    decisions.sort(key=lambda item: (item.sport or "", item.session_type or "", item.target_kind or "", item.status.value, item.source_proposal.value))
    return PlanningAdaptationProjection(planning_input=planning_input, decisions=tuple(decisions))


def with_planning_adaptation(context: PlanningContext, adaptation: PlanningAdaptationInput | None) -> PlanningContext:
    if adaptation is None:
        return context
    if adaptation.athlete_id != context.request.athlete_id:
        raise PlanningAdaptationAthleteMismatchError("planning adaptation athlete does not match context")
    if adaptation.cutoff_date != context.request.planning_date:
        raise PlanningAdaptationCutoffMismatchError("planning adaptation cutoff does not match context")
    payload = context.model_dump(mode="python", exclude={"fingerprint", "planning_adaptation"})
    payload["planning_adaptation"] = adaptation
    return PlanningContext(**payload, fingerprint=context_fingerprint(payload))


def apply_planning_adaptation(*, target: WorkoutTarget, context: PlanningContext, sport: str, session_type: str, target_kind: str):
    adaptation = context.planning_adaptation
    item = None if adaptation is None else next((row for row in adaptation.items if (row.sport, row.session_type, row.target_kind) == (sport, session_type, target_kind)), None)
    if item is None:
        return target, None
    before_min = Decimal(str(target.resolved_minimum)) if target.resolved_minimum is not None else None
    before_max = Decimal(str(target.resolved_maximum)) if target.resolved_maximum is not None else None
    if before_min != item.current_minimum or before_max != item.current_maximum or target.resolved_unit != item.unit:
        return target, PlanningAdaptationDecision(
            sport=sport, session_type=session_type, target_kind=target_kind,
            source_proposal=ProposalKind(item.proposal_kind), direction=ProposalDirection(item.direction),
            confidence=item.confidence, status=PlanningAdaptationDecisionStatus.SKIPPED_GUARD,
            reason=PlanningAdaptationDecisionReason.CURRENT_TARGET_MISMATCH,
            before_minimum=before_min, before_maximum=before_max,
            proposal_version=item.proposal_version,
        )
    metadata = WorkoutTargetPlanningAdaptation(
        proposal_version=item.proposal_version, numeric_policy_version=item.numeric_policy_version,
        proposal_kind=item.proposal_kind,
        direction=item.direction, confidence=item.confidence,
        before_minimum=float(before_min), before_maximum=float(before_max),
        after_minimum=float(item.proposed_minimum), after_maximum=float(item.proposed_maximum),
    )
    updated = target.model_copy(update={
        "resolved_minimum": float(item.proposed_minimum),
        "resolved_maximum": float(item.proposed_maximum),
        "planning_adaptation": metadata,
    })
    return updated, PlanningAdaptationDecision(
        sport=sport, session_type=session_type, target_kind=target_kind,
        source_proposal=ProposalKind(item.proposal_kind), direction=ProposalDirection(item.direction),
        confidence=item.confidence, status=PlanningAdaptationDecisionStatus.APPLIED,
        reason=PlanningAdaptationDecisionReason.TARGET_APPLIED,
        before_minimum=before_min, before_maximum=before_max,
        after_minimum=item.proposed_minimum, after_maximum=item.proposed_maximum,
        proposal_version=item.proposal_version,
    )
