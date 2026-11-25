from collections import Counter
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.planning.session_planning import SessionType, build_session_plan, _duration
from app.domains.planning.weekly_intent import (
    PlanningIntentShadowReport, WeeklyPlanningIntent, build_session_plan_with_shadow,
    compare_weekly_intent, UNKNOWN_MINUTES, UNKNOWN_VOLUME,
)
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_frequency_intent import tri
from tests.test_session_planning import build


@pytest.fixture(scope="module", params=[None, 5, 6, 7])
def frequency_case(request):
    ctx = tri(request.param)
    original, season, budgets, config = build(ctx)
    shadow_plan, report = build_session_plan_with_shadow(ctx, season, budgets, config)
    return ctx, original, shadow_plan, report, season, budgets, config


def profile_context():
    ctx = tri(6)
    goal = ctx.goals[0].model_copy(update={"category": "triathlon", "segments": tuple(
        s.model_copy(update={"distance_m": distance})
        for s, distance in zip(ctx.goals[0].segments, (3000, 110000, 30000), strict=True)
    )})
    history = []
    for w in ctx.training.windows:
        if w.days != 28:
            history.append(w)
            continue
        values = {
            "running": {"longest_duration_seconds": 6636},
            "cycling": {"longest_duration_seconds": 8517},
            "swimming": {"activity_count": 4, "duration_seconds": 6960},
            "strength": {"activity_count": 4, "duration_seconds": 5760},
        }
        history.append(w.model_copy(update={"sports": tuple(
            s.model_copy(update=values.get(s.sport, {})) for s in w.sports
        )}))
    return ctx.model_copy(update={
        "goals": (goal,), "training": ctx.training.model_copy(update={"windows": tuple(history)}),
        "performance": ctx.performance.model_copy(update={"swimming_css_seconds_per_100m": Decimal(110)}),
        "preferences": ctx.preferences.model_copy(update={"preferred_long_run_day": 4, "preferred_long_bike_day": 6}),
    })


@pytest.fixture(scope="module")
def profile():
    ctx = profile_context()
    original, season, budgets, config = build(ctx)
    plan, report = build_session_plan_with_shadow(ctx, season, budgets, config)
    return ctx, original, plan, report, season, budgets, config


def test_shadow_preserves_entire_plan_bytes_and_fingerprint(frequency_case):
    ctx, original, shadow_plan, report, *_ = frequency_case
    assert shadow_plan.model_dump_json() == original.model_dump_json()
    assert shadow_plan.fingerprint == original.fingerprint == report.plan_fingerprint
    assert "intent" not in original.model_dump_json()
    assert report.athlete_id == ctx.request.athlete_id


def test_null_legacy_and_targets_include_strength_in_total(frequency_case):
    ctx, _, plan, report, *_ = frequency_case
    intent = report.weeks[0].intent
    assert intent.requested_sessions == ctx.preferences.target_sessions_per_week
    expected = ctx.preferences.target_sessions_per_week or 5
    assert intent.resolved_sessions == len(plan.weeks[0].sessions) == expected
    assert intent.strength_sessions == 2
    assert intent.endurance_sessions == expected - 2
    assert sum(x.sessions for x in intent.desired_composition) == expected
    if intent.requested_sessions is None:
        assert intent.frequency_source == "legacy"
        assert intent.phase_adjusted_sessions is None
        assert intent.horizon_adjusted_sessions is None
        assert report.weeks[0].comparison.requested_target_met is None
        assert "LEGACY_RESOLVED_FREQUENCY" in {r.code for r in intent.frequency_reasons}
    else:
        assert intent.frequency_source == "explicit"
        assert intent.phase_adjusted_sessions == expected
        assert intent.horizon_adjusted_sessions == expected


