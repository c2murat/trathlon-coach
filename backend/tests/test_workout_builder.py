from decimal import Decimal
import json
from math import isfinite

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import PerformanceSnapshot
from app.domains.planning.models import StructuredWorkoutDefinition
from app.domains.planning.session_planning import SessionType
from app.domains.planning.workout_builder import (
    WorkoutBuilderConfig, WorkoutDecisionCode, WorkoutWarningCode,
    build_structured_workout, validate_structured_workout_draft,
    structured_workout_canonical_json, structured_workout_payload,
    workout_duration_seconds,
)
from tests.test_session_planning import build, with_running_frequency
from tests.test_weekly_budget import context, goal


CONFIG = WorkoutBuilderConfig(version="workout-1", algorithm_version="workout-algorithm-1")


def source(performance=None):
    ctx = context(windows=with_running_frequency())
    if performance is not None:
        ctx = ctx.model_copy(update={"performance": performance})
    plan, _, _, _ = build(ctx)
    return ctx, next(item for item in plan.weeks[0].sessions if item.discipline == "running")


def prescription(session, session_type, discipline="running", minutes=60):
    return session.model_copy(update={
        "session_type": session_type, "discipline": discipline,
        "target_duration_minutes": minutes,
    })


def targets(definition):
    result = []
    def visit(node):
        if node.kind == "step" and node.target and node.target.metric != "none":
            result.append(node.target)
        for child in node.steps or ():
            visit(child)
    for node in definition.steps:
        visit(node)
    return result


def test_run_easy_uses_threshold_pace_with_correct_slower_semantics():
    ctx, session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300")))
    draft = build_structured_workout(ctx, prescription(session, SessionType.RUN_EASY, minutes=45), CONFIG)
    target = targets(draft.definition)[0]
    assert workout_duration_seconds(draft.definition) == 2700
    assert target.reference == "threshold_pace"
    assert Decimal(str(target.minimum)) * 300 > 300
    assert draft.target_provenance.reference_value == 300
    assert WorkoutDecisionCode.TARGET_FROM_THRESHOLD_PACE in {item.code for item in draft.decisions}


def test_run_easy_without_reference_falls_back_to_rpe():
    ctx, session = source(PerformanceSnapshot())
    draft = build_structured_workout(ctx, prescription(session, SessionType.RUN_EASY, minutes=45), CONFIG)
    assert targets(draft.definition)[0].metric == "rpe"
    assert WorkoutWarningCode.WORKOUT_TARGET_FALLBACK_TO_RPE in {item.code for item in draft.warnings}


def test_run_threshold_has_repeats_recovery_and_exact_duration():
    ctx, session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300")))
    draft = build_structured_workout(ctx, prescription(session, SessionType.RUN_THRESHOLD), CONFIG)
    assert [item.kind for item in draft.definition.steps] == ["step", "repeat", "step"]
    repeat = draft.definition.steps[1]
    assert repeat.repetitions >= 2
    assert {item.phase for item in repeat.steps} == {"work", "recovery"}
    assert workout_duration_seconds(draft.definition) == 3600


def test_short_threshold_adapts_without_negative_or_impossible_repeat():
    ctx, session = source()
    draft = build_structured_workout(ctx, prescription(session, SessionType.RUN_THRESHOLD, minutes=20), CONFIG)
    assert workout_duration_seconds(draft.definition) == 1200
    assert all(item.duration is None or item.duration.seconds > 0 for item in draft.definition.steps)


def test_run_interval_is_faster_than_threshold_pace_and_repeated():
    ctx, session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300")))
    draft = build_structured_workout(ctx, prescription(session, SessionType.RUN_INTERVAL), CONFIG)
    target = targets(draft.definition)[0]
    assert Decimal(str(target.maximum)) * 300 < 300
    assert any(item.kind == "repeat" for item in draft.definition.steps)


def test_bike_endurance_threshold_and_interval_use_ftp_ranges():
    ctx, session = source(PerformanceSnapshot(cycling_ftp_watts=Decimal("250")))
    for kind, relation in (
        (SessionType.BIKE_ENDURANCE, "below"),
        (SessionType.BIKE_THRESHOLD, "around"),
        (SessionType.BIKE_INTERVAL, "above"),
    ):
        draft = build_structured_workout(ctx, prescription(session, kind, "cycling"), CONFIG)
        target = targets(draft.definition)[0]
        assert target.metric == "power" and target.reference == "FTP"
        if relation == "below": assert Decimal(str(target.maximum)) * 250 < 250
        if relation == "around": assert Decimal(str(target.minimum)) * 250 < 250 < Decimal(str(target.maximum)) * 250
        if relation == "above": assert Decimal(str(target.minimum)) * 250 > 250


