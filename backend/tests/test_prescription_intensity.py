"""C.6 uses actual builder targets only; no invented adjacent ranges or ladders.

Singleton contract examples describe the one existing prescribed level. They
exercise exact identification and boundaries, not a supported production ladder.
"""
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import canonical_json, context_fingerprint
from app.domains.planning.prescription_intensity import (
    PRESCRIPTION_INTENSITY_LEVEL_VERSION, TARGET_SEMANTICS,
    LevelResolutionStatus, LevelResolutionReason, LevelStepDirection,
    PrescriptionCapabilityReference, PrescriptionIntensityLevel, PrescriptionIntensityLadder,
    PrescriptionLevelAthleteMismatchError, PrescriptionLevelContextMismatchError,
    PrescriptionTargetRange, build_prescription_intensity_ladder, capability_fingerprint,
    identify_current_level, resolve_adjacent_level, resolve_prescription_intensity_step,
)
from app.domains.planning.numeric_adaptation import NumericAdaptationResolution
from app.domains.planning.planning_adaptation import normalize_numeric_planning_adaptation
from app.domains.planning.session_planning import SessionType
from tests.test_numeric_adaptation import bundle, directional, resolve
from tests.test_workout_builder import phase_targets


SPORTS = [("running", SessionType.RUN_THRESHOLD), ("cycling", SessionType.BIKE_THRESHOLD),
          ("swimming", SessionType.SWIM_THRESHOLD)]


def observed_level(sport="running", session_type=SessionType.RUN_THRESHOLD):
    context, session, draft = bundle(sport, session_type)
    target = phase_targets(draft.definition)[0]
    expected = TARGET_SEMANTICS[sport]
    level = PrescriptionIntensityLevel(
        sport=sport, session_type=session_type, target_kind=expected[0],
        level_id=session_type.value, index=0, semantic_role="work",
        target_range=PrescriptionTargetRange(minimum=Decimal(str(target.resolved_minimum)),
                                             maximum=Decimal(str(target.resolved_maximum)), unit=target.resolved_unit),
        unit=target.resolved_unit, source=draft.target_provenance.derivation_rule,
        source_version=draft.configuration_version,
        capability_reference=PrescriptionCapabilityReference(
            athlete_id=context.request.athlete_id, cutoff_date=context.request.planning_date,
            context_fingerprint=context.fingerprint, capability_fingerprint=capability_fingerprint(context),
            reference=target.reference, value=Decimal(str(target.reference_value)), unit=target.reference_unit,
        ),
    )
    return context, session, draft, level


def singleton(context, level):
    return PrescriptionIntensityLadder(
        ladder_id=level.session_type.value, athlete_id=context.request.athlete_id,
        cutoff_date=context.request.planning_date, context_fingerprint=context.fingerprint,
        sport=level.sport, session_type=level.session_type, target_kind=level.target_kind,
        unit=level.unit, semantic_role=level.semantic_role, levels=(level,),
    )


@pytest.mark.parametrize("session_type", [item for item in SessionType if item.value.startswith(("RUN_", "BIKE_", "SWIM_"))])
def test_no_production_ladder_for_any_existing_session_type(session_type):
    sport = "running" if session_type.value.startswith("RUN_") else "cycling" if session_type.value.startswith("BIKE_") else "swimming"
    context, _, _ = bundle(sport, session_type)
    before = context.model_dump_json()
    result = build_prescription_intensity_ladder(context=context, sport=sport, session_type=session_type.value,
                                                target_kind=TARGET_SEMANTICS[sport][0])
    assert result.status == LevelResolutionStatus.NO_SUPPORTED_LADDER
    assert result.ladder is None
    assert result.version == PRESCRIPTION_INTENSITY_LEVEL_VERSION
    assert context.model_dump_json() == before


@pytest.mark.parametrize("sport,session_type", SPORTS)
def test_exact_observed_target_is_identified_without_nearest_zone(sport, session_type):
    context, _, _, level = observed_level(sport, session_type)
    ladder = singleton(context, level)
    result = identify_current_level(context=context, ladder=ladder, current_range=level.target_range)
    assert result.status == LevelResolutionStatus.IDENTIFIED
    assert result.level_before == level
    assert result.level_after is None
    assert canonical_json(ladder) == canonical_json(PrescriptionIntensityLadder.model_validate_json(ladder.model_dump_json()))
    # A near target is an invalid-match fixture, never a candidate prescription.
    changed = level.target_range.model_copy(update={"maximum": level.target_range.maximum + Decimal("0.001")})
    mismatch = identify_current_level(context=context, ladder=ladder, current_range=changed)
    assert mismatch.status == LevelResolutionStatus.CURRENT_LEVEL_NOT_IDENTIFIED
    assert mismatch.level_before is mismatch.level_after is None
    assert mismatch.reason_codes == (LevelResolutionReason.EXACT_TARGET_MISMATCH,)


