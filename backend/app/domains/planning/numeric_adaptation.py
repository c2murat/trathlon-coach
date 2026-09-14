from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import model_validator

from app.domains.planning.contracts import FrozenModel, PlanningAdaptationInput, PlanningAdaptationItem
from app.domains.planning.execution_adaptation import AdaptationSignalConfidence
from app.domains.planning.execution_proposals import (
    ProposalDirection,
    ProposalKind,
    ProposalGuard,
    ExecutionAdaptationProposalContext,
)
from app.domains.planning.contracts import PlanningContext, canonical_json
from app.domains.planning.session_planning import SessionType
from app.domains.planning.contracts import PrescriptionLevelTransition
from app.domains.planning.prescription_intensity import (
    LevelResolutionStatus, LevelStepDirection, PrescriptionLevelResolution,
    PrescriptionTargetRange as NumericRange, resolve_prescription_intensity_step,
)


NUMERIC_ADAPTATION_RESOLUTION_VERSION = "0.8G.2C.5"


class NumericResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    NO_SAFE_STEP = "NO_SAFE_STEP"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    GUARDED = "GUARDED"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICT = "CONFLICT"


class NumericResolutionReason(StrEnum):
    NO_ORDERED_TARGET_LEVELS = "NO_ORDERED_TARGET_LEVELS"
    CURRENT_LEVEL_NOT_IDENTIFIED = "CURRENT_LEVEL_NOT_IDENTIFIED"
    LEVEL_BOUNDARY = "LEVEL_BOUNDARY"
    LEVEL_RESOLUTION_GUARD = "LEVEL_RESOLUTION_GUARD"
    ADJACENT_PRESCRIPTION_LEVEL = "ADJACENT_PRESCRIPTION_LEVEL"
    SOURCE_NOT_ACTIONABLE = "SOURCE_NOT_ACTIONABLE"
    SOURCE_GUARD = "SOURCE_GUARD"
    SESSION_TYPE_MISMATCH = "SESSION_TYPE_MISMATCH"
    INVALID_CURRENT_TARGET = "INVALID_CURRENT_TARGET"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_AMBIGUOUS = "TARGET_AMBIGUOUS"
    DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    STRENGTH_UNSUPPORTED = "STRENGTH_UNSUPPORTED"
    CONFLICTING_PROPOSALS = "CONFLICTING_PROPOSALS"


class NumericAdaptationResolution(FrozenModel):
    athlete_id: UUID
    cutoff_date: date
    sport: str | None = None
    session_type: str | None = None
    target_kind: str | None = None
    unit: str | None = None
    source_proposal_kind: ProposalKind
    direction: ProposalDirection
    confidence: AdaptationSignalConfidence
    current_range: NumericRange | None = None
    proposed_range: NumericRange | None = None
    status: NumericResolutionStatus
    reason_codes: tuple[NumericResolutionReason, ...]
    guards: tuple[NumericResolutionReason, ...] = ()
    source_guards: tuple[ProposalGuard, ...] = ()
    source_proposal_version: str
    numeric_policy_version: str = NUMERIC_ADAPTATION_RESOLUTION_VERSION
    level_resolution: PrescriptionLevelResolution | None = None

    @model_validator(mode="after")
    def coherent_resolution(self):
        if self.level_resolution is not None:
            levels = self.level_resolution
            if (levels.athlete_id, levels.cutoff_date, levels.sport, levels.session_type, levels.target_kind, levels.current_range) != (
                self.athlete_id, self.cutoff_date, self.sport, self.session_type, self.target_kind, self.current_range,
            ):
                raise ValueError("numeric and prescription level resolution scopes must agree")
            if self.status == NumericResolutionStatus.RESOLVED and (
                levels.status != LevelResolutionStatus.ADJACENT_LEVEL or levels.level_after.target_range != self.proposed_range
            ):
                raise ValueError("numeric candidate must come from the resolved adjacent level")
        if self.status == NumericResolutionStatus.RESOLVED:
            if self.guards or self.confidence not in {AdaptationSignalConfidence.MEDIUM, AdaptationSignalConfidence.HIGH}:
                raise ValueError("resolved numeric adaptation cannot be guarded or low confidence")
            if set(self.source_guards) - DIRECTION_ONLY_GUARDS:
                raise ValueError("resolved numeric adaptation has an unresolved source guard")
            if self.current_range is None or self.proposed_range is None:
                raise ValueError("resolved numeric adaptation requires current and proposed ranges")
            if self.current_range.unit != self.proposed_range.unit or self.unit != self.proposed_range.unit:
                raise ValueError("resolved numeric adaptation units must agree")
            # Reuse C.4 sport/kind/direction validation; C.5 additionally requires
            # both endpoints to move strictly in that direction.
            _planning_item(self)
            if self.current_range.minimum == self.proposed_range.minimum or self.current_range.maximum == self.proposed_range.maximum:
                raise ValueError("numeric adaptation must change both endpoints")
        elif self.proposed_range is not None:
            raise ValueError("non-resolved numeric adaptation cannot expose a proposed range")
        return self


