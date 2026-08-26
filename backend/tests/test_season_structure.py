from datetime import date, timedelta
from uuid import UUID

import pytest

from app.domains.planning.contracts import (
    AthleteTrainingSnapshot, AvailabilitySlot, ContextVersions, PerformanceSnapshot,
    PlanningContext, PlanningGoal, PlanningGoalSegment, PlanningPreferences,
    PlanningRequest,
)
from app.domains.planning.season_structure import (
    SeasonPhase, SeasonStructureBuilder, SeasonStructureConfig, SeasonStructureError,
)


START = date(2026, 1, 1)


def preferences(days=7, minutes=60):
    return PlanningPreferences(
        availability_slots=tuple(AvailabilitySlot(weekday=day, available_minutes=minutes, max_sessions=1) for day in range(days)),
        max_sessions_per_day=1, max_sessions_per_week=days,
        preferred_rest_days=(), strength_sessions_per_week=1,
    )


def goal(number, days, priority="A", category="running", sports=("run",)):
    return PlanningGoal(
        competition_goal_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        event_date=START + timedelta(days=days), timezone_name="UTC",
        category=category, event_format="custom", priority=priority,
        segments=tuple(PlanningGoalSegment(position=index, sport=sport, distance_m=1000 * index) for index, sport in enumerate(sports, 1)),
        status="active",
    )


def context(goals, prefs=None, horizon=None, start=START):
    prefs = prefs or preferences()
    request = PlanningRequest(
        athlete_id=UUID("10000000-0000-0000-0000-000000000001"),
        planning_date=start, timezone_name="UTC",
        goal_ids=tuple(item.competition_goal_id for item in goals), start_date=start,
        horizon_end_date=horizon, preferences=prefs,
        algorithm_version="planning-structure-test", configuration_version="context-test",
    )
    training = AthleteTrainingSnapshot(
        planning_date=start, timezone_name="UTC",
        observation_start=start - timedelta(days=90), observation_end=start - timedelta(days=1),
        observed_days=90, activities_available=False, status_available=False, windows=(),
    )
    versions = ContextVersions(
        planning_algorithm_version="planning-structure-test", configuration_version="context-test",
        training_load_algorithm_version="load", load_aggregation_algorithm_version="aggregate",
        manual_strength_algorithm_version="strength", training_status_algorithm_version="status",
    )
    return PlanningContext(
        request=request, preferences=prefs, goals=tuple(sorted(goals, key=lambda item: (item.event_date, item.priority, str(item.competition_goal_id)))),
        performance=PerformanceSnapshot(), training=training, training_status=None,
        versions=versions, warnings=(), fingerprint="0" * 64,
    )


def builder():
    return SeasonStructureBuilder(SeasonStructureConfig(version="season-config-1", algorithm_version="season-structure-1"))


@pytest.mark.parametrize("priority,role,taper,recovery", [("A", "primary", 14, 7), ("B", "supporting", 7, 3), ("C", "training", 0, 1)])
def test_priority_has_deterministic_structural_role(priority, role, taper, recovery):
    result = builder().build(context([goal(1, 90, priority)]))
    assert result.goals[0].role == role
    assert result.competition_markers[0].taper_days == taper
    assert result.competition_markers[0].recovery_days == recovery
    assert SeasonPhase.COMPETITION in {block.phase for block in result.blocks}


def test_a_b_c_and_b_after_a_remain_one_ordered_season():
    goals = [goal(1, 50, "B"), goal(2, 80, "A"), goal(3, 100, "C"), goal(4, 120, "B")]
    result = builder().build(context(goals))
    assert [item.priority for item in result.goals] == ["B", "A", "C", "B"]
    assert result.planning_end_date == START + timedelta(days=120)
    assert len(result.competition_markers) == 4


def test_two_separated_a_have_two_peaks_without_close_warning():
    result = builder().build(context([goal(1, 60), goal(2, 150)]))
    assert [item.role for item in result.goals] == ["primary", "primary"]
    assert "MULTIPLE_PRIMARY_GOALS_CLOSE" not in {item.code for item in result.warnings}


def test_close_a_and_b_during_taper_create_structured_conflicts():
    result = builder().build(context([goal(1, 60, "A"), goal(2, 68, "A"), goal(3, 55, "B")]))
    codes = {item.code for item in result.warnings}
    assert {"MULTIPLE_PRIMARY_GOALS_CLOSE", "GOAL_DURING_TAPER"} <= codes
    assert any(marker.conflict_codes for marker in result.competition_markers)


def test_custom_repeated_multisport_segments_are_preserved_as_disciplines():
    result = builder().build(context([goal(1, 80, "A", "duathlon", ("run", "bike", "run"))]))
    assert result.goals[0].disciplines == ("cycling", "running")


def test_category_is_only_a_fallback_when_historical_goal_has_no_segments():
    result = builder().build(context([goal(1, 80, "A", "aquathlon", ())]))
    assert result.goals[0].disciplines == ("running", "swimming")


def test_short_exact_start_and_past_horizons():
    short = builder().build(context([goal(1, 10)]))
    assert "SHORT_PREPARATION_HORIZON" in {item.code for item in short.warnings}
    exact = builder().build(context([goal(2, 0)]))
    assert exact.blocks[0].phase is SeasonPhase.COMPETITION
    with pytest.raises(SeasonStructureError):
        builder().build(context([goal(3, -1)], start=START))


def test_explicit_horizon_and_goal_exclusion_rule():
    far = goal(1, 100)
    result = builder().build(context([far], horizon=START + timedelta(days=120)))
    assert result.planning_end_date == START + timedelta(days=120)
    with pytest.raises(SeasonStructureError):
        builder().build(context([far], horizon=START + timedelta(days=99)))


@pytest.mark.parametrize("days,expected", [(7, set()), (3, set()), (1, {"MULTISPORT_AVAILABILITY_CONSTRAINT"}), (0, {"NO_TRAINING_AVAILABILITY", "MULTISPORT_AVAILABILITY_CONSTRAINT"})])
def test_availability_warnings_without_generating_sessions(days, expected):
    result = builder().build(context([goal(1, 80, "A", "triathlon", ("swim", "bike", "run"))], preferences(days)))
    codes = {item.code for item in result.warnings}
    assert expected <= codes
    if days == 0:
        assert next(item for item in result.warnings if item.code == "NO_TRAINING_AVAILABILITY").blocking


def test_configuration_changes_structure_deterministically():
    source = context([goal(1, 30)])
    first = builder().build(source)
    second = builder().build(source)
    changed = SeasonStructureBuilder(SeasonStructureConfig(version="season-config-2", algorithm_version="season-structure-1", taper_days_a=7)).build(source)
    assert first == second
    assert first != changed