@pytest.mark.parametrize("sport,session_type", SPORTS)
@pytest.mark.parametrize("direction", list(LevelStepDirection))
def test_single_existing_level_has_no_neighbor_and_never_creates_one(sport, session_type, direction):
    context, _, _, level = observed_level(sport, session_type)
    ladder = singleton(context, level)
    result = resolve_adjacent_level(context=context, ladder=ladder, current_range=level.target_range, direction=direction)
    assert result.status == LevelResolutionStatus.BOUNDARY
    assert result.reason_codes == (LevelResolutionReason.MAXIMUM_LEVEL if direction == LevelStepDirection.PROGRESSION else LevelResolutionReason.MINIMUM_LEVEL,)
    assert result.level_before == level and result.level_after is None
    assert ladder.levels == (level,)


@pytest.mark.parametrize("field", ["level_id", "target_range", "index", "unit", "session_type", "target_kind", "semantic_role", "capability_reference", "version"])
def test_invalid_ladder_contract_rejects_duplicates_mixed_scope_and_skips(field):
    context, _, _, level = observed_level()
    payload = singleton(context, level).model_dump(mode="python")
    if field in {"level_id", "target_range"}:
        # Repeating the actual level must fail; do not invent another range.
        other = level.model_dump(mode="python")
        other["index"] = 1
        if field == "target_range":
            other["level_id"] = "duplicate_range_invalid_fixture"
        payload["levels"] = (level.model_dump(mode="python"), other)
    else:
        row = payload["levels"][0]
        changes = {"index": 2, "unit": "watts", "session_type": SessionType.BIKE_THRESHOLD,
                   "target_kind": "POWER", "semantic_role": "recovery", "version": "wrong-version",
                   "capability_reference": {**row["capability_reference"], "athlete_id": UUID(int=999)}}
        row[field] = changes[field]
    with pytest.raises(ValidationError):
        PrescriptionIntensityLadder.model_validate(payload)


def test_units_and_bounds_reject_invalid_contracts():
    context, _, _, level = observed_level()
    ladder = singleton(context, level)
    wrong_unit = level.target_range.model_copy(update={"unit": "watts"})
    result = identify_current_level(context=context, ladder=ladder, current_range=wrong_unit)
    assert result.status == LevelResolutionStatus.GUARDED
    assert result.reason_codes == (LevelResolutionReason.UNIT_MISMATCH,)
    payload = level.model_dump(mode="python")
    payload["prescription_bounds"] = {"minimum": level.target_range.maximum, "maximum": level.target_range.maximum, "unit": level.unit}
    with pytest.raises(ValidationError, match="bounds"):
        PrescriptionIntensityLevel.model_validate(payload)


