from __future__ import annotations

from collections import Counter
from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.planning.execution_adaptation import (
    AdaptationMetrics, AdaptationReasonCode, AdaptationSignal,
    AdaptationSignalConfidence, AdaptationSignalKind, ExecutionAdaptationContext,
)


EXECUTION_ADAPTATION_PROPOSAL_VERSION = "0.8G.2C.3"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposalKind(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    INCREASE_TARGET = "INCREASE_TARGET"
    DECREASE_TARGET = "DECREASE_TARGET"
    REVIEW_EXECUTION = "REVIEW_EXECUTION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ProposalDirection(StrEnum):
    NONE = "NONE"
    FASTER_PACE = "FASTER_PACE"
    SLOWER_PACE = "SLOWER_PACE"
    HIGHER_POWER = "HIGHER_POWER"
    LOWER_POWER = "LOWER_POWER"
    REVIEW = "REVIEW"
    WAIT_FOR_EVIDENCE = "WAIT_FOR_EVIDENCE"


class ProposalReasonCode(StrEnum):
    SOURCE_INSUFFICIENT_SIGNAL = "SOURCE_INSUFFICIENT_SIGNAL"
    SOURCE_MAINTAIN_SIGNAL = "SOURCE_MAINTAIN_SIGNAL"
    SOURCE_PROGRESSION_SIGNAL = "SOURCE_PROGRESSION_SIGNAL"
    SOURCE_REGRESSION_SIGNAL = "SOURCE_REGRESSION_SIGNAL"
    SOURCE_INCONSISTENT_SIGNAL = "SOURCE_INCONSISTENT_SIGNAL"
    TARGET_STEP_UNAVAILABLE = "TARGET_STEP_UNAVAILABLE"
    DIRECTION_ONLY_PROPOSAL = "DIRECTION_ONLY_PROPOSAL"
    NO_EXECUTABLE_TARGET_KIND = "NO_EXECUTABLE_TARGET_KIND"
    DISCIPLINE_TARGET_MISMATCH = "DISCIPLINE_TARGET_MISMATCH"
    EXTREME_OVERSHOOT_GUARD = "EXTREME_OVERSHOOT_GUARD"
    STRENGTH_EXECUTION_DATA_INSUFFICIENT = "STRENGTH_EXECUTION_DATA_INSUFFICIENT"


class ProposalGuard(StrEnum):
    NO_NUMERIC_STEP_AVAILABLE = "NO_NUMERIC_STEP_AVAILABLE"
    NO_CURRENT_TARGET_BOUNDS = "NO_CURRENT_TARGET_BOUNDS"
    NO_CAPABILITY_BOUND_AVAILABLE = "NO_CAPABILITY_BOUND_AVAILABLE"
    UNSUPPORTED_TARGET_KIND = "UNSUPPORTED_TARGET_KIND"
    DISCIPLINE_COMPATIBILITY = "DISCIPLINE_COMPATIBILITY"
    EXTREME_OVERSHOOT = "EXTREME_OVERSHOOT"
    STRENGTH_INTENSITY_UNOBSERVED = "STRENGTH_INTENSITY_UNOBSERVED"


class PrescriptionRange(FrozenModel):
    minimum: float = Field(gt=0)
    maximum: float = Field(gt=0)
    unit: str

    @model_validator(mode="after")
    def valid_range(self):
        if self.minimum > self.maximum:
            raise ValueError("prescription range cannot be inverted")
        return self


class AdaptationProposal(FrozenModel):
    sport: str | None = None
    session_type: str | None = None
    target_kind: str | None = None
    proposal_kind: ProposalKind
    confidence: AdaptationSignalConfidence
    source_signal: AdaptationSignalKind
    source_signal_version: str
    source_reason_codes: tuple[AdaptationReasonCode, ...]
    reason_codes: tuple[ProposalReasonCode, ...]
    supporting_metrics: AdaptationMetrics
    supporting_session_ids: tuple[UUID, ...]
    current_prescription: PrescriptionRange | None = None
    proposed_direction: ProposalDirection
    proposed_range: PrescriptionRange | None = None
    applied_guards: tuple[ProposalGuard, ...] = ()


class ProposalSummary(FrozenModel):
    proposal_count: int
    no_change: int
    increase_target: int
    decrease_target: int
    review_execution: int
    insufficient_evidence: int


class ProposalGroupSummary(FrozenModel):
    sport: str | None = None
    session_type: str | None = None
    target_kind: str | None = None
    proposal_kind: ProposalKind
    confidence: AdaptationSignalConfidence
    evidence_count: int


class ExecutionAdaptationProposalContext(FrozenModel):
    athlete_profile_id: UUID
    as_of_date: date
    window_start_date: date
    algorithm_version: str = EXECUTION_ADAPTATION_PROPOSAL_VERSION
    source_adaptation_version: str
    proposals: tuple[AdaptationProposal, ...] = ()
    group_summaries: tuple[ProposalGroupSummary, ...] = ()
    summary: ProposalSummary


class ExecutionProposalAthleteMismatchError(ValueError):
    pass


SOURCE_REASON = {
    AdaptationSignalKind.INSUFFICIENT_EVIDENCE: ProposalReasonCode.SOURCE_INSUFFICIENT_SIGNAL,
    AdaptationSignalKind.MAINTAIN: ProposalReasonCode.SOURCE_MAINTAIN_SIGNAL,
    AdaptationSignalKind.PROGRESSION_CANDIDATE: ProposalReasonCode.SOURCE_PROGRESSION_SIGNAL,
    AdaptationSignalKind.REGRESSION_CANDIDATE: ProposalReasonCode.SOURCE_REGRESSION_SIGNAL,
    AdaptationSignalKind.INCONSISTENT_EXECUTION: ProposalReasonCode.SOURCE_INCONSISTENT_SIGNAL,
}
SUPPORTED_TARGETS = {
    ("running", "RUN_PACE"),
    ("cycling", "POWER"),
    ("swimming", "SWIM_PACE"),
}
CONFIDENCE_DOWNGRADE = {
    AdaptationSignalConfidence.HIGH: AdaptationSignalConfidence.MEDIUM,
    AdaptationSignalConfidence.MEDIUM: AdaptationSignalConfidence.LOW,
    AdaptationSignalConfidence.LOW: AdaptationSignalConfidence.LOW,
    AdaptationSignalConfidence.INSUFFICIENT: AdaptationSignalConfidence.INSUFFICIENT,
}


def _direction(signal: AdaptationSignal) -> ProposalDirection | None:
    progression = signal.signal == AdaptationSignalKind.PROGRESSION_CANDIDATE
    regression = signal.signal == AdaptationSignalKind.REGRESSION_CANDIDATE
    if not progression and not regression:
        return None
    if signal.target_kind in {"RUN_PACE", "SWIM_PACE"}:
        return ProposalDirection.FASTER_PACE if progression else ProposalDirection.SLOWER_PACE
    if signal.target_kind == "POWER":
        return ProposalDirection.HIGHER_POWER if progression else ProposalDirection.LOWER_POWER
    return None


def build_adaptation_proposal(signal: AdaptationSignal, *, source_version: str) -> AdaptationProposal:
    reasons = [SOURCE_REASON[signal.signal]]
    guards = []
    confidence = signal.confidence
    direction = ProposalDirection.NONE
    if signal.sport == "strength":
        kind = ProposalKind.INSUFFICIENT_EVIDENCE
        direction = ProposalDirection.WAIT_FOR_EVIDENCE
        reasons.append(ProposalReasonCode.STRENGTH_EXECUTION_DATA_INSUFFICIENT)
        guards.append(ProposalGuard.STRENGTH_INTENSITY_UNOBSERVED)
        confidence = AdaptationSignalConfidence.INSUFFICIENT
    elif signal.signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE:
        kind = ProposalKind.INSUFFICIENT_EVIDENCE
        direction = ProposalDirection.WAIT_FOR_EVIDENCE
    elif signal.signal == AdaptationSignalKind.MAINTAIN:
        kind = ProposalKind.NO_CHANGE
    elif signal.signal == AdaptationSignalKind.INCONSISTENT_EXECUTION:
        kind = ProposalKind.REVIEW_EXECUTION
        direction = ProposalDirection.REVIEW
        if AdaptationReasonCode.EXTREME_OVERSHOOT_PRESENT in signal.reason_codes:
            reasons.append(ProposalReasonCode.EXTREME_OVERSHOOT_GUARD)
            guards.append(ProposalGuard.EXTREME_OVERSHOOT)
    else:
        desired = _direction(signal)
        if signal.target_kind is None:
            kind = ProposalKind.REVIEW_EXECUTION
            direction = ProposalDirection.REVIEW
            reasons.append(ProposalReasonCode.NO_EXECUTABLE_TARGET_KIND)
            guards.append(ProposalGuard.UNSUPPORTED_TARGET_KIND)
            confidence = CONFIDENCE_DOWNGRADE[confidence]
        elif (signal.sport, signal.target_kind) not in SUPPORTED_TARGETS or desired is None:
            kind = ProposalKind.REVIEW_EXECUTION
            direction = ProposalDirection.REVIEW
            reasons.append(ProposalReasonCode.DISCIPLINE_TARGET_MISMATCH)
            guards.extend((ProposalGuard.UNSUPPORTED_TARGET_KIND, ProposalGuard.DISCIPLINE_COMPATIBILITY))
            confidence = CONFIDENCE_DOWNGRADE[confidence]
        else:
            kind = ProposalKind.INCREASE_TARGET if signal.signal == AdaptationSignalKind.PROGRESSION_CANDIDATE else ProposalKind.DECREASE_TARGET
            direction = desired
            reasons.extend((ProposalReasonCode.TARGET_STEP_UNAVAILABLE, ProposalReasonCode.DIRECTION_ONLY_PROPOSAL))
            guards.extend((ProposalGuard.NO_NUMERIC_STEP_AVAILABLE, ProposalGuard.NO_CURRENT_TARGET_BOUNDS, ProposalGuard.NO_CAPABILITY_BOUND_AVAILABLE))
            confidence = CONFIDENCE_DOWNGRADE[confidence]
    return AdaptationProposal(
        sport=signal.sport, session_type=signal.session_type, target_kind=signal.target_kind,
        proposal_kind=kind, confidence=confidence, source_signal=signal.signal,
        source_signal_version=source_version, source_reason_codes=signal.reason_codes,
        reason_codes=tuple(reasons), supporting_metrics=signal.supporting_metrics,
        supporting_session_ids=tuple(sorted(signal.supporting_session_ids, key=str)),
        proposed_direction=direction, applied_guards=tuple(guards),
    )


def build_execution_adaptation_proposal_context(adaptation: ExecutionAdaptationContext, *, athlete_profile_id: UUID | None = None) -> ExecutionAdaptationProposalContext:
    if athlete_profile_id is not None and adaptation.athlete_profile_id != athlete_profile_id:
        raise ExecutionProposalAthleteMismatchError("adaptation context athlete does not match requested athlete")
    structured_keys = {(item.sport, item.session_type) for item in adaptation.structured_target_signals}
    signals = list(adaptation.structured_target_signals)
    signals.extend(item for item in adaptation.session_type_signals if (item.sport, item.session_type) not in structured_keys)
    signals.sort(key=lambda item: (item.sport or "", item.session_type or "", item.target_kind or ""))
    proposals = tuple(build_adaptation_proposal(item, source_version=adaptation.algorithm_version) for item in signals)
    counts = Counter(item.proposal_kind for item in proposals)
    return ExecutionAdaptationProposalContext(
        athlete_profile_id=adaptation.athlete_profile_id, as_of_date=adaptation.as_of_date,
        window_start_date=adaptation.window_start_date,
        source_adaptation_version=adaptation.algorithm_version, proposals=proposals,
        group_summaries=tuple(ProposalGroupSummary(
            sport=item.sport, session_type=item.session_type, target_kind=item.target_kind,
            proposal_kind=item.proposal_kind, confidence=item.confidence,
            evidence_count=item.supporting_metrics.evaluable_sessions,
        ) for item in proposals),
        summary=ProposalSummary(
            proposal_count=len(proposals), no_change=counts[ProposalKind.NO_CHANGE],
            increase_target=counts[ProposalKind.INCREASE_TARGET],
            decrease_target=counts[ProposalKind.DECREASE_TARGET],
            review_execution=counts[ProposalKind.REVIEW_EXECUTION],
            insufficient_evidence=counts[ProposalKind.INSUFFICIENT_EVIDENCE],
        ),
    )