def test_unknown_targets_are_not_filled_from_output(frequency_case):
    _, _, _, report, *_ = frequency_case
    for shadow in report.weeks:
        intent = shadow.intent
        assert intent.weekly_minutes_target is None
        assert intent.weekly_minutes_unknown_reason == UNKNOWN_MINUTES
        assert all(s.volume_minutes_target is None and s.volume_unknown_reason == UNKNOWN_VOLUME for s in intent.desired_composition)
        assert shadow.comparison.actual_minutes is not None
        assert not shadow.comparison.fully_satisfies_intent
        assert "WEEKLY_MINUTES_INTENT_UNKNOWN" in {d.code for d in shadow.comparison.discrepancies}


def test_composition_reasons_are_captured_from_selection_not_recomputed(profile):
    _, _, _, report, *_ = profile
    intent = report.weeks[0].intent
    composition = {x.sport: x for x in intent.desired_composition}
    assert {s: x.sessions for s, x in composition.items()} == {"running": 1, "cycling": 2, "swimming": 1, "strength": 2}
    bike = next(x for x in composition["cycling"].reasons if x.code == "SHARE_DIVIDED_BY_NEXT_COUNT")
    evidence = {x.name: x.value for x in bike.inputs}
    assert evidence["previous_count"] == 1
    assert Decimal(evidence["selection_score"]) == composition["cycling"].target_share / 2
    assert "STRENGTH_PREFERENCE_WITH_PHASE_HORIZON_CAPACITY" in {x.code for x in composition["strength"].reasons}


def test_run_long_cap_and_deload_provenance(profile):
    ctx, _, _, report, _, budgets, config = profile
    longs = [next(s for s in w.intent.session_intents if s.role == "RUN_LONG") for w in report.weeks[:4]]
    first = longs[0].progression
    assert first.historical_longest_minutes == Decimal("110.6")
    assert (first.pre_progression_minutes, first.proposed_minutes, first.cap_minutes, first.final_legacy_minutes) == (110, 120, 120, 120)
    cap_reason = next(r for r in first.decisions if r.code == "OBJECTIVE_DISTANCE_FRACTION_AND_SAFETY_BOUNDS")
    values = {v.name: v.value for v in cap_reason.inputs}
    assert values["distance_m"] == 30000
    assert values["objective_minutes"] == 135
    assert values["safety_cap"] == 120
    assert [s.progression.final_legacy_minutes for s in longs] == [120, 120, 120, 102]
    assert "DELOAD_REPLACES_CAPPED_PROPOSAL" in {r.code for r in longs[3].progression.decisions}
    assert any(d.code == "CAP_REACHED" and d.sport == "running" for d in report.weeks[0].comparison.discrepancies)
    # A non-default policy is observed; shadow has no hardcoded 120.
    custom = config.model_copy(update={"long_run_safety_cap_minutes": 115})
    traces = []
    value = _duration(ctx, budgets.budgets[0], "running", SessionType.RUN_LONG, custom, {}, traces)
    assert value == traces[0]["cap_minutes"] == 115


def test_strength_24_is_historical_not_structural(profile):
    _, _, _, report, *_ = profile
    for w in report.weeks:
        for session in w.intent.session_intents:
            if session.sport != "strength":
                continue
            trace = session.progression
            assert trace.historical_window_days == 28
            assert trace.historical_activity_count == 4
            assert trace.historical_duration_seconds == 5760
            assert trace.historical_mean_minutes == trace.final_legacy_minutes == 24
            assert trace.progression_source == "historical_28d_mean_capped_by_default"
            assert not trace.structurally_derived


def test_session_roles_and_doubles_use_existing_policy(profile):
    _, _, _, report, *_ = profile
    intent = report.weeks[0].intent
    assert Counter(s.role for s in intent.session_intents) == Counter({
        "RUN_LONG": 1, "BIKE_LONG": 1, "BIKE_TEMPO": 1, "SWIM_TECHNIQUE": 1, "GENERAL_STRENGTH": 2,
    })
    sessions = {s.intent_id: s for s in intent.session_intents}
    assert intent.doubles_enabled
    assert any({sessions[p.first_intent_id].sport, sessions[p.second_intent_id].sport} == {"swimming", "strength"}
               for p in intent.compatible_doubles)
    assert not any(sessions[p.first_intent_id].key_session and sessions[p.second_intent_id].key_session
                   for p in intent.compatible_doubles)


