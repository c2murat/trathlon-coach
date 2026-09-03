from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from app.domains.planning.adaptive_targets import ADAPTIVE_PRESCRIPTION_VERSION, adapt_target
from app.domains.planning.contracts import (
    AdaptiveCapabilityPointSnapshot, AdaptiveCapabilitySnapshot, AdaptiveRepeatSnapshot,
    PerformanceSnapshot, context_fingerprint,
)
from app.domains.planning.models import WorkoutTarget
from app.domains.planning.session_planning import SessionType
from app.domains.planning.season_structure import SeasonPhase
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_workout_builder import phase_targets, prescription, source
from tests.test_session_planning import build


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
