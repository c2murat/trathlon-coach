from collections import Counter
from datetime import timedelta
from uuid import UUID

import pytest

from app.domains.planning.contracts import AvailabilitySlot, PlanningWarning
from app.domains.planning.intent_workouts import IntentWorkoutBuild
from app.domains.planning.preview import TrainingPlanPreviewArtifact, build_preview_artifact, preview_artifact_payload
from app.domains.planning.season_structure import SeasonStructureBuilder, SeasonStructureConfig
from app.domains.planning.session_planning import SessionPlanningConfig, SessionType, build_session_plan
from app.domains.planning.weekly_budget import WeeklyBudgetConfig, build_weekly_budget_plan
from app.domains.planning.weekly_distribution import distribute_week, refresh_explicit_date_warnings
from app.domains.planning.weekly_intent import build_session_plan_with_intent
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_frequency_intent import tri
from tests.test_weekly_intent_shadow import profile_context


def inputs(ctx):
    season = SeasonStructureBuilder(SeasonStructureConfig(version="test", algorithm_version="test")).build(ctx)
    budgets = build_weekly_budget_plan(ctx, season, WeeklyBudgetConfig(version="test", algorithm_version="test"))
    config = SessionPlanningConfig(version="test", algorithm_version="test")
    return season, budgets, config


def run(ctx):
    season, budgets, config = inputs(ctx)
    wc = WorkoutBuilderConfig(version="test", algorithm_version="test")
    content = IntentWorkoutBuild(ctx, wc)
    plan, diagnostic, structure = build_session_plan_with_intent(ctx, season, budgets, config, workout_observer=content.prepare)
    drafts = content.finish(plan, structure) if structure else tuple(
        build_structured_workout(ctx, s, wc) for w in plan.weeks for s in w.sessions)
    structure = content.annotate(structure) if structure else None
    roles = {g.goal_id: g.role for g in season.goals}
    artifact = build_preview_artifact(
        athlete_id=ctx.request.athlete_id, timezone_name=ctx.request.timezone_name, context_fingerprint_value=ctx.fingerprint,
        season=season, budgets=budgets, session_plan=plan, goals=tuple(g.model_copy(update={"role": roles[g.competition_goal_id]}) for g in ctx.goals),
        workout_drafts=drafts, algorithm_version="test", configuration_version="test", structural_planning=structure,
    )
    return plan, diagnostic, structure, content, artifact


@pytest.fixture(scope="module", params=[5, 6, 7])
def explicit(request):
    ctx = profile_context()
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={"target_sessions_per_week": request.param})})
    return ctx, run(ctx)


def test_exact_total_and_single_composition_authority(explicit):
    ctx, (plan, diagnostic, report, _, _) = explicit
    assert diagnostic.mode == "STRUCTURAL_INTENT"
    for result, week in zip(report.weeks, plan.weeks, strict=True):
        intent = result.intent
        assert intent.authority == "frequency_composition"
        assert sum(c.sessions for c in intent.desired_composition) == len(intent.session_intents) == intent.resolved_sessions
        assert intent.strength_sessions <= intent.resolved_sessions
        assert result.placed + len(result.unplaced) == result.generated == intent.resolved_sessions
        assert result.generated_workout_count == result.generated
        assert len(set(result.placed_intent_ids)) == result.placed
        if intent.phase == "BASE" and (intent.week_end - intent.week_start).days == 6:
            assert result.placed == ctx.preferences.target_sessions_per_week
            assert not result.unplaced
            assert intent.strength_sessions == 2
            assert intent.endurance_sessions == ctx.preferences.target_sessions_per_week - 2
            assert result.classification == "exact_frequency"
    if ctx.preferences.target_sessions_per_week == 6:
        assert {c.sport: c.sessions for c in report.weeks[0].intent.desired_composition} == {
            "running": 1, "cycling": 2, "swimming": 1, "strength": 2}


def test_content_and_legacy_draft_identity_unchanged_for_each_intent(explicit):
    ctx, (plan, _, report, content, artifact) = explicit
    wc = content.config
    for session in artifact.sessions:
        expected = build_structured_workout(ctx, session.prescription, wc)
        assert session.workout.model_dump_json() == expected.model_dump_json()
    first = report.weeks[0].intent
    assert next(s for s in first.session_intents if s.role == "RUN_LONG").target_duration_minutes == 120
    assert all(s.target_duration_minutes == 24 for s in first.session_intents if s.sport == "strength")
    assert first.weekly_minutes_target is None