def test_comparison_detects_count_composition_role_duration_and_placement(profile):
    _, _, plan, report, *_ = profile
    intent = report.weeks[0].intent
    week = plan.weeks[0]
    run = next(s for s in week.sessions if s.session_type.value == "RUN_LONG")
    omitted = week.model_copy(update={"sessions": tuple(s for s in week.sessions if s is not run)})
    comparison = compare_weekly_intent(intent, omitted)
    assert {"SESSION_COUNT_MISMATCH", "SPORT_COMPOSITION_MISMATCH", "MISSING_ROLE"} <= {d.code for d in comparison.discrepancies}
    assert not comparison.resolved_generation_matches
    tampered = run.model_copy(update={"target_duration_minutes": 119, "date": run.date + timedelta(days=1)})
    changed = week.model_copy(update={"sessions": tuple(tampered if s is run else s for s in week.sessions)})
    comparison = compare_weekly_intent(intent, changed)
    assert {"UNEXPLAINED_DURATION", "PREFERRED_DAY_MISS"} <= {d.code for d in comparison.discrepancies}
    assert week.model_dump_json() == plan.weeks[0].model_dump_json()


def test_capacity_reduction_is_explained_before_placement():
    ctx = tri(6)
    ctx = ctx.model_copy(update={
        "goals": (ctx.goals[0].model_copy(update={"event_date": ctx.goals[0].event_date - timedelta(days=1)}),),
        "preferences": ctx.preferences.model_copy(update={"max_sessions_per_week": 6}),
    })
    _, season, budgets, config = build(ctx)
    plan, report = build_session_plan_with_shadow(ctx, season, budgets, config)
    race = next(w for w in report.weeks if any(g.occurs_this_week for g in w.intent.competition_context))
    assert race.intent.requested_sessions == 6
    assert race.intent.resolved_sessions == 6  # Capacity no longer rewrites intent.
    assert race.intent.frequency_capacity == race.comparison.actual_sessions == 5
    assert not race.comparison.resolved_generation_matches
    assert not race.comparison.requested_target_met
    assert "SESSION_COUNT_MISMATCH" in {d.code for d in race.comparison.discrepancies}
    capacity = next(r for r in race.intent.frequency_reasons if r.code == "CAPACITY_INCLUDES_COMPETITION_RESERVATION")
    assert {v.name: v.value for v in capacity.inputs}["competition_count"] == 1
    assert plan.weeks[-1].frequency_decision["generated_training_sessions"] == 5


def test_deep_immutability_and_round_trip(profile):
    _, _, _, report, *_ = profile
    intent = report.weeks[0].intent
    with pytest.raises(ValidationError, match="frozen"):
        intent.requested_sessions = 99
    with pytest.raises(ValidationError, match="frozen"):
        intent.session_intents[0].progression.final_legacy_minutes = 1
    assert isinstance(intent.reasons[0].inputs, tuple)
    assert WeeklyPlanningIntent.model_validate_json(intent.model_dump_json()) == intent
    assert PlanningIntentShadowReport.model_validate_json(report.model_dump_json()) == report