class NumericAdaptationResolutionContext(FrozenModel):
    athlete_id: UUID
    cutoff_date: date
    source_proposal_version: str
    numeric_policy_version: str = NUMERIC_ADAPTATION_RESOLUTION_VERSION
    resolutions: tuple[NumericAdaptationResolution, ...] = ()

    @model_validator(mode="after")
    def consistent_scope(self):
        for item in self.resolutions:
            if (item.athlete_id, item.cutoff_date, item.source_proposal_version, item.numeric_policy_version) != (
                self.athlete_id, self.cutoff_date, self.source_proposal_version, self.numeric_policy_version,
            ):
                raise ValueError("numeric resolution scope and versions must agree")
        return self


class NumericAdaptationAthleteMismatchError(ValueError):
    pass


class NumericAdaptationCutoffMismatchError(ValueError):
    pass


EXPECTED = {
    "running": ("RUN_PACE", "seconds_per_km", "pace", "RUN_"),
    "cycling": ("POWER", "watts", "power", "BIKE_"),
    "swimming": ("SWIM_PACE", "seconds_per_100m", "swim_pace", "SWIM_"),
}
# These C.3 guards describe missing numeric resolution, not safety clearance.
# All are retained for audit; every other source guard blocks the attempt.
DIRECTION_ONLY_GUARDS = frozenset({
    ProposalGuard.NO_NUMERIC_STEP_AVAILABLE,
    ProposalGuard.NO_CURRENT_TARGET_BOUNDS,
    ProposalGuard.NO_CAPABILITY_BOUND_AVAILABLE,
})


def _work_targets(draft):
    def visit(nodes):
        for node in nodes:
            if node.kind == "repeat":
                yield from visit(node.steps or ())
            elif node.phase == "work" and node.target is not None:
                yield node.target
    return tuple(visit(draft.definition.steps)) if draft.definition else ()


def _signature(proposal):
    # Include legacy numeric fields for conflict detection only, never as targets.
    return canonical_json({
        "kind": proposal.proposal_kind,
        "direction": proposal.proposed_direction,
        "confidence": proposal.confidence,
        "current": proposal.current_prescription,
        "proposed": proposal.proposed_range,
        "guards": sorted(proposal.applied_guards),
    })


def _result(proposals, proposal, status, reason, *, current=None, proposed=None, guards=(), levels=None):
    return NumericAdaptationResolution(
        athlete_id=proposals.athlete_profile_id,
        cutoff_date=proposals.as_of_date,
        sport=proposal.sport,
        session_type=proposal.session_type,
        target_kind=proposal.target_kind,
        unit=current.unit if current else None,
        source_proposal_kind=proposal.proposal_kind,
        direction=proposal.proposed_direction,
        confidence=proposal.confidence,
        current_range=current,
        proposed_range=proposed,
        status=status,
        reason_codes=(reason,),
        guards=tuple(guards),
        source_guards=tuple(sorted(set(proposal.applied_guards))),
        source_proposal_version=proposals.algorithm_version,
        level_resolution=levels,
    )


