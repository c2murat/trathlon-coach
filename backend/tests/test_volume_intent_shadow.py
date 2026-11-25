from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domains.planning.volume_intent import VolumeShadowBuild, WeeklyVolumeIntent, project_volume_intent
from app.domains.planning.weekly_intent import build_session_plan_with_intent
from app.domains.planning.intent_workouts import IntentWorkoutBuild
from app.domains.planning.workout_builder import WorkoutBuilderConfig
from tests.test_structural_weekly_intent import inputs, run
from tests.test_weekly_intent_shadow import profile_context


def shadow_run(ctx):
    season, budgets, config = inputs(ctx)
    volume = VolumeShadowBuild(ctx, config)
    content = IntentWorkoutBuild(ctx, WorkoutBuilderConfig(version="test", algorithm_version="test"))
    prepared = []

    def prepare(intent, prescriptions):
        volume.prepare(intent, prescriptions)
        assert intent.week_start in volume.intents  # available BEFORE builder
        prepared.append(intent.week_start)
        content.prepare(intent, prescriptions)

    plan, shadow, structure = build_session_plan_with_intent(ctx, season, budgets, config, workout_observer=prepare)
    drafts = content.finish(plan, structure)
    return plan, shadow, structure, volume, drafts


@pytest.fixture(scope="module")
def captured():
    ctx = profile_context()
    plan, shadow, structure, volume, drafts = shadow_run(ctx)
    return ctx, plan, shadow, structure, volume, drafts, volume.finish(plan, shadow, drafts)


def test_shadow_preserves_complete_artifact_and_fingerprint(captured):
    ctx, plan, shadow, structure, volume, drafts, report = captured
    old_plan, _, old_structure, _, old_artifact = run(ctx)
    assert old_plan.model_dump_json() == plan.model_dump_json()
    assert old_structure.model_dump_json() == content_annotated(structure)
    assert [s.workout.model_dump_json() for s in old_artifact.sessions] == [d.model_dump_json() for d in drafts]
    before = old_artifact.model_dump_json()
    volume.finish(plan, shadow, drafts, old_artifact.load_reconciliation)
    assert old_artifact.model_dump_json() == before
    assert report.mode == "SHADOW_NO_WORKOUT_OR_ARTIFACT_EFFECT"


def content_annotated(structure):
    return structure.model_copy(update={"weeks": tuple(w.model_copy(update={"generated_workout_count": w.generated}) for w in structure.weeks)}).model_dump_json()


def test_exact_bottom_up_sport_and_role_reconciliation(captured):
    _, _, shadow, _, _, _, report = captured
    for original, week in zip(shadow.weeks, report.weeks, strict=True):
        v = week.intent
        assert sum(s.minutes_target for s in v.sports) == v.weekly_minutes_target
        assert v.run_minutes_target + v.bike_minutes_target + v.swim_minutes_target + v.strength_minutes_target == v.weekly_minutes_target
        assert all(sum(r.target_duration_intent for r in s.roles) == s.minutes_target for s in v.sports)
        assert v.planning_intent.weekly_minutes_target == v.weekly_minutes_target
        assert original.intent.weekly_minutes_target is None  # immutable artifact snapshot
        assert v.planning_intent.resolved_sessions == original.intent.resolved_sessions
        assert tuple(s.role for s in v.planning_intent.session_intents) == tuple(s.role for s in original.intent.session_intents)
        assert all(s.minutes_variance == 0 for s in week.sessions if s.placed)
        assert week.minutes_variance == -week.constrained_minutes
        assert not week.daily_violations


def test_load_shares_are_not_minutes_weights(captured):
    ctx, _, shadow, _, _, _, report = captured
    config = inputs(ctx)[2]
    original = shadow.weeks[0].intent
    changed = original.model_copy(update={"weekly_load_budget": Decimal("999999"), "desired_composition": tuple(
        s.model_copy(update={"target_share": Decimal("0.25")}) for s in original.desired_composition)})
    projection = project_volume_intent(ctx, changed, config)
    assert projection.weekly_minutes_target == report.weeks[0].intent.weekly_minutes_target
    assert [s.minutes_target for s in projection.sports] == [s.minutes_target for s in report.weeks[0].intent.sports]
    assert projection.weekly_load_budget == Decimal("999999")


