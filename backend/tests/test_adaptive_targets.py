from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from app.domains.planning.adaptive_targets import ADAPTIVE_PRESCRIPTION_VERSION, adapt_target
from app.domains.planning.contracts import (
    AdaptiveCapabilityPointSnapshot, AdaptiveCapabilitySnapshot, AdaptiveRepeatSnapshot,
    PerformanceSnapshot, context_fingerprint,
)
from app.domains.planning.models import WorkoutTarget
from app.domains.planning.session_planning import SessionType, _type_sequence
from app.domains.planning.season_structure import SeasonPhase
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_workout_builder import phase_targets, prescription, source
from tests.test_session_planning import build
from tests.test_weekly_budget import context, goal


CONFIG = WorkoutBuilderConfig(version=ADAPTIVE_PRESCRIPTION_VERSION, algorithm_version=ADAPTIVE_PRESCRIPTION_VERSION)


def point(dimension, value, confidence="HIGH", days=5, support=4, sources=()):
    return AdaptiveCapabilityPointSnapshot(
        dimension=dimension, usable_value=Decimal(str(value)), confidence=confidence,
        days_since_evidence=days, support_count=support, source_activity_ids=tuple(sources),
    )


def snapshot(*, run=(), bike=(), swim=(), repeats=(), swim_repeats=()):
    return AdaptiveCapabilitySnapshot(
        algorithm_version="0.8G.2A", cutoff_date=source()[0].request.planning_date,
        running_duration=tuple(run), cycling_duration=tuple(bike), swimming_distance=tuple(swim),
        running_repeats=tuple(repeats),
        swimming_repeats=tuple(swim_repeats),
    )


def with_snapshot(context, value):
    updated = context.model_copy(update={"adaptive_capability": value})
    payload = updated.model_dump(mode="python", exclude={"fingerprint"})
    return updated.model_copy(update={"fingerprint": context_fingerprint(payload)})


def work_target(context, session_type, discipline="running", *, week=1, phase=SeasonPhase.BUILD):
    _, base_session = source()
    session = prescription(base_session, session_type, discipline)
    session = session.model_copy(update={"date": context.request.planning_date + timedelta(days=7 * week), "phase": phase})
    return phase_targets(build_structured_workout(context, session, CONFIG).definition)[0]


def test_same_threshold_fast_run_capability_adapts_interval_but_not_easy():
    base, _ = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("260")))
    athlete_a = with_snapshot(base, snapshot(run=(point(180, 217),)))
    athlete_b = with_snapshot(base, snapshot())
    interval_a = work_target(athlete_a, SessionType.RUN_INTERVAL)
    interval_b = work_target(athlete_b, SessionType.RUN_INTERVAL)
    assert interval_a.resolved_minimum < interval_b.resolved_minimum
    assert interval_a.resolved_maximum < interval_b.resolved_maximum
    assert interval_a.adaptation.capability_value == 217
    assert work_target(athlete_a, SessionType.RUN_EASY).resolved_minimum == work_target(athlete_b, SessionType.RUN_EASY).resolved_minimum


def test_running_duration_matching_and_interpolation_never_uses_absolute_best():
    base, base_session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("260")))
    snap = snapshot(run=(point(60, 201), point(120, 211), point(180, 217), point(300, 229)))
    session = prescription(base_session, SessionType.RUN_INTERVAL).model_copy(update={"phase": SeasonPhase.BUILD})
    baseline = WorkoutTarget(metric="pace", mode="percent_reference", reference="threshold_pace", minimum=.9, maximum=.96, reference_value=260, reference_unit="seconds_per_km", resolved_minimum=234, resolved_maximum=250, resolved_unit="seconds_per_km")
    results = [adapt_target(target=baseline, snapshot=snap, session=session, family="interval", effort_seconds=seconds, repeat_count=4) for seconds in (60, 120, 180, 240, 300)]
    assert [item.adaptation.capability_dimension for item in results] == [60, 120, 180, 240, 300]
    assert [item.adaptation.capability_value for item in results] == [201, 211, 217, 223, 229]
    assert all(item.resolved_minimum > item.adaptation.capability_value * .95 for item in results)