def resolve_numeric_adaptations(*, proposals: ExecutionAdaptationProposalContext,
                                context: PlanningContext, prescriptions, drafts):
    """Resolve against freshly built, unadapted Planning targets, without IO.

    C.6 is the only adjacent-level source. Its conservative production catalog
    has no supported ladders; absence of a real step preserves the C.5 fallback.
    """
    athlete_id = context.request.athlete_id
    cutoff_date = context.request.planning_date
    if proposals.athlete_profile_id != athlete_id:
        raise NumericAdaptationAthleteMismatchError("proposal athlete does not match planning athlete")
    if proposals.as_of_date != cutoff_date:
        raise NumericAdaptationCutoffMismatchError("proposal cutoff does not match planning cutoff")
    if context.adaptive_capability and context.adaptive_capability.cutoff_date != cutoff_date:
        raise NumericAdaptationCutoffMismatchError("capability cutoff does not match planning cutoff")
    if context.planning_adaptation is not None:
        raise ValueError("numeric resolution requires the unadapted planning context")
    targets = defaultdict(list)
    for session, draft in zip(prescriptions, drafts, strict=True):
        if draft.session_type != session.session_type or (draft.sport is not None and draft.sport != session.discipline):
            raise ValueError("numeric resolution draft does not match prescription")
        if draft.context_fingerprint != context.fingerprint:
            raise ValueError("numeric resolution draft does not match base context")
        targets[(session.discipline, session.session_type.value)].extend(_work_targets(draft))
    grouped = defaultdict(list)
    for proposal in proposals.proposals:
        grouped[(proposal.sport or "", proposal.session_type or "", proposal.target_kind or "")].append(proposal)
    resolutions = []
    for key, group in sorted(grouped.items()):
        unique = {_signature(item): item for item in group}
        if len(unique) > 1:
            resolutions.extend(_result(
                proposals, unique[signature], NumericResolutionStatus.CONFLICT,
                NumericResolutionReason.CONFLICTING_PROPOSALS,
                guards=(NumericResolutionReason.CONFLICTING_PROPOSALS,),
            ) for signature in sorted(unique))
            continue
        proposal = group[0]

        def append(status, reason, *, current=None, guarded=False):
            resolutions.append(_result(proposals, proposal, status, reason,
                                       current=current, guards=(reason,) if guarded else ()))

        if proposal.sport == "strength":
            append(NumericResolutionStatus.NOT_APPLICABLE, NumericResolutionReason.STRENGTH_UNSUPPORTED)
            continue
        if proposal.proposal_kind not in {ProposalKind.INCREASE_TARGET, ProposalKind.DECREASE_TARGET}:
            append(NumericResolutionStatus.NOT_APPLICABLE, NumericResolutionReason.SOURCE_NOT_ACTIONABLE)
            continue
        if proposal.confidence not in {AdaptationSignalConfidence.HIGH, AdaptationSignalConfidence.MEDIUM}:
            append(NumericResolutionStatus.GUARDED, NumericResolutionReason.LOW_CONFIDENCE, guarded=True)
            continue
        if set(proposal.applied_guards) - DIRECTION_ONLY_GUARDS:
            append(NumericResolutionStatus.GUARDED, NumericResolutionReason.SOURCE_GUARD, guarded=True)
            continue
        expected = EXPECTED.get(proposal.sport)
        if expected is None or proposal.target_kind != expected[0]:
            append(NumericResolutionStatus.UNSUPPORTED, NumericResolutionReason.UNIT_MISMATCH, guarded=True)
            continue
        if proposal.session_type not in SessionType._value2member_map_ or not proposal.session_type.startswith(expected[3]):
            append(NumericResolutionStatus.GUARDED, NumericResolutionReason.SESSION_TYPE_MISMATCH, guarded=True)
            continue
        increasing = proposal.proposal_kind == ProposalKind.INCREASE_TARGET
        direction = (ProposalDirection.HIGHER_POWER if increasing else ProposalDirection.LOWER_POWER) if proposal.sport == "cycling" else (ProposalDirection.FASTER_PACE if increasing else ProposalDirection.SLOWER_PACE)
        if proposal.proposed_direction != direction:
            append(NumericResolutionStatus.GUARDED, NumericResolutionReason.DIRECTION_MISMATCH, guarded=True)
            continue
        matches = targets.get(key[:2], ())
        if not matches:
            append(NumericResolutionStatus.NO_SAFE_STEP, NumericResolutionReason.TARGET_NOT_FOUND)
            continue
        if any(target.resolved_unit != expected[1] or target.metric != expected[2] for target in matches):
            append(NumericResolutionStatus.UNSUPPORTED, NumericResolutionReason.UNIT_MISMATCH, guarded=True)
            continue
        try:
            ranges = {NumericRange(minimum=Decimal(str(target.resolved_minimum)),
                                   maximum=Decimal(str(target.resolved_maximum)),
                                   unit=target.resolved_unit) for target in matches}
        except (ValueError, ArithmeticError):
            append(NumericResolutionStatus.GUARDED, NumericResolutionReason.INVALID_CURRENT_TARGET, guarded=True)
            continue
        if len(ranges) != 1:
            append(NumericResolutionStatus.GUARDED, NumericResolutionReason.TARGET_AMBIGUOUS, guarded=True)
            continue
        current = next(iter(ranges))
        levels = resolve_prescription_intensity_step(
            context=context, sport=proposal.sport, session_type=proposal.session_type,
            target_kind=proposal.target_kind, current_range=current,
            direction=LevelStepDirection.PROGRESSION if increasing else LevelStepDirection.REGRESSION,
        )
        if levels.status == LevelResolutionStatus.ADJACENT_LEVEL:
            resolutions.append(_result(proposals, proposal, NumericResolutionStatus.RESOLVED,
                NumericResolutionReason.ADJACENT_PRESCRIPTION_LEVEL, current=current,
                proposed=levels.level_after.target_range, levels=levels))
        else:
            reason = {
                LevelResolutionStatus.NO_SUPPORTED_LADDER: NumericResolutionReason.NO_ORDERED_TARGET_LEVELS,
                LevelResolutionStatus.CURRENT_LEVEL_NOT_IDENTIFIED: NumericResolutionReason.CURRENT_LEVEL_NOT_IDENTIFIED,
                LevelResolutionStatus.BOUNDARY: NumericResolutionReason.LEVEL_BOUNDARY,
            }.get(levels.status, NumericResolutionReason.LEVEL_RESOLUTION_GUARD)
            resolutions.append(_result(proposals, proposal, NumericResolutionStatus.NO_SAFE_STEP,
                reason, current=current, levels=levels))
    return NumericAdaptationResolutionContext(
        athlete_id=athlete_id, cutoff_date=cutoff_date,
        source_proposal_version=proposals.algorithm_version,
        resolutions=tuple(resolutions),
    )