def test_run_cap_and_strength_root_causes(captured):
    first = captured[-1].weeks[0]
    run_role = next(r for s in first.intent.sports for r in s.roles if r.role == "RUN_LONG")
    assert run_role.rolling_reference == Decimal("110.6")
    assert run_role.trace.pre_progression_minutes == 110
    assert run_role.progression_increment_minutes == 10
    assert run_role.proposed_value == run_role.final_value == run_role.cap == 120
    assert "CAP_REACHED" in {r.code for r in run_role.reasons}
    for s in first.strength_volume_intent:
        assert not s.independently_derivable
        assert s.duration_seconds == 24 * 60
        assert s.exercises and s.sets and s.reps and s.rest_seconds and s.rpe_bounds


def test_previous_role_value_and_deterministic_progression(captured):
    ctx, plan, shadow, structure, volume, drafts, report = captured
    rebuilt = VolumeShadowBuild(ctx, inputs(ctx)[2])
    for w in shadow.weeks:
        rebuilt.prepare(w.intent)
    assert rebuilt.finish(plan, shadow, drafts).model_dump_json() == report.model_dump_json()
    roles = [r for s in report.weeks[1].intent.sports for r in s.roles]
    assert next(r for r in roles if r.role == "RUN_LONG").previous_week_value == 120
    assert all(r.reasons for r in roles)
    with pytest.raises(ValueError, match="PREPARED_TWICE"):
        rebuilt.prepare(shadow.weeks[0].intent)


def test_invalid_volume_invariants(captured):
    v = captured[-1].weeks[0].intent.model_dump()
    v["weekly_minutes_target"] += 1
    with pytest.raises(ValidationError):
        WeeklyVolumeIntent.model_validate(v)
    v = captured[-1].weeks[0].intent.model_dump()
    v["sports"][0]["minutes_target"] += 1
    with pytest.raises(ValidationError):
        WeeklyVolumeIntent.model_validate(v)


def test_capacity_diagnostic_and_unplaced_intent(captured):
    ctx = captured[0]
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={
        "availability_slots": tuple(s.model_copy(update={"available_minutes": 25, "max_sessions": 1}) for s in ctx.preferences.availability_slots),
        "max_sessions_per_day": 1})})
    plan, shadow, structure, volume, drafts = shadow_run(ctx)
    report = volume.finish(plan, shadow, drafts)
    assert any(w.constrained_minutes for w in report.weeks)
    assert all(not w.daily_violations for w in report.weeks)
    assert all(sum(s.placed for s in w.sessions) <= 7 for w in report.weeks)
    assert any("MINUTES_UNDER_TARGET" in w.diagnostics for w in report.weeks)
    original = captured[2].weeks[0].intent
    projected = project_volume_intent(ctx, original.model_copy(update={"daily_availability": ctx.preferences.availability_slots,
        "max_daily_sessions": 1}), inputs(ctx)[2])
    assert projected.aggregate_excess_minutes > 0


def test_explicit_workout_divergence_is_reported(captured):
    _, plan, shadow, _, volume, drafts, _ = captured
    d = drafts[0]
    node = d.definition.steps[0]
    longer = node.model_copy(update={"duration": node.duration.model_copy(update={"seconds": node.duration.seconds + 60})})
    changed = d.model_copy(update={"definition": d.definition.model_copy(update={"steps": (longer,) + tuple(d.definition.steps[1:])})})
    report = volume.finish(plan, shadow, (changed,) + drafts[1:])
    assert report.weeks[0].minutes_variance == 1
    assert "MINUTES_OVER_TARGET" in report.weeks[0].diagnostics
    assert any(s.reason == "EXPLICIT_WORKOUT_DURATION_DIVERGENCE" for s in report.weeks[0].sessions)


def test_null_default_bypasses_prebuild_shadow():
    ctx = profile_context()
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={"target_sessions_per_week": None})})
    season, budgets, config = inputs(ctx)
    volume = VolumeShadowBuild(ctx, config)
    _, _, structure = build_session_plan_with_intent(ctx, season, budgets, config, workout_observer=volume.prepare)
    assert structure is None
    assert not volume.intents