def test_repeat_like_support_is_traced_and_more_repetitions_are_more_conservative():
    _, session = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("260")))
    session = prescription(session, SessionType.RUN_INTERVAL).model_copy(update={"phase": SeasonPhase.BUILD})
    repeat = AdaptiveRepeatSnapshot(repeat_count=6, typical_duration_seconds=175, typical_distance_m=800, representative_value=Decimal("219"), confidence="HIGH", days_since_evidence=8)
    snap = snapshot(run=(point(180, 217),), repeats=(repeat,))
    baseline = WorkoutTarget(metric="pace", mode="percent_reference", reference="threshold_pace", minimum=.9, maximum=.96, reference_value=260, reference_unit="seconds_per_km", resolved_minimum=234, resolved_maximum=250, resolved_unit="seconds_per_km")
    low_volume = adapt_target(target=baseline, snapshot=snap, session=session, family="interval", effort_seconds=180, repeat_count=2)
    high_volume = adapt_target(target=baseline, snapshot=snap, session=session, family="interval", effort_seconds=180, repeat_count=8)
    assert low_volume.adaptation.repeat_evidence_used
    assert high_volume.adaptation.repeat_factor < low_volume.adaptation.repeat_factor
    assert high_volume.resolved_minimum > low_volume.resolved_minimum


def test_bike_interval_uses_power_duration_but_endurance_and_long_do_not():
    base, _ = source(PerformanceSnapshot(cycling_ftp_watts=Decimal("140")))
    athlete_a = with_snapshot(base, snapshot(bike=(point(180, 183), point(300, 183))))
    athlete_b = with_snapshot(base, snapshot())
    assert work_target(athlete_a, SessionType.BIKE_INTERVAL, "cycling").resolved_maximum > work_target(athlete_b, SessionType.BIKE_INTERVAL, "cycling").resolved_maximum
    for kind in (SessionType.BIKE_ENDURANCE, SessionType.BIKE_LONG):
        assert work_target(athlete_a, kind, "cycling").resolved_maximum == work_target(athlete_b, kind, "cycling").resolved_maximum


