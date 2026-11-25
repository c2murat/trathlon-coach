"""Synthetic timing reviews only; never injected into active planning."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import context_fingerprint
from app.domains.planning.strength_timing import empty_timing_snapshot
from app.domains.planning.strength_timing_inputs import compile_strength_timing_inputs
from app.domains.planning.strength_timing_eligibility import (
    VERSION, StrengthTimingReview, evaluate_strength_timing_eligibility,
)
from tests.test_strength_timing_policy import base, single, explicit
from tests.test_strength_timing_inputs import rep


def complete(base):
    ctx, _, _ = base
    w = single(base)
    snapshot = compile_strength_timing_inputs(ctx, w, explicit(ctx, w, rep())).snapshot
    return ctx, w, snapshot


def reviewed(ctx, w, snapshot):
    e = evaluate_strength_timing_eligibility(ctx, w, snapshot).estimate
    return StrengthTimingReview(review_id="synthetic-review", version="fixture-v1",
        timing_snapshot_fingerprint=e.timing_snapshot_fingerprint,
        reviewed_provenance_fingerprints=tuple(context_fingerprint(k.provenance) for k in e.known_components),
        reviewed_policy_versions=(snapshot.policy_version,), independence="verified")


def test_complete_reviewed_eligible_still_legacy_and_not_authorized(base):
    ctx, w, s = complete(base); before = w.model_dump_json()
    result = evaluate_strength_timing_eligibility(ctx, w, s, reviewed(ctx, w, s))
    assert result.temporally_eligible and not result.reasons
    assert result.version == VERSION and result.estimate.coverage == "complete"
    assert result.estimate.validation_state == "not_evaluated"
    assert not result.activation_authorized
    assert {result.daily_availability, result.weekly_distribution, result.double_sessions, result.load_budget} == {"not_evaluated"}
    assert w.model_dump_json() == before
    assert not hasattr(result, "selected_duration_minutes")


@pytest.mark.parametrize("updates,reason", [
    ({"independence": "unverifiable"}, "INTEGRITY_REQUIREMENTS_UNVERIFIABLE"),
    ({"independence": "circular"}, "CIRCULAR_TIMING_DEPENDENCY"),
    ({"reviewed_provenance_fingerprints": ()}, "INSUFFICIENT_PROVENANCE"),
    ({"reviewed_policy_versions": ()}, "INTEGRITY_REQUIREMENTS_UNVERIFIABLE"),
    ({"timing_snapshot_fingerprint": "f" * 64}, "TIMING_SNAPSHOT_BINDING_MISMATCH"),
    ({"review_id": ""}, "INTEGRITY_REQUIREMENTS_UNVERIFIABLE"),
])
def test_complete_does_not_bypass_other_criteria(base, updates, reason):
    ctx, w, s = complete(base)
    review = reviewed(ctx, w, s).model_copy(update=updates)
    result = evaluate_strength_timing_eligibility(ctx, w, s, review)
    assert result.estimate.coverage == "complete"
    assert not result.temporally_eligible and reason in result.reasons
    assert not result.activation_authorized


def test_complete_without_review_is_unverifiable(base):
    ctx, w, s = complete(base)
    result = evaluate_strength_timing_eligibility(ctx, w, s)
    assert not result.temporally_eligible
    assert result.reasons == ("INTEGRITY_REQUIREMENTS_UNVERIFIABLE",)


@pytest.mark.parametrize("kind", ["partial", "unavailable"])
def test_incomplete_can_never_be_eligible(base, kind):
    ctx, _, _ = base; w = single(base)
    s = compile_strength_timing_inputs(ctx, w, explicit(ctx, w, rep()).model_copy(update={"warmup": None})).snapshot if kind == "partial" else empty_timing_snapshot(ctx, w)
    result = evaluate_strength_timing_eligibility(ctx, w, s, reviewed(ctx, w, s))
    assert result.estimate.coverage == kind
    assert "COVERAGE_" + kind.upper() in result.reasons
    assert "UNKNOWN_COMPONENTS" in result.reasons and not result.temporally_eligible


@pytest.mark.parametrize("field,value,diagnostic", [
    ("definition_fingerprint", "a" * 64, "TIMING_SNAPSHOT_BINDING_MISMATCH"),
    ("workout_fingerprint", "a" * 64, "TIMING_SNAPSHOT_BINDING_MISMATCH"),
    ("context_fingerprint", "f" * 64, "TIMING_SNAPSHOT_BINDING_MISMATCH"),
    ("policy_version", "", "INVALID_TIMING_SNAPSHOT_CONTRACT"),
])
def test_bad_snapshot_fails_closed(base, field, value, diagnostic):
    ctx, w, s = complete(base); review = reviewed(ctx, w, s)
    result = evaluate_strength_timing_eligibility(ctx, w, s.model_copy(update={field:value}), review)
    assert not result.temporally_eligible and diagnostic in result.reasons


def test_overlapping_rest_and_invalid_interval_revalidated(base):
    ctx, w, s = complete(base); review = reviewed(ctx, w, s)
    exercise = s.exercises[0]
    for changed in (
        exercise.model_copy(update={"pauses": exercise.pauses + exercise.pauses}),
        exercise.model_copy(update={"execution_per_set": exercise.execution_per_set.model_copy(update={
            "seconds": exercise.execution_per_set.seconds.model_copy(update={"minimum": 999})})}),
    ):
        result = evaluate_strength_timing_eligibility(ctx, w, s.model_copy(update={"exercises":(changed,)}), review)
        assert not result.temporally_eligible
        assert "INVALID_TIMING_SNAPSHOT_CONTRACT" in result.reasons


def test_ambiguous_repeat_preserves_existing_diagnostic(base):
    from app.domains.planning.models import WorkoutNode
    ctx, w, _ = complete(base)
    definition = w.definition.model_copy(update={"steps":[WorkoutNode(kind="repeat", repetitions=2, steps=w.definition.steps)]})
    w = w.model_copy(update={"definition":definition, "fingerprint":context_fingerprint(definition)})
    result = evaluate_strength_timing_eligibility(ctx, w, empty_timing_snapshot(ctx, w))
    assert not result.temporally_eligible and "UNSUPPORTED_REPEAT_STRUCTURE" in result.reasons


def test_review_and_result_immutable_and_activation_cannot_be_enabled(base):
    ctx, w, s = complete(base); review = reviewed(ctx, w, s)
    result = evaluate_strength_timing_eligibility(ctx, w, s, review)
    with pytest.raises(ValidationError): review.independence = "circular"
    with pytest.raises(ValidationError): result.temporally_eligible = False
    with pytest.raises(ValidationError): type(result).model_validate(result.model_dump() | {"activation_authorized": True})


def test_deterministic_review_order(base):
    ctx, w, s = complete(base); review = reviewed(ctx, w, s)
    a = evaluate_strength_timing_eligibility(ctx, w, s, review)
    b = evaluate_strength_timing_eligibility(ctx, w, s, review.model_copy(update={"reviewed_provenance_fingerprints":tuple(reversed(review.reviewed_provenance_fingerprints))}))
    assert a == b


def test_foreign_athlete_and_missing_provenance_are_rejected(base):
    from uuid import UUID
    ctx, w, s = complete(base); review = reviewed(ctx, w, s)
    foreign = s.model_copy(update={"athlete_id":UUID("20000000-0000-0000-0000-000000000002")})
    result = evaluate_strength_timing_eligibility(ctx, w, foreign, review)
    assert not result.temporally_eligible and "TIMING_SNAPSHOT_BINDING_MISMATCH" in result.reasons
    e = s.exercises[0]
    bad = e.model_copy(update={"execution_per_set":e.execution_per_set.model_copy(update={"provenance":None})})
    result = evaluate_strength_timing_eligibility(ctx, w, s.model_copy(update={"exercises":(bad,)}), review)
    assert not result.temporally_eligible and "INVALID_TIMING_SNAPSHOT_CONTRACT" in result.reasons


def test_eligibility_has_no_runtime_consumers_or_duration_selector():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app"
    consumers = [p for p in root.rglob("*.py") if p.name != "strength_timing_eligibility.py"
                 and "strength_timing_eligibility" in p.read_text(encoding="utf-8")]
    assert consumers == []


@pytest.mark.parametrize("legacy,available,load", [(24,1,1), (40,5000,9999)])
def test_eligibility_independent_of_planning_values(base, legacy, available, load):
    ctx, w, _ = complete(base)
    prefs = ctx.preferences.model_copy(update={"availability_slots":tuple(x.model_copy(update={"available_minutes":available}) for x in ctx.preferences.availability_slots)})
    ctx = ctx.model_copy(update={"preferences":prefs, "training":ctx.training.model_copy(update={"windows":tuple(x.model_copy(update={"total_training_load":Decimal(load), "total_duration_seconds":legacy*60}) for x in ctx.training.windows)})})
    ctx = ctx.model_copy(update={"fingerprint":context_fingerprint(ctx.model_dump(exclude={"fingerprint"}))})
    # Rebind after changing the context; allocated time cannot supply evidence.
    definition = w.definition.model_copy(update={"steps":[n.model_copy(update={"duration":n.duration.model_copy(update={"seconds":legacy*99})}) for n in w.definition.steps]})
    w = w.model_copy(update={"definition":definition,"context_fingerprint":ctx.fingerprint,"fingerprint":context_fingerprint(definition)})
    s = compile_strength_timing_inputs(ctx, w, explicit(ctx, w, rep())).snapshot
    result = evaluate_strength_timing_eligibility(ctx, w, s, reviewed(ctx, w, s))
    assert result.temporally_eligible and result.estimate.duration_seconds.minimum == 30
    assert not result.activation_authorized