def test_bike_uses_threshold_hr_then_rpe_when_ftp_is_missing():
    ctx, session = source(PerformanceSnapshot(cycling_threshold_heart_rate_bpm=165))
    hr = build_structured_workout(ctx, prescription(session, SessionType.BIKE_THRESHOLD, "cycling"), CONFIG)
    assert targets(hr.definition)[0].reference == "threshold_hr"
    ctx = ctx.model_copy(update={"performance": PerformanceSnapshot()})
    fallback = build_structured_workout(ctx, prescription(session, SessionType.BIKE_INTERVAL, "cycling"), CONFIG)
    assert targets(fallback.definition)[0].metric == "rpe"


def test_swim_css_semantics_fallback_and_technique_are_safe():
    ctx, session = source(PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("100")))
    aerobic = build_structured_workout(ctx, prescription(session, SessionType.SWIM_AEROBIC, "swimming"), CONFIG)
    interval = build_structured_workout(ctx, prescription(session, SessionType.SWIM_INTERVAL, "swimming"), CONFIG)
    assert Decimal(str(targets(aerobic.definition)[0].minimum)) * 100 > 100
    assert Decimal(str(targets(interval.definition)[0].maximum)) * 100 < 100
    technique = build_structured_workout(ctx, prescription(session, SessionType.SWIM_TECHNIQUE, "swimming", 45), CONFIG)
    assert technique.definition.steps[0].instructions == "technique"
    assert not any(word in str(technique.definition).lower() for word in ("catch-up", "single-arm", "fins", "paddles"))
    ctx = ctx.model_copy(update={"performance": PerformanceSnapshot()})
    assert targets(build_structured_workout(ctx, prescription(session, SessionType.SWIM_AEROBIC, "swimming"), CONFIG).definition)[0].metric == "rpe"


def test_relative_targets_snapshot_resolved_power_run_and_css_ranges():
    performance = PerformanceSnapshot(
        cycling_ftp_watts=Decimal("250"),
        running_threshold_pace_seconds_per_km=Decimal("240"),
        swimming_css_seconds_per_100m=Decimal("100"),
    )
    ctx, session = source(performance)
    power = targets(build_structured_workout(ctx, prescription(session, SessionType.BIKE_EASY, "cycling"), CONFIG).definition)[0]
    run = targets(build_structured_workout(ctx, prescription(session, SessionType.RUN_EASY), CONFIG).definition)[0]
    swim = targets(build_structured_workout(ctx, prescription(session, SessionType.SWIM_EASY, "swimming"), CONFIG).definition)[0]
    assert (power.reference_value, power.resolved_minimum, power.resolved_maximum, power.resolved_unit) == (250, 125, 163, "watts")
    assert (run.reference_value, run.resolved_minimum, run.resolved_maximum, run.resolved_unit) == (240, 276, 324, "seconds_per_km")
    assert (swim.reference_value, swim.resolved_minimum, swim.resolved_maximum, swim.resolved_unit) == (100, 110, 125, "seconds_per_100m")


def test_missing_references_never_create_zero_resolved_targets():
    ctx, session = source(PerformanceSnapshot())
    for kind, discipline in ((SessionType.BIKE_EASY, "cycling"), (SessionType.RUN_EASY, "running"), (SessionType.SWIM_EASY, "swimming")):
        target = targets(build_structured_workout(ctx, prescription(session, kind, discipline), CONFIG).definition)[0]
        assert target.reference_value is None
        assert target.resolved_minimum is None and target.resolved_maximum is None


def test_strength_is_generic_and_does_not_invent_exercises_sets_or_weight():
    ctx, session = source()
    draft = build_structured_workout(ctx, prescription(session, SessionType.GENERAL_STRENGTH, "strength", 40), CONFIG)
    serialized = str(draft.definition.model_dump(mode="json")).lower()
    assert draft.definition.steps[0].instructions == "general strength"
    assert targets(draft.definition)[0].metric == "rpe"
    assert not any(word in serialized for word in ("squat", "deadlift", "kilograms"))


def test_competition_returns_explicit_non_buildable_result():
    event = goal(days=6)
    ctx = context(goals=(event,), horizon=event.event_date)
    plan, _, _, _ = build(ctx)
    session = next(item for item in plan.weeks[0].sessions if item.session_type is SessionType.COMPETITION)
    draft = build_structured_workout(ctx, session, CONFIG)
    assert not draft.buildable and draft.definition is None
    assert WorkoutWarningCode.STRUCTURED_WORKOUT_NOT_APPLICABLE in {item.code for item in draft.warnings}
    assert validate_structured_workout_draft(draft, session) == ()


