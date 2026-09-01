from decimal import Decimal
import json
from math import isfinite

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import PerformanceSnapshot
from app.domains.planning.models import StructuredWorkoutDefinition
from app.domains.planning.session_planning import SessionType
from app.domains.planning.season_structure import SeasonPhase
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


def phase_targets(definition, phase="work"):
    result=[]
    def visit(node):
        if node.kind=="step" and node.phase==phase and node.target and node.target.metric!="none": result.append(node.target)
        for child in node.steps or (): visit(child)
    for node in definition.steps: visit(node)
    return result


def leaves(definition):
    result=[]
    def visit(node):
        if node.kind=="step": result.append(node)
        for child in node.steps or (): visit(child)
    for node in definition.steps: visit(node)
    return result


def test_run_easy_uses_threshold_pace_with_correct_slower_semantics():
    ctx, session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300")))
    draft = build_structured_workout(ctx, prescription(session, SessionType.RUN_EASY, minutes=45), CONFIG)
    target = phase_targets(draft.definition)[0]
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
    target = phase_targets(draft.definition)[0]
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
        target = phase_targets(draft.definition)[0]
        assert target.metric == "power" and target.reference == "FTP"
        if relation == "below": assert Decimal(str(target.maximum)) * 250 < 250
        if relation == "around": assert Decimal(str(target.minimum)) * 250 < 250 < Decimal(str(target.maximum)) * 250
        if relation == "above": assert Decimal(str(target.minimum)) * 250 > 250


def test_quality_zone_order_and_resolved_examples_are_physiologically_distinct():
    performance=PerformanceSnapshot(cycling_ftp_watts=Decimal("140"),running_threshold_pace_seconds_per_km=Decimal("260"))
    ctx,session=source(performance)
    bike={kind:phase_targets(build_structured_workout(ctx,prescription(session,kind,"cycling"),CONFIG).definition)[0] for kind in (SessionType.BIKE_ENDURANCE,SessionType.BIKE_TEMPO,SessionType.BIKE_THRESHOLD,SessionType.BIKE_INTERVAL)}
    assert bike[SessionType.BIKE_ENDURANCE].maximum<=.72
    assert bike[SessionType.BIKE_TEMPO].maximum<bike[SessionType.BIKE_THRESHOLD].minimum
    assert bike[SessionType.BIKE_THRESHOLD].minimum<1<bike[SessionType.BIKE_THRESHOLD].maximum
    assert (bike[SessionType.BIKE_THRESHOLD].resolved_minimum,bike[SessionType.BIKE_THRESHOLD].resolved_maximum)==(133,147)
    assert bike[SessionType.BIKE_INTERVAL].minimum>1
    run={kind:phase_targets(build_structured_workout(ctx,prescription(session,kind),CONFIG).definition)[0] for kind in (SessionType.RUN_RECOVERY,SessionType.RUN_EASY,SessionType.RUN_TEMPO,SessionType.RUN_THRESHOLD,SessionType.RUN_INTERVAL)}
    assert run[SessionType.RUN_RECOVERY].minimum>=run[SessionType.RUN_EASY].maximum
    assert run[SessionType.RUN_EASY].minimum>run[SessionType.RUN_TEMPO].maximum
    assert run[SessionType.RUN_TEMPO].minimum>run[SessionType.RUN_THRESHOLD].minimum
    assert run[SessionType.RUN_INTERVAL].maximum<run[SessionType.RUN_THRESHOLD].minimum
    assert (run[SessionType.RUN_TEMPO].resolved_minimum,run[SessionType.RUN_TEMPO].resolved_maximum)==(268,281)
    assert (run[SessionType.RUN_THRESHOLD].resolved_minimum,run[SessionType.RUN_THRESHOLD].resolved_maximum)==(252,268)