def test_null_does_not_invoke_authority_and_preserves_bytes(monkeypatch):
    ctx = tri()
    season, budgets, config = inputs(ctx)
    before = build_session_plan(ctx, season, budgets, config, structural_intent=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("NULL must not enter structural authority")

    monkeypatch.setattr("app.domains.planning.weekly_intent.create_weekly_planning_intent", forbidden)
    after, report, structure = build_session_plan_with_intent(ctx, season, budgets, config)
    assert before.model_dump_json() == after.model_dump_json()
    assert before.fingerprint == after.fingerprint
    assert structure is None and report.mode == "SHADOW_NO_GENERATION_EFFECT"
    assert all(w.intent.frequency_source == "legacy" for w in report.weeks)


def test_frequency_rule_runs_once_per_week(monkeypatch):
    from app.domains.planning import session_planning as sp
    ctx = profile_context(); season, budgets, config = inputs(ctx)
    calls = []
    original = sp._frequency

    def count(*args, **kwargs):
        calls.append(args[1].week_start)
        return original(*args, **kwargs)

    monkeypatch.setattr(sp, "_frequency", count)
    build_session_plan_with_intent(ctx, season, budgets, config)
    assert calls == [b.week_start for b in budgets.budgets]


def test_race_capacity_is_unplaced_not_a_fake_phase_reduction():
    ctx = profile_context()
    ctx = ctx.model_copy(update={
        "goals": (ctx.goals[0].model_copy(update={"event_date": ctx.goals[0].event_date - timedelta(days=1)}),),
        "preferences": ctx.preferences.model_copy(update={"max_sessions_per_week": 6}),
    })
    plan, _, report, _, artifact = run(ctx)
    race = report.weeks[-1]
    assert race.requested_training_sessions == race.phase_adjusted_sessions == race.intended_sessions == 6
    assert race.generated_workout_count == 6
    assert race.competition_sessions == 1
    assert race.placed == 5 and race.total_calendar_sessions == 6
    assert len(race.unplaced) == 1
    assert race.unplaced[0].reason == "WEEKLY_LIMIT_INCLUDING_COMPETITION"
    assert race.classification == "constrained_unplaced"
    assert race.intent.strength_sessions == 1  # Existing taper rule, total stays6.
    assert any(w.code == "FREQUENCY_TARGET_CONSTRAINED" for w in plan.weeks[-1].warnings)
    assert artifact.structural_planning.weeks[-1].unplaced[0].session.role


def test_daily_one_and_unavailable_day_keep_unplaced_identity():
    ctx = profile_context()
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={
        "target_sessions_per_week": 7, "max_sessions_per_day": 1,
        "availability_slots": tuple(s for s in ctx.preferences.availability_slots if s.weekday != 3),
    })})
    plan, _, report, _, _ = run(ctx)
    first = report.weeks[0]
    assert first.intended_sessions == first.generated == first.generated_workout_count == 7
    assert first.placed == 6 and len(first.unplaced) == 1
    assert first.unplaced[0].reason
    for week in plan.weeks:
        assert max(Counter(s.date for s in week.sessions).values(), default=0) <= 1
        assert all(s.date.weekday() != 3 for s in week.sessions if s.discipline != "competition")


def test_double_preserves_six_total_and_final_preferences():
    ctx = profile_context()
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={
        "availability_slots": tuple(s for s in ctx.preferences.availability_slots if s.weekday != 3),
    })})
    plan, _, report, _, _ = run(ctx)
    first = report.weeks[0]
    assert first.generated == first.placed == 6 and not first.unplaced
    assert first.occupied_days == 5 and first.double_days == 1
    assert all(s.date.weekday() != 0 for s in plan.weeks[0].sessions)
    assert not any(w.code == "PREFERRED_REST_DAY_UNAVAILABLE" for w in plan.weeks[0].warnings)


def test_explicit_free_day_beats_strength_separation(explicit):
    ctx, (plan, _, _, _, _) = explicit
    week = plan.weeks[0]
    strengths = [s for s in week.sessions if s.discipline == "strength"]
    swim = next(s for s in week.sessions if s.discipline == "swimming")
    sessions = tuple(s.model_copy(update={"date": week.week_start + timedelta(days=d), "target_duration_minutes": 30})
                     for s, d in zip((*strengths, swim), (0, 2, 1), strict=True))
    prefs = ctx.preferences.model_copy(update={"availability_slots": tuple(
        AvailabilitySlot(weekday=d, available_minutes=120, max_sessions=2) for d in (0, 1, 2))})
    ctx = ctx.model_copy(update={"preferences": prefs})
    result = distribute_week(week.model_copy(update={"sessions": sessions}), ctx, SessionPlanningConfig(version="test", algorithm_version="test"))
    assert all(s.date.weekday() != 0 for s in result.sessions)
    assert len(result.sessions) == 3