@pytest.mark.parametrize("sport,session_type", SPORTS)
@pytest.mark.parametrize("value", [None, Decimal("0"), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_capability_is_explicit_without_arithmetic(sport, session_type, value):
    context, _, _ = bundle(sport, session_type)
    context = context.model_copy(update={"performance": context.performance.model_copy(update={TARGET_SEMANTICS[sport][2]: value})})
    result = build_prescription_intensity_ladder(context=context, sport=sport, session_type=session_type.value, target_kind=TARGET_SEMANTICS[sport][0])
    assert result.status == LevelResolutionStatus.GUARDED
    assert result.reason_codes == (LevelResolutionReason.INVALID_CAPABILITY_REFERENCE,)


def test_no_strength_ladder_and_unknown_session_is_explicit():
    context, _, _ = bundle()
    strength = build_prescription_intensity_ladder(context=context, sport="strength", session_type="GENERAL_STRENGTH", target_kind="RPE")
    assert strength.status == LevelResolutionStatus.UNSUPPORTED
    assert strength.reason_codes == (LevelResolutionReason.STRENGTH_UNSUPPORTED,)
    unsupported = build_prescription_intensity_ladder(context=context, sport="running", session_type="RUN_UNKNOWN", target_kind="RUN_PACE")
    assert unsupported.status == LevelResolutionStatus.NO_SUPPORTED_LADDER
    assert unsupported.reason_codes == (LevelResolutionReason.UNSUPPORTED_SESSION_TYPE,)


def test_cross_athlete_stale_cutoff_and_changed_capability_rejected():
    context, _, _, level = observed_level()
    ladder = singleton(context, level)
    other = context.model_copy(update={"request": context.request.model_copy(update={"athlete_id": UUID(int=999)})})
    with pytest.raises(PrescriptionLevelAthleteMismatchError):
        identify_current_level(context=other, ladder=ladder, current_range=level.target_range)
    stale = context.model_copy(update={"request": context.request.model_copy(update={"planning_date": context.request.planning_date + timedelta(days=1)})})
    with pytest.raises(PrescriptionLevelContextMismatchError):
        identify_current_level(context=stale, ladder=ladder, current_range=level.target_range)
    changed = context.model_copy(update={"performance": context.performance.model_copy(update={"running_threshold_pace_seconds_per_km": Decimal("260")})})
    with pytest.raises(PrescriptionLevelContextMismatchError, match="stale"):
        identify_current_level(context=changed, ladder=ladder, current_range=level.target_range)


@pytest.mark.parametrize("sport,session_type", SPORTS)
@pytest.mark.parametrize("increasing", [True, False])
def test_c6_to_c5_to_c4_preserves_baseline_and_audits_attempt(sport, session_type, increasing):
    context, session, draft = bundle(sport, session_type)
    result = resolve(context, session, draft, increasing=increasing)
    numeric = result.resolutions[0]
    assert numeric.proposed_range is None
    if numeric.level_resolution is not None:
        assert numeric.level_resolution.status == LevelResolutionStatus.NO_SUPPORTED_LADDER
        assert numeric.level_resolution.current_range == numeric.current_range
        assert numeric.level_resolution.version == PRESCRIPTION_INTENSITY_LEVEL_VERSION
        assert numeric.level_resolution.level_after is None
    else:
        # SWIM can have main and residual targets; ambiguity blocks before C.6.
        assert numeric.status == "GUARDED"
    assert normalize_numeric_planning_adaptation(result).planning_input is None
    assert result == resolve(context, session, draft, increasing=increasing)
    assert numeric == NumericAdaptationResolution.model_validate_json(numeric.model_dump_json())


def test_c5_consumes_c6_result_instead_of_recomputing_levels(monkeypatch):
    context, session, draft = bundle()
    captured = []

    def capture(**kwargs):
        captured.append(kwargs)
        return resolve_prescription_intensity_step(**kwargs)

    monkeypatch.setattr("app.domains.planning.numeric_adaptation.resolve_prescription_intensity_step", capture)
    result = resolve(context, session, draft)
    assert len(captured) == 1
    assert captured[0]["context"] is context
    assert result.resolutions[0].level_resolution.status == LevelResolutionStatus.NO_SUPPORTED_LADDER


def test_no_action_does_not_invoke_level_resolution(monkeypatch):
    context, session, draft = bundle()

    def forbidden(**kwargs):
        raise AssertionError("ineligible proposals cannot ask for a level step")

    monkeypatch.setattr("app.domains.planning.numeric_adaptation.resolve_prescription_intensity_step", forbidden)
    from app.domains.planning.execution_adaptation import AdaptationSignalConfidence
    for confidence in (AdaptationSignalConfidence.LOW, AdaptationSignalConfidence.INSUFFICIENT):
        result = resolve(context, session, draft, directional(context, session, confidence=confidence))
        assert result.resolutions[0].level_resolution is None


def test_legacy_c4_c5_hashes_ignore_absent_level_metadata():
    from tests.test_planning_adaptation import planning_item
    context, session, draft = bundle()
    # Reuse the existing C.4 transport fixture, adding no ladder or numeric step.
    current = phase_targets(draft.definition)[0]
    item = planning_item(context, sport="running", session_type=session.session_type.value, target_kind="RUN_PACE",
                         kind="INCREASE_TARGET", direction="FASTER_PACE",
                         current=(current.resolved_minimum, current.resolved_maximum, current.resolved_unit),
                         proposed=(current.resolved_minimum, current.resolved_maximum, current.resolved_unit))
    legacy = item.model_dump(mode="python")
    for row in legacy["items"]:
        row.pop("prescription_level_transition")
    assert context_fingerprint({"input": item}) == context_fingerprint({"input": legacy})


def test_acceptance_does_not_recompute_c6(monkeypatch):
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication
    from tests.test_planning_preview_application import seeded
    engine, preview_id, athlete_id, user_id, stored = seeded()

    def forbidden(**kwargs):
        raise AssertionError("acceptance must not recompute C.6")

    monkeypatch.setattr("app.domains.planning.numeric_adaptation.resolve_prescription_intensity_step", forbidden)
    with Session(engine) as db:
        app = PlanningPreviewApplication(db)
        app.accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role="athlete")
        assert app.artifact(app.get(preview_id=preview_id, athlete_id=athlete_id)) == stored
    engine.dispose()


def test_overlapping_ftp_zone_cannot_identify_prescription_level():
    from app.domains.performance_profile.zones import (
        PerformanceReference, Sport, MetricType, Unit, cycling_power_zones,
    )
    from tests.test_planning_preview_artifact import artifact
    from app.domains.planning.planning_adaptation import with_planning_adaptation

    context, session, draft = bundle("cycling", SessionType.BIKE_THRESHOLD)
    target = phase_targets(draft.definition)[0]
    zones = cycling_power_zones(PerformanceReference(
        sport=Sport.CYCLING, metric=MetricType.POWER,
        value=float(context.performance.cycling_ftp_watts), unit=Unit.WATT,
    ))
    threshold_zone = next(zone for zone in zones.zones if zone.number == 4)
    assert (target.resolved_minimum, target.resolved_maximum) == (190, 210)
    assert (threshold_zone.lower, threshold_zone.upper) == (180, 210)
    assert threshold_zone.lower < target.resolved_minimum < threshold_zone.upper
    # These are real outputs of two different production semantics. Overlap
    # never registers the zone as a prescription level or as a step candidate.
    result = resolve(context, session, draft)
    numeric = result.resolutions[0]
    assert numeric.level_resolution.status == LevelResolutionStatus.NO_SUPPORTED_LADDER
    assert numeric.level_resolution.level_before is numeric.level_resolution.level_after is None
    assert numeric.status == "NO_SAFE_STEP" and numeric.proposed_range is None
    projection = normalize_numeric_planning_adaptation(result)
    assert artifact(with_planning_adaptation(context, projection.planning_input)) == artifact(context)


@pytest.mark.parametrize("case", ["mismatch", "minimum", "maximum"])
def test_unavailable_neighbor_diagnostic_survives_c5_c4_and_preview(monkeypatch, case):
    from tests.test_planning_preview_artifact import artifact
    from app.domains.planning.planning_adaptation import with_planning_adaptation
    context, session, draft, level = observed_level()
    # Contract composition using only the existing target, not a production
    # ladder provider. There is no invented alternative and no successful step.
    observed = singleton(context, level)
    if case == "mismatch":
        unrelated = phase_targets(bundle("running", SessionType.RUN_EASY)[2].definition)[0]
        current = PrescriptionTargetRange(minimum=Decimal(str(unrelated.resolved_minimum)),
                                          maximum=Decimal(str(unrelated.resolved_maximum)), unit=unrelated.resolved_unit)
        diagnostic = identify_current_level(context=context, ladder=observed, current_range=current)
        from tests.test_numeric_adaptation import replace_work_targets
        draft = replace_work_targets(draft, resolved_minimum=float(current.minimum), resolved_maximum=float(current.maximum))
        expected = "CURRENT_LEVEL_NOT_IDENTIFIED"
    else:
        direction = LevelStepDirection.REGRESSION if case == "minimum" else LevelStepDirection.PROGRESSION
        diagnostic = resolve_adjacent_level(context=context, ladder=observed, current_range=level.target_range, direction=direction)
        expected = "LEVEL_BOUNDARY"
    monkeypatch.setattr("app.domains.planning.numeric_adaptation.resolve_prescription_intensity_step", lambda **kwargs: diagnostic)
    result = resolve(context, session, draft, increasing=case != "minimum")
    assert result.resolutions[0].status == "NO_SAFE_STEP"
    assert result.resolutions[0].reason_codes == (expected,)
    assert result.resolutions[0].proposed_range is None
    projection = normalize_numeric_planning_adaptation(result)
    assert projection.decisions[0].status == "SKIPPED_NO_SAFE_STEP"
    assert artifact(with_planning_adaptation(context, projection.planning_input)) == artifact(context)
