from collections import Counter, defaultdict
from decimal import Decimal
from uuid import UUID

import pytest

from app.domains.planning.contracts import AvailabilitySlot, context_fingerprint
from app.domains.planning.intent_workouts import IntentWorkoutBuild
from app.domains.planning.preview import build_preview_artifact
from app.domains.planning.volume_intent import VolumeShadowBuild
from app.domains.planning.weekly_intent import build_session_plan_with_intent
from app.domains.planning.workout_builder import WorkoutBuilderConfig, workout_duration_seconds
from tests.test_structural_weekly_intent import inputs
from tests.test_weekly_intent_shadow import profile_context


def pipeline(ctx, active=True):
    season, budgets, config = inputs(ctx)
    content = IntentWorkoutBuild(ctx, WorkoutBuilderConfig(version="test", algorithm_version="test"))
    volume = VolumeShadowBuild(ctx, config)

    def prepare(intent, prescriptions):
        volume.prepare(intent, prescriptions)
        content.prepare(intent, prescriptions)

    plan, shadow, structure = build_session_plan_with_intent(ctx, season, budgets, config,
        workout_observer=prepare, coherent_volume=active)
    if structure is None:
        from app.domains.planning.workout_builder import build_structured_workout
        drafts = tuple(build_structured_workout(ctx, s, content.config) for w in plan.weeks for s in w.sessions)
    else:
        drafts = content.finish(plan, structure)
        structure = content.annotate(structure)
    roles = {g.goal_id: g.role for g in season.goals}
    artifact = build_preview_artifact(athlete_id=ctx.request.athlete_id, timezone_name=ctx.request.timezone_name,
        context_fingerprint_value=ctx.fingerprint, season=season, budgets=budgets, session_plan=plan,
        goals=tuple(g.model_copy(update={"role": roles[g.competition_goal_id]}) for g in ctx.goals),
        workout_drafts=drafts, algorithm_version="test", configuration_version="test", structural_planning=structure)
    report = volume.finish(plan, shadow, drafts, artifact.load_reconciliation) if structure else None
    return artifact, shadow, report


@pytest.fixture(scope="module")
def active():
    return pipeline(profile_context())


def test_null_bypasses_volume_authority_and_preserves_all_bytes(monkeypatch):
    ctx = profile_context()
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={"target_sessions_per_week": None})})
    before = pipeline(ctx, False)[0]
    monkeypatch.setattr("app.domains.planning.volume_intent.activate_endurance_volume",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("NULL entered volume authority")))
    after, _, report = pipeline(ctx, True)
    assert after.model_dump_json() == before.model_dump_json()
    assert report is None


def test_exact_six_and_explicit_duration_sources(active):
    artifact, shadow, report = active
    assert report.mode == "ENDURANCE_VOLUME_AUTHORITY_STRENGTH_LEGACY"
    for week in shadow.weeks:
        intent = week.intent
        assert intent.duration_authority == "endurance_volume_intent"
        if (intent.week_end - intent.week_start).days == 6:
            assert intent.resolved_sessions == 6
        assert intent.weekly_minutes_target == sum(s.target_duration_minutes for s in intent.session_intents)
        for s in intent.session_intents:
            assert s.duration_source == ("historical_legacy" if s.sport == "strength" else "coherent_volume_intent")
    for week in artifact.session_plan.weeks:
        if not any(s.discipline == "competition" for s in week.sessions):
            assert len(week.sessions) == 6


def test_applied_progression_and_caps_for_run_bike_and_swim(active):
    artifact, shadow, report = active
    for week, comparison in zip(shadow.weeks, report.weeks, strict=True):
        for s in week.intent.session_intents:
            if s.sport == "strength":
                assert s.target_duration_minutes == 24
                continue
            assert any(r.code == "ENDURANCE_VOLUME_DURATION_AUTHORITY" for r in s.progression.decisions)
            if s.progression.cap_minutes is not None:
                assert s.target_duration_minutes <= s.progression.cap_minutes
        assert comparison.minutes_variance == -comparison.constrained_minutes
        if not comparison.constrained_minutes:
            assert comparison.minutes_variance_percent == 0
        assert comparison.minutes_tolerance is None
    longs = [[next(s.target_duration_minutes for s in w.intent.session_intents if s.role == role) for w in shadow.weeks[:6]]
             for role in ("RUN_LONG", "BIKE_LONG")]
    assert longs[0][3:6] == [102, 112, 120]
    assert longs[1][:3] == [156, 171, 180]  # not +15 applied twice
    assert longs[1][3:6] == [153, 168, 180]
    swims = [next(s.target_duration_minutes for s in w.intent.session_intents if s.sport == "swimming") for w in shadow.weeks[:3]]
    assert swims == [34, 39, 44]