def test_bike_long_uses_limited_sweet_spot_only_in_build_or_specific():
    ctx,session=source(PerformanceSnapshot(cycling_ftp_watts=Decimal("140")))
    base=prescription(session,SessionType.BIKE_LONG,"cycling",120).model_copy(update={"phase":SeasonPhase.BASE})
    build_session=base.model_copy(update={"phase":SeasonPhase.BUILD})
    base_draft=build_structured_workout(ctx,base,CONFIG)
    build_draft=build_structured_workout(ctx,build_session,CONFIG)
    assert all(Decimal(str(node.target.maximum))<=Decimal("0.72") for node in leaves(base_draft.definition) if node.phase=="work")
    sweet=[node for node in leaves(build_draft.definition) if node.phase=="work" and node.target and node.target.minimum==.88]
    assert sweet and all(node.target.maximum==.94 for node in sweet)
    assert sum(node.duration.seconds for node in sweet)*3 < workout_duration_seconds(build_draft.definition)


@pytest.mark.parametrize(("kind","discipline","minutes"),((SessionType.RUN_EASY,"running",45),(SessionType.BIKE_ENDURANCE,"cycling",60)))
def test_taper_keeps_short_activation_without_changing_total_duration_or_load(kind,discipline,minutes):
    performance=PerformanceSnapshot(cycling_ftp_watts=Decimal("140"),running_threshold_pace_seconds_per_km=Decimal("260"))
    ctx,session=source(performance)
    source_session=prescription(session,kind,discipline,minutes).model_copy(update={"phase":SeasonPhase.TAPER})
    draft=build_structured_workout(ctx,source_session,CONFIG)
    activation=[node for node in leaves(draft.definition) if node.title=="Activación corta"]
    assert activation and workout_duration_seconds(draft.definition)==minutes*60
    assert sum(node.duration.seconds for node in activation)<minutes*60//10
    assert max(node.duration.seconds for node in activation)<=60
    assert source_session.target_load==session.target_load


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
    assert Decimal(str(phase_targets(interval.definition)[0].maximum)) * 100 < 100
    technique = build_structured_workout(ctx, prescription(session, SessionType.SWIM_TECHNIQUE, "swimming", 45), CONFIG)
    drill = technique.definition.steps[1].steps[0]
    assert drill.phase == "drill" and drill.duration.mode == "distance" and drill.instructions
    assert not any(word in str(technique.definition).lower() for word in ("fins", "paddles"))
    ctx = ctx.model_copy(update={"performance": PerformanceSnapshot()})
    assert targets(build_structured_workout(ctx, prescription(session, SessionType.SWIM_AEROBIC, "swimming"), CONFIG).definition)[0].metric == "rpe"


def test_relative_targets_snapshot_resolved_power_run_and_css_ranges():
    performance = PerformanceSnapshot(
        cycling_ftp_watts=Decimal("250"),
        running_threshold_pace_seconds_per_km=Decimal("240"),
        swimming_css_seconds_per_100m=Decimal("100"),
    )
    ctx, session = source(performance)
    power = phase_targets(build_structured_workout(ctx, prescription(session, SessionType.BIKE_EASY, "cycling"), CONFIG).definition)[0]
    run = phase_targets(build_structured_workout(ctx, prescription(session, SessionType.RUN_EASY), CONFIG).definition)[0]
    swim = phase_targets(build_structured_workout(ctx, prescription(session, SessionType.SWIM_EASY, "swimming"), CONFIG).definition)[0]
    assert (power.reference_value, power.resolved_minimum, power.resolved_maximum, power.resolved_unit) == (250, 125, 163, "watts")
    assert (run.reference_value, run.resolved_minimum, run.resolved_maximum, run.resolved_unit) == (240, 276, 312, "seconds_per_km")
    assert (swim.reference_value, swim.resolved_minimum, swim.resolved_maximum, swim.resolved_unit) == (100, 110, 125, "seconds_per_100m")


