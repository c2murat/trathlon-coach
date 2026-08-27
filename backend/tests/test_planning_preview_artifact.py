from app.domains.planning.preview import build_preview_artifact, preview_artifact_payload
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_session_planning import build, with_running_frequency
from tests.test_weekly_budget import context


def artifact(ctx=None):
    ctx = ctx or context(windows=with_running_frequency())
    plan, season, budgets, _ = build(ctx)
    config = WorkoutBuilderConfig(version="workout-1", algorithm_version="workout-algorithm-1")
    prescriptions = tuple(item for week in plan.weeks for item in week.sessions)
    drafts = tuple(build_structured_workout(ctx, item, config) for item in prescriptions)
    return build_preview_artifact(
        athlete_id=ctx.request.athlete_id, timezone_name=ctx.request.timezone_name,
        context_fingerprint_value=ctx.fingerprint, season=season, budgets=budgets,
        session_plan=plan, goals=ctx.goals, workout_drafts=drafts,
        algorithm_version="0.8F.6", configuration_version="0.8F.6",
    )


def test_preview_is_complete_and_fingerprint_excludes_itself():
    result = artifact()
    payload = preview_artifact_payload(result)
    assert "fingerprint" not in payload
    assert len(result.sessions) == sum(len(week.sessions) for week in result.session_plan.weeks)


def test_preview_round_trip_and_fingerprint_are_deterministic():
    first = artifact()
    second = artifact()
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.fingerprint == second.fingerprint


def test_preview_fingerprint_detects_a_changed_prescription():
    first = artifact()
    changed_plan = first.session_plan.model_copy(update={
        "weeks": (
            first.session_plan.weeks[0].model_copy(update={
                "sessions": (
                    first.session_plan.weeks[0].sessions[0].model_copy(update={"target_duration_minutes": 1}),
                    *first.session_plan.weeks[0].sessions[1:],
                )
            }),
            *first.session_plan.weeks[1:],
        )
    })
    drafts = tuple(item.workout for item in first.sessions)
    try:
        changed = build_preview_artifact(
            athlete_id=first.athlete_id, timezone_name=first.timezone_name,
            context_fingerprint_value=first.context_fingerprint,
            season=first.season_structure, budgets=first.weekly_budget_plan,
            session_plan=changed_plan, goals=first.goals, workout_drafts=drafts,
            algorithm_version=first.algorithm_version,
            configuration_version=first.configuration_version,
        )
    except ValueError:
        return
    assert changed.fingerprint != first.fingerprint