def test_swim_200_quality_uses_reliable_evidence_but_easy_does_not():
    base, _ = source(PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110")))
    athlete_a = with_snapshot(base, snapshot(swim=(point(200, 99),)))
    athlete_b = with_snapshot(base, snapshot())
    quality_a = work_target(athlete_a, SessionType.SWIM_INTERVAL, "swimming", week=2)
    quality_b = work_target(athlete_b, SessionType.SWIM_INTERVAL, "swimming", week=2)
    assert quality_a.adaptation.capability_dimension == 200
    assert quality_a.resolved_maximum < quality_b.resolved_maximum
    assert work_target(athlete_a, SessionType.SWIM_EASY, "swimming").resolved_maximum == work_target(athlete_b, SessionType.SWIM_EASY, "swimming").resolved_maximum


def test_swim_exact_medium_point_remains_anchor_when_slower_repeat_overlaps_source():
    shared = uuid4()
    repeat = AdaptiveRepeatSnapshot(
        repeat_count=8, typical_duration_seconds=205, typical_distance_m=184,
        representative_value=Decimal("103"), confidence="MEDIUM", days_since_evidence=18,
        source_activity_id=shared,
    )
    snap = snapshot(
        swim=(point(200, Decimal("98.9"), confidence="MEDIUM", days=18, support=8, sources=(shared,)),),
        swim_repeats=(repeat,),
    )
    base, session = source(PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110")))
    target = WorkoutTarget(metric="swim_pace", mode="percent_reference", reference="CSS", minimum=.85, maximum=.95, reference_value=110, reference_unit="seconds_per_100m", resolved_minimum=94, resolved_maximum=105, resolved_unit="seconds_per_100m")
    adapted = adapt_target(target=target, snapshot=snap, session=prescription(session, SessionType.SWIM_INTERVAL, "swimming").model_copy(update={"phase": SeasonPhase.BUILD}), family="interval", effort_meters=200, repeat_count=10)
    assert adapted.adaptation.capability_value == 98.9
    assert adapted.adaptation.repeat_evidence_used
    assert adapted.adaptation.repeat_source_overlap is True
    assert adapted.adaptation.blend_factor == .4
    assert adapted.resolved_minimum >= 97 and adapted.resolved_maximum <= 104


def test_independent_coherent_swim_repeat_reinforces_without_replacing_anchor():
    point_source, repeat_source = uuid4(), uuid4()
    repeat = AdaptiveRepeatSnapshot(repeat_count=6, typical_duration_seconds=200, typical_distance_m=200, representative_value=Decimal("100"), confidence="MEDIUM", days_since_evidence=10, source_activity_id=repeat_source)
    snap = snapshot(swim=(point(200, Decimal("98.9"), confidence="MEDIUM", sources=(point_source,)),), swim_repeats=(repeat,))
    _, session = source(PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110")))
    target = WorkoutTarget(metric="swim_pace", mode="percent_reference", reference="CSS", minimum=.85, maximum=.95, reference_value=110, reference_unit="seconds_per_100m", resolved_minimum=94, resolved_maximum=105, resolved_unit="seconds_per_100m")
    adapted = adapt_target(target=target, snapshot=snap, session=prescription(session, SessionType.SWIM_INTERVAL, "swimming").model_copy(update={"phase": SeasonPhase.BUILD}), family="interval", effort_meters=200, repeat_count=6)
    assert adapted.adaptation.capability_value == 98.9
    assert adapted.adaptation.repeat_source_overlap is False
    assert adapted.adaptation.blend_factor == .45


def test_swim_trace_survives_when_rounding_keeps_legacy_range():
    snap = snapshot(swim=(point(200, Decimal("99.5"), confidence="MEDIUM"),))
    _, session = source(PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110")))
    target = WorkoutTarget(metric="swim_pace", mode="percent_reference", reference="CSS", minimum=.9, maximum=.91, reference_value=110, reference_unit="seconds_per_100m", resolved_minimum=99, resolved_maximum=100, resolved_unit="seconds_per_100m")
    adapted = adapt_target(target=target, snapshot=snap, session=prescription(session, SessionType.SWIM_INTERVAL, "swimming").model_copy(update={"phase": SeasonPhase.BUILD}), family="interval", effort_meters=200, repeat_count=1)
    assert (adapted.resolved_minimum, adapted.resolved_maximum) == (99, 100)
    assert adapted.adaptation is not None


def test_low_missing_old_and_taper_capability_fall_back_safely():
    base, _ = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("260")))
    low = with_snapshot(base, snapshot(run=(point(180, 200, confidence="LOW"),)))
    missing = with_snapshot(base, snapshot())
    assert work_target(low, SessionType.RUN_INTERVAL).adaptation is None
    assert work_target(missing, SessionType.RUN_INTERVAL).adaptation is None
    high = with_snapshot(base, snapshot(run=(point(180, 217),)))
    assert work_target(high, SessionType.RUN_INTERVAL, phase=SeasonPhase.TAPER).adaptation is None


def test_capability_snapshot_is_deterministic_and_changes_context_fingerprint():
    base, _ = source()
    first = with_snapshot(base, snapshot(run=(point(180, 217),)))
    repeated = with_snapshot(base, snapshot(run=(point(180, 217),)))
    changed = with_snapshot(base, snapshot(run=(point(180, 220),)))
    assert first.fingerprint == repeated.fingerprint
    assert first.fingerprint != changed.fingerprint != base.fingerprint


def test_capability_changes_only_workout_targets_not_macro_session_plan():
    base, _ = source(PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("260")))
    adaptive = with_snapshot(base, snapshot(run=(point(180, 217),)))
    baseline_plan = build(base)[0]
    adaptive_plan = build(adaptive)[0]
    assert adaptive_plan.weeks == baseline_plan.weeks


def test_single_a_triathlon_keeps_quality_selection_independent_from_capability():
    event = goal(sports=("swim", "bike", "run")).model_copy(update={
        "event_date": date(2026, 10, 17),
        "event_format": "triathlon",
        "priority": "A",
        "role": "primary",
    })
    performance = PerformanceSnapshot(
        cycling_ftp_watts=Decimal("155"),
        running_threshold_pace_seconds_per_km=Decimal("250"),
        swimming_css_seconds_per_100m=Decimal("110"),
    )
    baseline = context(goals=(event,)).model_copy(update={"performance": performance})
    repeat = AdaptiveRepeatSnapshot(
        repeat_count=6, typical_duration_seconds=190, typical_distance_m=800,
        representative_value=Decimal("225"), confidence="HIGH", days_since_evidence=7,
    )
    adaptive = with_snapshot(baseline, snapshot(
        run=(point(60, 205, "HIGH"), point(120, 212, "HIGH"), point(180, 220, "MEDIUM")),
        repeats=(repeat,),
    ))

    baseline_plan = build(baseline)[0]
    adaptive_plan = build(adaptive)[0]
    assert adaptive_plan.weeks == baseline_plan.weeks
    assert len(adaptive_plan.weeks) == len(baseline_plan.weeks)
    assert all(
        len(adaptive_week.sessions) == len(baseline_week.sessions)
        and adaptive_week.planned_load == baseline_week.planned_load
        and adaptive_week.budget_target_load == baseline_week.budget_target_load
        and [item.target_duration_minutes for item in adaptive_week.sessions]
        == [item.target_duration_minutes for item in baseline_week.sessions]
        for adaptive_week, baseline_week in zip(adaptive_plan.weeks, baseline_plan.weeks)
    )

    sessions = tuple(item for week in adaptive_plan.weeks for item in week.sessions)
    interval = next(item for item in sessions if item.session_type is SessionType.RUN_INTERVAL)
    assert interval.phase in {SeasonPhase.BUILD, SeasonPhase.SPECIFIC}
    assert {item.discipline for item in sessions} >= {"running", "cycling", "swimming"}
    assert not any(item.phase is SeasonPhase.RECOVERY for item in sessions)

    taper = tuple(item for item in sessions if item.phase is SeasonPhase.TAPER)
    assert taper and all((event.event_date - item.date).days <= 14 for item in taper)
    assert not any(item.session_type is SessionType.RUN_INTERVAL for item in taper)

    representative = {
        discipline: next(item for item in sessions if item.discipline == discipline and item.target_duration_minutes)
        for discipline in ("running", "cycling", "swimming")
    }
    workouts = {
        discipline: build_structured_workout(adaptive, session, CONFIG)
        for discipline, session in representative.items()
    }
    expected_references = {
        "running": ("threshold_pace", 250.0),
        "cycling": ("FTP", 155.0),
        "swimming": ("CSS", 110.0),
    }
    for discipline, draft in workouts.items():
        target = phase_targets(draft.definition)[0]
        reference, value = expected_references[discipline]
        assert target.reference == reference
        assert target.reference_value == value

    interval_target = phase_targets(build_structured_workout(adaptive, interval, CONFIG).definition)[0]
    assert interval_target.reference == "threshold_pace"
    assert interval_target.reference_value == 250.0
    assert interval_target.adaptation is None
    five_min_reference = WorkoutTarget(
        metric="pace", mode="percent_reference", reference="threshold_pace",
        minimum=.9, maximum=.96, reference_value=250, reference_unit="seconds_per_km",
        resolved_minimum=225, resolved_maximum=240, resolved_unit="seconds_per_km",
    )
    assert adapt_target(
        target=five_min_reference, snapshot=adaptive.adaptive_capability,
        session=interval, family="interval", effort_seconds=300, repeat_count=5,
    ) == five_min_reference

    compatible = with_snapshot(baseline, snapshot(run=(point(240, 220, "HIGH"),)))
    compatible_plan = build(compatible)[0]
    assert compatible_plan.weeks == baseline_plan.weeks
    compatible_interval = next(
        item for week in compatible_plan.weeks for item in week.sessions
        if item.session_type is SessionType.RUN_INTERVAL
    )
    compatible_target = phase_targets(
        build_structured_workout(compatible, compatible_interval, CONFIG).definition,
    )[0]
    assert compatible_target.adaptation is not None
    assert (compatible_target.resolved_minimum, compatible_target.resolved_maximum) != (
        interval_target.resolved_minimum, interval_target.resolved_maximum,
    )


def test_single_a_triathlon_running_quality_choice_is_driven_by_exposure_deficit():
    low_interval_exposure = {
        SessionType.RUN_TEMPO: 3,
        SessionType.RUN_THRESHOLD: 2,
        SessionType.RUN_INTERVAL: 0,
    }
    high_interval_exposure = {
        SessionType.RUN_TEMPO: 0,
        SessionType.RUN_THRESHOLD: 2,
        SessionType.RUN_INTERVAL: 5,
    }

    deficient = _type_sequence("running", SeasonPhase.BUILD, 3, 0, low_interval_exposure)
    repeated = _type_sequence("running", SeasonPhase.BUILD, 3, 0, low_interval_exposure)
    saturated = _type_sequence("running", SeasonPhase.BUILD, 3, 0, high_interval_exposure)

    assert deficient == repeated
    assert deficient == [SessionType.RUN_LONG, SessionType.RUN_INTERVAL, SessionType.RUN_EASY]
    assert saturated == [SessionType.RUN_LONG, SessionType.RUN_TEMPO, SessionType.RUN_EASY]