@pytest.mark.parametrize("minutes", [30, 45, 60, 75, 90, 120])
def test_duration_is_exact_across_supported_lengths(minutes):
    ctx, session = source()
    for kind in (SessionType.RUN_EASY, SessionType.RUN_THRESHOLD, SessionType.RUN_INTERVAL):
        draft = build_structured_workout(ctx, prescription(session, kind, minutes=minutes), CONFIG)
        assert workout_duration_seconds(draft.definition) == minutes * 60


def test_determinism_config_fingerprint_v1_roundtrip_and_no_input_mutation():
    ctx, session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300")))
    session = prescription(session, SessionType.RUN_THRESHOLD)
    original = session.model_dump()
    first = build_structured_workout(ctx, session, CONFIG)
    repeated = build_structured_workout(ctx, session, CONFIG)
    changed = build_structured_workout(ctx, session, CONFIG.model_copy(update={"run_pace_threshold": (Decimal("0.95"), Decimal("1.01")), "version": "workout-2"}))
    assert first == repeated and first.fingerprint == repeated.fingerprint
    assert first.fingerprint != changed.fingerprint and first.definition != changed.definition
    assert StructuredWorkoutDefinition.model_validate(first.definition.model_dump(mode="json")) == first.definition
    assert session.model_dump() == original


def test_invalid_references_fall_back_without_absurd_target():
    ctx, session = source(PerformanceSnapshot(
        running_threshold_pace_seconds_per_km=Decimal("0"),
        cycling_ftp_watts=Decimal("0"), swimming_css_seconds_per_100m=Decimal("0"),
        running_threshold_heart_rate_bpm=0,
    ))
    for kind, discipline in (
        (SessionType.RUN_EASY, "running"),
        (SessionType.BIKE_ENDURANCE, "cycling"),
        (SessionType.SWIM_AEROBIC, "swimming"),
    ):
        draft = build_structured_workout(ctx, prescription(session, kind, discipline), CONFIG)
        assert targets(draft.definition)[0].metric == "rpe"


def test_config_and_draft_validator_reject_invalid_ranges_duration_and_sport():
    with pytest.raises(ValidationError):
        WorkoutBuilderConfig(
            version="bad", algorithm_version="bad",
            run_pace_easy=(Decimal("1.30"), Decimal("1.10")),
        )
    ctx, session = source()
    session = prescription(session, SessionType.RUN_EASY, minutes=45)
    draft = build_structured_workout(ctx, session, CONFIG)
    bad_definition = draft.definition.model_copy(update={"sport": "cycling"})
    invalid = draft.model_copy(update={"definition": bad_definition})
    assert "WORKOUT_SPORT_MISMATCH" in {
        item.code for item in validate_structured_workout_draft(invalid, session)
    }
    short_step = draft.definition.steps[0].model_copy(update={
        "duration": draft.definition.steps[0].duration.model_copy(update={"seconds": 60}),
    })
    invalid = draft.model_copy(update={
        "definition": draft.definition.model_copy(update={"steps": [short_step]}),
    })
    assert "WORKOUT_DURATION_MISMATCH" in {
        item.code for item in validate_structured_workout_draft(invalid, session)
    }


@pytest.mark.parametrize(("kind", "discipline"), [
    (SessionType.RUN_EASY, "running"),
    (SessionType.RUN_THRESHOLD, "running"),
    (SessionType.RUN_INTERVAL, "running"),
    (SessionType.BIKE_ENDURANCE, "cycling"),
    (SessionType.BIKE_THRESHOLD, "cycling"),
    (SessionType.SWIM_AEROBIC, "swimming"),
    (SessionType.SWIM_THRESHOLD, "swimming"),
    (SessionType.GENERAL_STRENGTH, "strength"),
])
def test_v1_json_roundtrip_matches_future_orm_schema(kind, discipline):
    performance = PerformanceSnapshot(
        running_threshold_pace_seconds_per_km=Decimal("300"),
        cycling_ftp_watts=Decimal("250"),
        swimming_css_seconds_per_100m=Decimal("100"),
    )
    ctx, session = source(performance)
    session = prescription(session, kind, discipline)
    draft = build_structured_workout(ctx, session, CONFIG)
    payload = structured_workout_payload(draft.definition)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    rebuilt = StructuredWorkoutDefinition.model_validate(json.loads(encoded))
    assert structured_workout_payload(rebuilt) == payload
    assert workout_duration_seconds(rebuilt) == session.target_duration_minutes * 60
    assert draft.target_provenance is not None and draft.decisions
    assert all(not isinstance(value, Decimal) for value in _leaf_values(payload))