def test_existing_long_policy_grows_to_cap_and_applies_deload_and_taper(captured):
    from app.domains.planning.session_planning import _duration, SessionType
    from app.domains.planning.season_structure import SeasonPhase
    from app.domains.planning.weekly_budget import BudgetAdjustment
    ctx = captured[0]
    _, budgets, config = inputs(ctx)
    budget = budgets.budgets[0]
    for previous, expected in ((70, 80), (115, 120)):
        trace = []
        assert _duration(ctx, budget, "running", SessionType.RUN_LONG, config, {"running": previous}, trace) == expected
        assert trace[0]["proposed_minutes"] == previous + config.long_run_progression_minutes
    deload = budget.model_copy(update={"adjustments": (BudgetAdjustment(code="DELOAD", factor=Decimal("0.80")),)})
    assert _duration(ctx, deload, "running", SessionType.RUN_LONG, config, {"running": 100}) == 85
    taper = budget.model_copy(update={"dominant_phase": SeasonPhase.TAPER, "adjustments": ()})
    assert _duration(ctx, taper, "running", SessionType.RUN_LONG, config, {"running": 100}) == 65


def test_available_capacity_reserves_competition_and_max_weekly(captured):
    ctx, _, shadow, _, _, _, _ = captured
    _, _, config = inputs(ctx)
    original = shadow.weeks[0].intent
    goal = original.competition_context[0].model_copy(update={"event_date": original.week_start, "occurs_this_week": True})
    race = original.model_copy(update={"competition_context": (goal,), "competition_sessions": 1, "max_weekly_sessions": 6})
    before = project_volume_intent(ctx, original, config)
    after = project_volume_intent(ctx, race, config)
    assert after.weekly_minutes_target == before.weekly_minutes_target
    slot = next(s for s in original.daily_availability if s.weekday == original.week_start.weekday())
    assert after.weekly_capacity_minutes == before.weekly_capacity_minutes - slot.available_minutes
    assert after.session_capacity <= 5


def test_doubles_change_capacity_without_changing_volume(captured):
    ctx, _, shadow, _, _, _, _ = captured
    original = shadow.weeks[0].intent
    config = inputs(ctx)[2]
    single = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={"max_sessions_per_day": 1})})
    a = project_volume_intent(ctx, original, config)
    b = project_volume_intent(single, original.model_copy(update={"max_daily_sessions": 1}), config)
    assert a.weekly_minutes_target == b.weekly_minutes_target
    assert a.weekly_capacity_minutes == b.weekly_capacity_minutes
    assert a.session_capacity >= b.session_capacity


@pytest.mark.parametrize("target", [None, 6])
def test_application_report_is_ephemeral_and_resets_after_failure(monkeypatch, target):
    from sqlalchemy.orm import Session
    from app.application.planning_preview import PlanningPreviewApplication, PlanningContextAssembler, ExecutionAdaptationProposalAssembler
    from app.domains.planning.execution_adaptation import build_execution_adaptation_context
    from app.domains.planning.execution_proposals import build_execution_adaptation_proposal_context
    from tests.test_execution_adaptation import context as evidence_context
    from tests.test_planning_preview_application import seeded
    ctx = profile_context()
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={"target_sessions_per_week": target})})
    evidence = evidence_context().model_copy(update={"athlete_profile_id": ctx.request.athlete_id, "as_of_date": ctx.request.planning_date})
    proposals = build_execution_adaptation_proposal_context(build_execution_adaptation_context(evidence))
    monkeypatch.setattr(PlanningContextAssembler, "assemble", lambda *a, **k: ctx)
    monkeypatch.setattr(ExecutionAdaptationProposalAssembler, "assemble", lambda *a, **k: proposals)
    engine, _, _, user, _ = seeded()
    with Session(engine) as session:
        app = PlanningPreviewApplication(session)
        row = app.generate(request=ctx.request, user_id=user)
        assert (app.volume_shadow_report is not None) == (target is not None)
        assert "volume_shadow_report" not in row.artifact
        assert "volume_intent" not in row.artifact
        assert row.artifact["fingerprint"] == row.artifact_fingerprint
        if target is not None:
            assert app.artifact(row).fingerprint == row.artifact_fingerprint
        if target is not None:
            assert app.volume_shadow_report.context_fingerprint == app.shadow_report.context_fingerprint
            assert app.volume_shadow_report.weeks[0].estimated_load is not None
        monkeypatch.setattr(PlanningContextAssembler, "assemble", lambda *a, **k: (_ for _ in ()).throw(ValueError("context unavailable")))
        with pytest.raises(ValueError, match="context unavailable"):
            app.generate(request=ctx.request, user_id=user)
        assert app.volume_shadow_report is None