def test_run_reference_below_cap_is_not_forced_to_120():
    ctx = profile_context()
    windows = tuple(w.model_copy(update={"sports": tuple(s.model_copy(update={"longest_duration_seconds": 4200})
        if s.sport == "running" else s for s in w.sports)}) if w.days == 28 else w for w in ctx.training.windows)
    ctx = ctx.model_copy(update={"training": ctx.training.model_copy(update={"windows": windows})})
    _, shadow, _ = pipeline(ctx)
    longs = [next(s.target_duration_minutes for s in w.intent.session_intents if s.role == "RUN_LONG") for w in shadow.weeks[:3]]
    assert longs == [80, 90, 100]


def test_strength_content_and_all_workouts_unchanged_when_targets_match(active):
    before = pipeline(profile_context(), False)[0]
    after = active[0]
    assert after.session_plan.model_dump_json() == before.session_plan.model_dump_json()
    assert [s.model_dump_json() for s in after.sessions] == [s.model_dump_json() for s in before.sessions]
    assert after.fingerprint == before.fingerprint
    assert after.session_plan.fingerprint == before.session_plan.fingerprint


def alter_projection(original, role, delta):
    """Inject a consistent alternate volume policy to verify data flow, not physiology."""
    def project(ctx, intent, config, previous=None):
        value = original(ctx, intent, config, previous)
        if intent.duration_authority != "legacy":
            return value
        selected = next((r for s in value.sports for r in s.roles if r.role == role), None)
        if selected is None:
            return value
        sport = selected.sport
        sports = tuple(s.model_copy(update={"minutes_target": s.minutes_target + delta,
            "roles": tuple(r.model_copy(update={"target_duration_intent": r.target_duration_intent + delta,
                "final_value": r.final_value + delta}) if r.intent_id == selected.intent_id else r for r in s.roles)})
            if s.sport == sport else s for s in value.sports)
        total = value.weekly_minutes_target + delta
        copy = value.planning_intent.model_copy(update={"weekly_minutes_target": total,
            "desired_composition": tuple(c.model_copy(update={"volume_minutes_target": c.volume_minutes_target + delta})
                if c.sport == sport else c for c in value.planning_intent.desired_composition)})
        names = {"running": "run_minutes_target", "cycling": "bike_minutes_target", "swimming": "swim_minutes_target"}
        return value.model_copy(update={"planning_intent": copy, "sports": sports, "weekly_minutes_target": total,
            names[sport]: getattr(value, names[sport]) + delta})
    return project


def test_builder_consumes_volume_duration_and_changes_real_fingerprints(monkeypatch, active):
    from app.domains.planning import volume_intent
    monkeypatch.setattr(volume_intent, "project_volume_intent", alter_projection(volume_intent.project_volume_intent, "SWIM_TECHNIQUE", -5))
    changed, shadow, report = pipeline(profile_context())
    first = next(s for s in changed.sessions if s.prescription.discipline == "swimming")
    assert first.prescription.target_duration_minutes == 29
    assert workout_duration_seconds(first.workout.definition) == 29 * 60
    assert changed.fingerprint != active[0].fingerprint
    assert changed.session_plan.fingerprint != active[0].session_plan.fingerprint
    assert report.weeks[0].minutes_variance == 0
    assert all(s.prescription.target_load == b.prescription.target_load for s,b in zip(changed.sessions,active[0].sessions))