def test_determinism_and_athlete_isolation(profile):
    ctx, _, plan, report, season, budgets, config = profile
    repeated, repeated_report = build_session_plan_with_shadow(ctx, season, budgets, config)
    assert repeated.model_dump_json() == plan.model_dump_json()
    assert repeated_report.model_dump_json() == report.model_dump_json()
    other_id = UUID("20000000-0000-0000-0000-000000000002")
    other = ctx.model_copy(update={"request": ctx.request.model_copy(update={"athlete_id": other_id}), "fingerprint": "b" * 64})
    _, other_season, other_budgets, other_config = build(other)
    _, other_report = build_session_plan_with_shadow(other, other_season, other_budgets, other_config)
    assert all(w.intent.athlete_id == other_id for w in other_report.weeks)
    assert all(s.intent_id.startswith(str(other_id)) for w in other_report.weeks for s in w.intent.session_intents)
    assert {s.intent_id for w in report.weeks for s in w.intent.session_intents}.isdisjoint(
        s.intent_id for w in other_report.weeks for s in w.intent.session_intents)
    assert report.model_dump_json() == repeated_report.model_dump_json()


def test_workout_bytes_and_fingerprints_remain_identical(profile):
    ctx, original, plan, *_ = profile
    config = WorkoutBuilderConfig(version="shadow-equivalence", algorithm_version="shadow-equivalence")
    for before, after in zip(original.weeks, plan.weeks, strict=True):
        for a, b in zip(before.sessions, after.sessions, strict=True):
            assert build_structured_workout(ctx, a, config).model_dump_json() == build_structured_workout(ctx, b, config).model_dump_json()


def test_failed_generation_cannot_expose_previous_athlete_diagnostics(profile, monkeypatch):
    from app.application.planning_preview import PlanningPreviewApplication, PlanningContextAssembler
    ctx, _, _, report, *_ = profile
    app = PlanningPreviewApplication(None)
    app.shadow_report = report

    def unavailable(*args, **kwargs):
        raise ValueError("context unavailable")

    monkeypatch.setattr(PlanningContextAssembler, "assemble", unavailable)
    other_request = ctx.request.model_copy(update={"athlete_id": UUID("20000000-0000-0000-0000-000000000002")})
    with pytest.raises(ValueError, match="context unavailable"):
        app.generate(request=other_request, user_id=UUID(int=1))
    assert app.shadow_report is None


def test_intents_exist_before_placement_and_cannot_hide_dropped_needs(profile, monkeypatch):
    from app.domains.planning import session_planning as module
    ctx, _, _, _, season, budgets, config = profile
    original_place = module._place
    events = []

    def observed_place(*args):
        assert events[-1] == "intent"
        sessions, warnings = original_place(*args)
        events.append("place")
        return sessions[1:], warnings

    captured = []

    def observer(intent):
        events.append("intent")
        captured.append(intent)

    monkeypatch.setattr(module, "_place", observed_place)
    changed = build_session_plan(ctx, season, budgets, config, intent_observer=observer, structural_intent=False)
    assert len(captured[0].session_intents) == 6
    assert len(changed.weeks[0].sessions) == 5
    assert "MISSING_ROLE" in {d.code for d in compare_weekly_intent(captured[0], changed.weeks[0]).discrepancies}


def test_frequency_composition_survives_a_missing_generated_need(profile, monkeypatch):
    from app.domains.planning import session_planning as module
    ctx, _, _, _, season, budgets, config = profile
    original_sequence = module._type_sequence

    def missing_type(discipline, *args, **kwargs):
        values = original_sequence(discipline, *args, **kwargs)
        return values[:1] if discipline == "cycling" else values

    monkeypatch.setattr(module, "_type_sequence", missing_type)
    plan, report = build_session_plan_with_shadow(ctx, season, budgets, config, structural_intent=False)
    first = report.weeks[0]
    assert first.intent.resolved_sessions == 6
    assert next(c for c in first.intent.desired_composition if c.sport == "cycling").sessions == 2
    assert len(first.intent.session_intents) == len(plan.weeks[0].sessions) == 5
    assert {"SESSION_INTENT_COUNT_MISMATCH", "SPORT_COMPOSITION_MISMATCH", "RESOLVED_SESSION_COUNT_MISMATCH"} <= {
        d.code for d in first.comparison.discrepancies}
