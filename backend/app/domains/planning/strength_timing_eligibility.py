"""Temporal integrity eligibility only. Never selects or activates duration.

Evidence is an explicit review attestation, not an empirical accuracy claim.
Recompute through the existing estimator; do not trust a supplied coverage flag.
"""
from typing import Literal

from pydantic import ValidationError

from app.domains.planning.contracts import FrozenModel, context_fingerprint
from app.domains.planning.strength_timing import (
    Digest, Text, StrengthTimingSnapshot, StrengthTimingEstimate,
    estimate_strength_timing,
)

VERSION = "strength-timing-eligibility-shadow-4b5-v1"


class StrengthTimingReview(FrozenModel):
    review_id: Text
    version: Text
    timing_snapshot_fingerprint: Digest
    # Exact provenance objects reviewed, identified by their canonical hashes.
    reviewed_provenance_fingerprints: tuple[Digest, ...] = ()
    reviewed_policy_versions: tuple[Text, ...] = ()
    independence: Literal["verified", "unverifiable", "circular"] = "unverifiable"


class StrengthTimingEligibility(FrozenModel):
    version: str = VERSION
    mode: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    temporally_eligible: bool
    estimate: StrengthTimingEstimate
    review_id: str | None = None
    reasons: tuple[str, ...]
    # These are separate future responsibilities, never implied by eligibility.
    daily_availability: Literal["not_evaluated"] = "not_evaluated"
    weekly_distribution: Literal["not_evaluated"] = "not_evaluated"
    double_sessions: Literal["not_evaluated"] = "not_evaluated"
    load_budget: Literal["not_evaluated"] = "not_evaluated"
    activation_authorized: Literal[False] = False


def evaluate_strength_timing_eligibility(context, workout, snapshot: StrengthTimingSnapshot | None,
                                         review: StrengthTimingReview | None = None):
    """Read no legacy, target, availability, load or weekly-budget values.

    The estimator validates binding, intervals, routes, occurrences and disjoint
    temporal scopes. Independent provenance applicability cannot be established
    from populated fields alone: require a bound, explicit review record.
    """
    estimate = estimate_strength_timing(context, workout, snapshot)
    reasons = list(estimate.diagnostics)
    if estimate.coverage != "complete":
        reasons.append("COVERAGE_" + estimate.coverage.upper())
    if estimate.missing_components:
        reasons.append("UNKNOWN_COMPONENTS")
    validated_review = None
    if review is None:
        reasons.append("INTEGRITY_REQUIREMENTS_UNVERIFIABLE")
    else:
        try:
            validated_review = StrengthTimingReview.model_validate(review.model_dump(mode="python"))
        except ValidationError:
            reasons.append("INTEGRITY_REQUIREMENTS_UNVERIFIABLE")
    if validated_review is not None:
        if estimate.timing_snapshot_fingerprint != validated_review.timing_snapshot_fingerprint:
            reasons.append("TIMING_SNAPSHOT_BINDING_MISMATCH")
        if validated_review.independence == "circular":
            reasons.append("CIRCULAR_TIMING_DEPENDENCY")
        elif validated_review.independence != "verified":
            reasons.append("INTEGRITY_REQUIREMENTS_UNVERIFIABLE")
        # Hashes include source id, version, derivation and input references.
        # This reviews the entire provenance chain declaration, not just a label.
        reviewed = set(validated_review.reviewed_provenance_fingerprints)
        if any(context_fingerprint(k.provenance) not in reviewed for k in estimate.known_components):
            reasons.append("INSUFFICIENT_PROVENANCE")
        if snapshot is not None:
            policies = {snapshot.policy_version}
            policies.update(k.provenance.version for k in estimate.known_components
                            if k.provenance.source in {"configurable_prescription", "reviewed_timing_policy"})
            if policies - set(validated_review.reviewed_policy_versions):
                reasons.append("INTEGRITY_REQUIREMENTS_UNVERIFIABLE")
    reasons = tuple(sorted(set(reasons)))
    return StrengthTimingEligibility(temporally_eligible=not reasons, estimate=estimate,
        review_id=validated_review.review_id if validated_review else None, reasons=reasons)