def test_warnings_come_from_final_dates(explicit):
    ctx, (plan, _, _, _, _) = explicit
    week = plan.weeks[0].model_copy(update={"warnings": (PlanningWarning(code="PREFERRED_REST_DAY_UNAVAILABLE"),)})
    result = refresh_explicit_date_warnings(week, ctx, SessionPlanningConfig(version="test", algorithm_version="test"))
    assert all(s.date.weekday() != 0 for s in result.sessions)
    assert not any(w.code == "PREFERRED_REST_DAY_UNAVAILABLE" for w in result.warnings)


def test_prebuilt_content_precedes_final_distribution_and_greedy_loss_is_recovered(monkeypatch):
    from app.domains.planning import session_planning as sp, weekly_distribution as wd
    ctx = profile_context()
    place = sp._place; distribute = wd.distribute_week
    prepared = set()
    wc = WorkoutBuilderConfig(version="test", algorithm_version="test")
    content = IntentWorkoutBuild(ctx, wc)

    def greedy(*args, **kwargs):
        sessions, warnings = place(*args, **kwargs)
        outcome = kwargs.get("outcome")
        if outcome is not None:
            for i, need in enumerate(args[2]):
                if need.discipline == "swimming":
                    outcome[i] = "TEST_GREEDY_OMISSION"
                    sessions = [s for s in sessions if s.discipline != "swimming"]
        return sessions, warnings

    def prepare(intent, seeds):
        content.prepare(intent, seeds)
        prepared.add(intent.week_start)

    def calendar(week, *args, **kwargs):
        assert week.week_start in prepared
        return distribute(week, *args, **kwargs)

    monkeypatch.setattr(sp, "_place", greedy)
    monkeypatch.setattr(wd, "distribute_week", calendar)
    season, budgets, config = inputs(ctx)
    plan, _, report = build_session_plan_with_intent(ctx, season, budgets, config, workout_observer=prepare)
    assert len(plan.weeks[0].sessions) == 6
    assert not report.weeks[0].unplaced
    assert not any(w.code == "FREQUENCY_TARGET_CONSTRAINED" for w in plan.weeks[0].warnings)


def test_corrupt_role_composition_is_a_central_invariant(monkeypatch):
    from app.domains.planning import session_planning as sp
    original = sp._type_sequence

    def missing(discipline, *args, **kwargs):
        values = original(discipline, *args, **kwargs)
        return values[:1] if discipline == "cycling" else values

    monkeypatch.setattr(sp, "_type_sequence", missing)
    ctx = profile_context(); season, budgets, config = inputs(ctx)
    with pytest.raises(ValueError, match="SESSION_INTENT_COMPOSITION_INVARIANT"):
        build_session_plan_with_intent(ctx, season, budgets, config)


def test_diagnostic_metadata_never_enters_fingerprint(explicit):
    _, (_, _, report, _, artifact) = explicit
    modified = artifact.model_copy(update={"structural_planning": report.model_copy(update={"algorithm_version": "diagnostic-only"})})
    assert preview_artifact_payload(artifact) == preview_artifact_payload(modified)
    assert artifact.fingerprint == modified.fingerprint
    assert "structural_planning" not in preview_artifact_payload(artifact)
    assert artifact.structural_planning is not None
    assert TrainingPlanPreviewArtifact.model_validate_json(artifact.model_dump_json(exclude_none=True)).structural_planning == report


def test_determinism_and_multiathlete_isolation():
    first = profile_context()
    result = run(first)
    repeated = run(first)
    assert result[-1].model_dump_json() == repeated[-1].model_dump_json()
    other_id = UUID("30000000-0000-0000-0000-000000000003")
    other = first.model_copy(update={"request": first.request.model_copy(update={"athlete_id": other_id}), "fingerprint": "c" * 64})
    other_report = run(other)[2]
    assert other_report.athlete_id == other_id
    assert {s.intent_id for w in result[2].weeks for s in w.intent.session_intents}.isdisjoint(
        s.intent_id for w in other_report.weeks for s in w.intent.session_intents)