def test_missing_references_never_create_zero_resolved_targets():
    ctx, session = source(PerformanceSnapshot())
    for kind, discipline in ((SessionType.BIKE_EASY, "cycling"), (SessionType.RUN_EASY, "running"), (SessionType.SWIM_EASY, "swimming")):
        target = targets(build_structured_workout(ctx, prescription(session, kind, discipline), CONFIG).definition)[0]
        assert target.reference_value is None
        assert target.resolved_minimum is None and target.resolved_maximum is None


def test_strength_is_executable_provider_neutral_and_does_not_invent_weight():
    ctx, session = source()
    draft = build_structured_workout(ctx, prescription(session, SessionType.GENERAL_STRENGTH, "strength", 40), CONFIG)
    serialized = str(draft.definition.model_dump(mode="json")).lower()
    assert all(item.phase == "strength" and item.title and item.movement_pattern for item in draft.definition.steps)
    assert all(item.sets and item.reps and item.rest_seconds for item in draft.definition.steps)
    assert targets(draft.definition)[0].metric == "rpe"
    assert "kilograms" not in serialized


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
        target = phase_targets(rebuilt)[0]
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
    target = phase_targets(StructuredWorkoutDefinition.model_validate(payload))[0]
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


def test_long_workouts_change_by_phase_without_changing_planned_duration():
    ctx, base = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300"), cycling_ftp_watts=Decimal("250")))
    for kind, discipline in ((SessionType.RUN_LONG, "running"), (SessionType.BIKE_LONG, "cycling")):
        maintenance = prescription(base, kind, discipline, 120).model_copy(update={"phase": SeasonPhase.MAINTENANCE})
        specific = maintenance.model_copy(update={"phase": SeasonPhase.SPECIFIC, "date": maintenance.date + __import__("datetime").timedelta(days=14)})
        simple = build_structured_workout(ctx, maintenance, CONFIG).definition
        quality = build_structured_workout(ctx, specific, CONFIG).definition
        assert not any(item.kind == "repeat" for item in simple.steps)
        assert any(item.kind == "repeat" for item in quality.steps)
        assert workout_duration_seconds(simple) == workout_duration_seconds(quality) == 7200


def test_swim_uses_distance_repeats_recovery_and_exact_estimated_duration():
    ctx, base = source(PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("100")))
    session = prescription(base, SessionType.SWIM_THRESHOLD, "swimming", 60)
    definition = build_structured_workout(ctx, session, CONFIG).definition
    repeat = next(item for item in definition.steps if item.kind == "repeat")
    assert repeat.steps[0].duration.mode == "distance"
    assert repeat.steps[0].duration.meters in {100, 200, 300, 400}
    assert repeat.steps[1].phase == "recovery" and repeat.steps[1].duration.mode == "time"
    assert workout_duration_seconds(definition) == 3600


def test_specific_swim_aerobic_contains_limited_css_exposure():
    ctx, base = source(PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("100")))
    session = prescription(base, SessionType.SWIM_AEROBIC, "swimming", 45).model_copy(update={"phase": SeasonPhase.SPECIFIC})
    definition = build_structured_workout(ctx, session, CONFIG).definition
    repeat = next(item for item in definition.steps if item.kind == "repeat")
    assert repeat.steps[0].title == "Series a ritmo CSS"
    assert repeat.steps[0].target.minimum == .97
    assert repeat.steps[1].phase == "recovery"
    assert workout_duration_seconds(definition) == 2700


def test_strength_variants_are_deterministic_balanced_and_duration_bounded():
    ctx, base = source()
    first = prescription(base, SessionType.GENERAL_STRENGTH, "strength", 40)
    second = first.model_copy(update={"date": first.date + __import__("datetime").timedelta(days=7)})
    a = build_structured_workout(ctx, first, CONFIG).definition
    repeated = build_structured_workout(ctx, first, CONFIG).definition
    b = build_structured_workout(ctx, second, CONFIG).definition
    assert a == repeated and [item.title for item in a.steps] != [item.title for item in b.steps]
    assert len({item.movement_pattern for item in a.steps}) == len(a.steps)
    assert workout_duration_seconds(a) == 2400
    assert all("kg" not in (item.instructions or "").lower() for item in a.steps)