def test_projection_cannot_bypass_existing_caps(monkeypatch):
    from app.domains.planning import volume_intent
    monkeypatch.setattr(volume_intent, "project_volume_intent", alter_projection(volume_intent.project_volume_intent, "RUN_LONG", 1))
    with pytest.raises(ValueError, match="EXCEEDS_EXISTING_CAP"):
        pipeline(profile_context())


def test_doubles_revalidated_after_volume_changes(monkeypatch):
    from app.domains.planning import volume_intent
    ctx = profile_context()
    slots = tuple(AvailabilitySlot(weekday=i, available_minutes=60 if i == 2 else 300, max_sessions=2)
                  for i in range(7) if i != 3)
    ctx = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={"availability_slots": slots})})
    monkeypatch.setattr(volume_intent, "project_volume_intent", alter_projection(volume_intent.project_volume_intent, "SWIM_TECHNIQUE", 10))
    artifact, _, report = pipeline(ctx)
    for week in artifact.session_plan.weeks:
        days = defaultdict(list)
        for session in week.sessions:
            if session.discipline != "competition":
                days[session.date].append(session)
        for day, sessions in days.items():
            assert len(sessions) <= 2
            assert sum(s.target_duration_minutes for s in sessions) <= next(s.available_minutes for s in slots if s.weekday == day.weekday())
            if day.weekday() == 2:
                assert not ({s.discipline for s in sessions} == {"strength", "swimming"})  # 44+24 > 60
    assert not any(w.daily_violations for w in report.weeks)


def test_volume_variance_and_percent_when_unplaced():
    ctx = profile_context()
    prefs = ctx.preferences.model_copy(update={"availability_slots": tuple(s.model_copy(update={"available_minutes": 25, "max_sessions": 1})
        for s in ctx.preferences.availability_slots), "max_sessions_per_day": 1})
    _, _, report = pipeline(ctx.model_copy(update={"preferences": prefs}))
    constrained = [w for w in report.weeks if w.constrained_minutes]
    assert constrained
    for w in constrained:
        assert w.minutes_variance == w.actual_minutes - w.intent.weekly_minutes_target
        assert w.minutes_variance_percent == w.minutes_variance / w.intent.weekly_minutes_target * 100
        assert "MINUTES_UNDER_TARGET" in w.diagnostics
        assert not w.daily_violations


def test_determinism_and_multiathlete(active):
    ctx = profile_context()
    assert pipeline(ctx)[0].model_dump_json() == active[0].model_dump_json()
    other = UUID("20000000-0000-0000-0000-000000000002")
    ctx = ctx.model_copy(update={"request": ctx.request.model_copy(update={"athlete_id": other})})
    ctx = ctx.model_copy(update={"fingerprint": context_fingerprint(ctx.model_dump(exclude={"fingerprint"}))})
    artifact, shadow, report = pipeline(ctx)
    assert artifact.athlete_id == other
    assert report.context_fingerprint == ctx.fingerprint
    assert all(str(other) in s.intent_id for w in shadow.weeks for s in w.intent.session_intents)
    assert artifact.fingerprint != active[0].fingerprint


@pytest.mark.parametrize("phase", ["RECOVERY", "BUILD", "TAPER", "COMPETITION"])
def test_phase_policies_are_preserved_before_duration_authority(phase):
    from app.domains.planning.season_structure import SeasonPhase
    from app.domains.planning.weekly_intent import create_weekly_planning_intent
    ctx = profile_context()
    _, budgets, config = inputs(ctx)
    budget = budgets.budgets[0].model_copy(update={"dominant_phase": SeasonPhase(phase)})
    def make(active):
        return create_weekly_planning_intent(ctx, budget, budgets.baseline, config,
            {"running": 100, "cycling": 150, "swimming": 40}, {}, {}, {}, [], {}, coherent_volume=active)
    legacy, active = make(False), make(True)
    assert [(s.role, s.target_duration_minutes) for s in active.session_intents] == [(s.role, s.target_duration_minutes) for s in legacy.session_intents]
    assert active.weekly_minutes_target == sum(s.target_duration_minutes for s in legacy.session_intents)
    if phase in {"RECOVERY", "TAPER"}:
        assert not any(s.role.endswith("LONG") for s in active.session_intents)