def _planning_item(item: NumericAdaptationResolution) -> PlanningAdaptationItem:
    transition = None
    if item.level_resolution is not None:
        levels = item.level_resolution
        if levels.status != LevelResolutionStatus.ADJACENT_LEVEL:
            raise ValueError("only an adjacent prescription level can affect planning")
        before, after = levels.level_before, levels.level_after
        transition = PrescriptionLevelTransition(
            policy_version=levels.version, ladder_id=levels.ladder_id,
            level_before=before.level_id, level_after=after.level_id,
            index_before=before.index, index_after=after.index,
            source_before=before.source, source_after=after.source,
            source_version_before=before.source_version, source_version_after=after.source_version,
            capability_fingerprint=before.capability_reference.capability_fingerprint,
            base_context_fingerprint=levels.context_fingerprint,
        )
    return PlanningAdaptationItem(
        proposal_version=item.source_proposal_version,
        numeric_policy_version=item.numeric_policy_version,
        prescription_level_transition=transition,
        cutoff_date=item.cutoff_date,
        sport=item.sport, session_type=item.session_type, target_kind=item.target_kind,
        proposal_kind=item.source_proposal_kind.value, direction=item.direction.value,
        confidence=item.confidence.value,
        current_minimum=item.current_range.minimum, current_maximum=item.current_range.maximum,
        proposed_minimum=item.proposed_range.minimum, proposed_maximum=item.proposed_range.maximum,
        unit=item.proposed_range.unit,
    )


def project_resolved_adaptations(context: NumericAdaptationResolutionContext) -> PlanningAdaptationInput | None:
    items = tuple(_planning_item(item) for item in context.resolutions if item.status == NumericResolutionStatus.RESOLVED)
    if not items:
        return None
    return PlanningAdaptationInput(
        athlete_id=context.athlete_id, proposal_version=context.source_proposal_version,
        numeric_policy_version=context.numeric_policy_version,
        cutoff_date=context.cutoff_date, items=items,
    )