def test_every_leaf_is_provider_neutral_and_semantically_explicit():
    ctx, base = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("300")))
    definition = build_structured_workout(ctx, prescription(base, SessionType.RUN_THRESHOLD), CONFIG).definition
    leaves=[]
    def visit(nodes):
        for node in nodes:
            if node.kind == "repeat": visit(node.steps)
            else: leaves.append(node)
    visit(definition.steps)
    assert all(item.phase and item.title and item.duration and item.target for item in leaves)
    assert all(item.duration.mode in {"time", "distance", "open"} for item in leaves)
    assert "garmin" not in structured_workout_canonical_json(definition).lower()


def test_step_role_targets_are_differentiated_for_bike_run_and_swim():
    performance = PerformanceSnapshot(
        cycling_ftp_watts=Decimal("250"), running_threshold_pace_seconds_per_km=Decimal("300"),
        swimming_css_seconds_per_100m=Decimal("100"),
    )
    ctx, base = source(performance)
    bike = build_structured_workout(ctx, prescription(base, SessionType.BIKE_ENDURANCE, "cycling"), CONFIG).definition
    assert bike.steps[0].target.maximum <= bike.steps[1].target.minimum
    assert bike.steps[1].target.model_dump() != bike.steps[-1].target.model_dump()
    run = build_structured_workout(ctx, prescription(base, SessionType.RUN_THRESHOLD), CONFIG).definition
    repeat = next(item for item in run.steps if item.kind == "repeat")
    assert run.steps[0].target.minimum > repeat.steps[0].target.maximum
    assert repeat.steps[1].target.minimum > repeat.steps[0].target.maximum
    swim = build_structured_workout(ctx, prescription(base, SessionType.SWIM_TECHNIQUE, "swimming", 45), CONFIG).definition
    drill = next(item for item in swim.steps if item.kind == "repeat").steps[0]
    assert len({swim.steps[0].target.minimum, drill.target.minimum, swim.steps[-1].target.minimum}) == 3


def test_strength_phase_reduces_volume_without_changing_duration():
    ctx, base = source()
    build_session = prescription(base, SessionType.GENERAL_STRENGTH, "strength", 40).model_copy(update={"phase": SeasonPhase.BUILD})
    recovery_session = build_session.model_copy(update={"phase": SeasonPhase.RECOVERY})
    build_definition = build_structured_workout(ctx, build_session, CONFIG).definition
    recovery_definition = build_structured_workout(ctx, recovery_session, CONFIG).definition
    assert {item.sets for item in build_definition.steps} == {3}
    assert {item.sets for item in recovery_definition.steps} == {2}
    assert len(build_definition.steps) == 6 and len(recovery_definition.steps) == 4
    assert {item.target.maximum for item in recovery_definition.steps} == {6}
    assert workout_duration_seconds(build_definition) == workout_duration_seconds(recovery_definition) == 2400


def test_strength_taper_is_not_a_copy_of_maintenance_and_variant_b_is_spanish():
    ctx, base = source()
    maintenance = prescription(base, SessionType.GENERAL_STRENGTH, "strength", 40)
    taper = maintenance.model_copy(update={"date": maintenance.date + __import__("datetime").timedelta(days=7), "phase": SeasonPhase.TAPER})
    normal = build_structured_workout(ctx, maintenance, CONFIG).definition
    reduced = build_structured_workout(ctx, taper, CONFIG).definition
    assert len(normal.steps) == 6 and len(reduced.steps) == 3
    assert {item.sets for item in reduced.steps} == {2}
    assert {item.reps for item in reduced.steps} == {6}
    assert any(item.title == "Sentadilla búlgara" for item in reduced.steps)
    assert workout_duration_seconds(normal) == workout_duration_seconds(reduced) == 2400
