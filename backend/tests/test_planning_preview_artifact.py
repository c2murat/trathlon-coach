import pytest

from app.application.planning_preview import PREVIEW_ARTIFACT_VERSION, SESSION_PLANNING_VERSION, WORKOUT_BUILDER_VERSION
from app.domains.planning.preview import TrainingPlanPreviewArtifact, build_preview_artifact, preview_artifact_payload
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


def test_new_session_workout_and_preview_generation_versions_are_coherent():
    assert SESSION_PLANNING_VERSION == WORKOUT_BUILDER_VERSION == PREVIEW_ARTIFACT_VERSION == "0.8F.9"


def test_preview_round_trip_and_fingerprint_are_deterministic():
    first = artifact()
    second = artifact()
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.fingerprint == second.fingerprint


def test_legacy_0_8f_8_session_metadata_remains_readable():
    source = artifact()
    legacy = source.model_dump(mode="json")
    legacy["session_plan"]["configuration_version"] = "0.8F.8"
    legacy["session_plan"]["algorithm_version"] = "0.8F.8"
    for week in legacy["session_plan"]["weeks"]:
        for session in week["sessions"]:
            session["rule_version"] = "0.8F.8"
    for session in legacy["sessions"]:
        session["prescription"]["rule_version"] = "0.8F.8"

    parsed = TrainingPlanPreviewArtifact.model_validate(legacy)

    assert parsed.session_plan.configuration_version == "0.8F.8"
    assert parsed.session_plan.algorithm_version == "0.8F.8"
    assert {session.rule_version for week in parsed.session_plan.weeks for session in week.sessions} == {"0.8F.8"}


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


def test_new_preview_rejects_a_missing_nested_leaf_title_but_old_v1_remains_readable():
    source = artifact()
    drafts = list(item.workout for item in source.sessions)
    index = next(
        index for index, draft in enumerate(drafts)
        if draft.definition is not None
        and any(node.kind == "repeat" for node in draft.definition.steps)
    )
    draft = drafts[index]
    definition = draft.definition
    repeat_index = next(index for index, node in enumerate(definition.steps) if node.kind == "repeat")
    repeat = definition.steps[repeat_index]
    missing = repeat.steps[0].model_copy(update={"title": None})
    repeat = repeat.model_copy(update={"steps": [missing, *repeat.steps[1:]]})
    steps = list(definition.steps); steps[repeat_index] = repeat
    definition = definition.model_copy(update={"steps": steps})
    drafts[index] = draft.model_copy(update={"definition": definition})
    with pytest.raises(ValueError, match="new preview workout leaf requires title"):
        build_preview_artifact(
            athlete_id=source.athlete_id, timezone_name=source.timezone_name,
            context_fingerprint_value=source.context_fingerprint,
            season=source.season_structure, budgets=source.weekly_budget_plan,
            session_plan=source.session_plan, goals=source.goals,
            workout_drafts=tuple(drafts), algorithm_version=source.algorithm_version,
            configuration_version=source.configuration_version,
        )

    legacy = source.model_dump(mode="json")
    for session in legacy["sessions"]:
        definition = session["workout"].get("definition")
        if not definition:
            continue
        pending = list(definition["steps"])
        while pending:
            node = pending.pop()
            if node["kind"] == "repeat":
                pending.extend(node.get("steps", []))
            else:
                node.pop("title", None)
    parsed = TrainingPlanPreviewArtifact.model_validate(legacy)
    assert parsed.schema_version == 1
