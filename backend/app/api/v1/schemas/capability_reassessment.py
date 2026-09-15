"""Bounded public projection of C.7; policy remains in the domain."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from app.domains.planning.contracts import FrozenModel
from app.domains.capability.reassessment import (
    CapabilityKind, CapabilityReassessmentContext, ReassessmentConfidence,
    ReassessmentReason, ReassessmentStatus, ReassessmentSummary,
)


class CapabilityReferenceResponse(FrozenModel):
    value: Decimal
    unit: str
    effective_from: datetime | None
    source: str | None
    quality: str | None


class CapabilityEvidenceResponse(FrozenModel):
    eligible_comparisons: int
    recent: int
    background: int
    contradicting: int


class CapabilityCandidateResponse(FrozenModel):
    capability_kind: CapabilityKind
    status: ReassessmentStatus
    confidence: ReassessmentConfidence
    current_reference: CapabilityReferenceResponse | None
    evidence: CapabilityEvidenceResponse
    reason_codes: tuple[ReassessmentReason, ...]


class CapabilityReassessmentResponse(FrozenModel):
    api_version: Literal["0.8G.2C.8"] = "0.8G.2C.8"
    athlete_profile_id: UUID
    as_of_date: date
    window_start_date: date
    algorithm_version: str
    candidates: tuple[CapabilityCandidateResponse, ...]
    summary: ReassessmentSummary

    @classmethod
    def from_context(cls, context: CapabilityReassessmentContext):
        return cls(athlete_profile_id=context.athlete_profile_id, as_of_date=context.as_of_date,
            window_start_date=context.window_start_date, algorithm_version=context.algorithm_version,
            summary=context.summary, candidates=tuple(CapabilityCandidateResponse(
                capability_kind=item.capability_kind, status=item.status, confidence=item.confidence,
                reason_codes=item.reason_codes,
                current_reference=CapabilityReferenceResponse(**{key: getattr(item.current_reference, key)
                    for key in CapabilityReferenceResponse.model_fields}) if item.current_reference else None,
                evidence=CapabilityEvidenceResponse(**{key: getattr(item.evidence, key)
                    for key in CapabilityEvidenceResponse.model_fields}),
            ) for item in context.candidates))