def _leaf_values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaf_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaf_values(item)
    else:
        yield value


def test_final_payload_pace_css_power_and_hr_semantics_survive_roundtrip():
    performance = PerformanceSnapshot(
        running_threshold_pace_seconds_per_km=Decimal("300"),
        cycling_ftp_watts=Decimal("250"),
        swimming_css_seconds_per_100m=Decimal("100"),
    )
    ctx, base = source(performance)
    cases = (
        (SessionType.RUN_EASY, "running", lambda target: target.minimum * 300 > 300),
        (SessionType.RUN_INTERVAL, "running", lambda target: target.maximum * 300 < 300),
        (SessionType.BIKE_ENDURANCE, "cycling", lambda target: target.maximum * 250 < 250),
        (SessionType.BIKE_THRESHOLD, "cycling", lambda target: target.minimum * 250 < 250 < target.maximum * 250),
        (SessionType.BIKE_INTERVAL, "cycling", lambda target: target.minimum * 250 > 250),
        (SessionType.SWIM_AEROBIC, "swimming", lambda target: target.minimum * 100 > 100),
        (SessionType.SWIM_INTERVAL, "swimming", lambda target: target.maximum * 100 < 100),
    )
    for kind, discipline, assertion in cases:
        draft = build_structured_workout(ctx, prescription(base, kind, discipline), CONFIG)
        rebuilt = StructuredWorkoutDefinition.model_validate(structured_workout_payload(draft.definition))
        target = targets(rebuilt)[0]
        assert assertion(target)
        assert isfinite(target.minimum) and isfinite(target.maximum)

    hr_context = ctx.model_copy(update={
        "performance": PerformanceSnapshot(cycling_threshold_heart_rate_bpm=165),
    })
    hr = build_structured_workout(hr_context, prescription(base, SessionType.BIKE_THRESHOLD, "cycling"), CONFIG)
    target = targets(StructuredWorkoutDefinition.model_validate(structured_workout_payload(hr.definition)))[0]
    assert target.metric == "heart_rate" and target.reference == "threshold_hr"
    assert target.mode == "percent_reference"


@pytest.mark.parametrize("minutes", [30, 45, 60, 75, 90, 120])
def test_duration_and_repeat_expansion_survive_canonical_roundtrip(minutes):
    ctx, session = source()
    session = prescription(session, SessionType.RUN_INTERVAL, minutes=minutes)
    draft = build_structured_workout(ctx, session, CONFIG)
    rebuilt = StructuredWorkoutDefinition.model_validate(structured_workout_payload(draft.definition))
    assert workout_duration_seconds(rebuilt) == minutes * 60
    original_repeat = next((item for item in draft.definition.steps if item.kind == "repeat"), None)
    rebuilt_repeat = next((item for item in rebuilt.steps if item.kind == "repeat"), None)
    assert (rebuilt_repeat.repetitions if rebuilt_repeat else None) == (original_repeat.repetitions if original_repeat else None)


def test_float_quantization_non_finite_rejection_canonical_json_and_input_isolation():
    config = CONFIG.model_copy(update={
        "version": "precision-test",
        "run_pace_easy": (Decimal("1.1234567"), Decimal("1.2345678")),
    })
    ctx, session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300")))
    session = prescription(session, SessionType.RUN_EASY, minutes=45)
    draft = build_structured_workout(ctx, session, config)
    payload = structured_workout_payload(draft.definition)
    target = targets(StructuredWorkoutDefinition.model_validate(payload))[0]
    assert target.minimum == 1.123 and target.maximum == 1.235
    assert structured_workout_canonical_json(draft.definition) == structured_workout_canonical_json(draft.definition.model_copy(deep=True))
    json.dumps(payload, allow_nan=False)

    original_payload = structured_workout_payload(draft.definition)
    object.__setattr__(session, "target_duration_minutes", 1)
    object.__setattr__(ctx, "fingerprint", "b" * 64)
    object.__setattr__(config, "run_pace_easy", (Decimal("2"), Decimal("3")))
    assert structured_workout_payload(draft.definition) == original_payload

    for invalid in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
        with pytest.raises(ValidationError):
            WorkoutBuilderConfig(
                version="invalid", algorithm_version="invalid",
                run_pace_easy=(invalid, Decimal("1.2")),
            )


def test_competition_has_no_payload_to_roundtrip():
    event = goal(days=6)
    ctx = context(goals=(event,), horizon=event.event_date)
    plan, _, _, _ = build(ctx)
    session = next(item for item in plan.weeks[0].sessions if item.session_type is SessionType.COMPETITION)
    draft = build_structured_workout(ctx, session, CONFIG)
    assert draft.definition is None and not draft.buildable
