from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.domains.planning.contracts import (
    AthleteTrainingSnapshot, AvailabilitySlot, ContextVersions, PerformanceSnapshot,
    PlanningContext, PlanningGoal, PlanningGoalSegment, PlanningPreferences,
    PlanningRequest, SportTrainingSnapshot, TrainingStatusSnapshot,
    TrainingWindowSnapshot,
)
from app.domains.planning.season_structure import SeasonStructureBuilder, SeasonStructureConfig
from app.domains.planning.weekly_budget import (
    BudgetConfidence, WeeklyBudgetConfig, build_weekly_budget_plan,
)


START = date(2026, 1, 5)


def goal(number=1, days=84, priority="A", sports=("run",)):
    return PlanningGoal(
        competition_goal_id=UUID(f"00000000-0000-0000-0000-{number:012d}"),
        event_date=START + timedelta(days=days), timezone_name="Europe/Madrid",
        category="custom", event_format="custom", priority=priority,
        segments=tuple(PlanningGoalSegment(position=index, sport=sport, distance_m=1000 * index) for index, sport in enumerate(sports, 1)),
        status="active",
    )


def preferences(minutes=600, strength=0):
    per_day = minutes // 6
    remainder = minutes - per_day * 6
    return PlanningPreferences(
        availability_slots=tuple(AvailabilitySlot(
            weekday=day, available_minutes=per_day + (remainder if day == 5 else 0), max_sessions=1,
        ) for day in range(6)),
        max_sessions_per_day=1, max_sessions_per_week=6,
        preferred_rest_days=(6,), strength_sessions_per_week=strength,
    )


def sports(load=Decimal("0"), strength=Decimal("0"), duration=0):
    values = {"running": load, "cycling": Decimal(0), "swimming": Decimal(0), "strength": strength}
    return tuple(SportTrainingSnapshot(
        sport=sport, activity_count=4 if value else 0, training_days=4 if value else 0,
        duration_seconds=duration if value else 0, training_load=value,
        loaded_activity_count=4 if value else 0, missing_load_activity_count=0,
    ) for sport, value in values.items())


def historical_windows(recent=Decimal("400"), prior21=Decimal("400"), prior14=Decimal("400"), prior48=Decimal("400"), *, coverage="complete", quality="high", include=True, strength=Decimal("0")):
    if not include:
        return ()
    totals = {
        7: recent,
        28: recent + prior21 * 3,
        42: recent + prior21 * 3 + prior14 * 2,
        90: recent + prior21 * 3 + prior14 * 2 + prior48 * (Decimal(48) / 7),
    }
    weekly_seconds = Decimal(420 * 60)
    windows = []
    for days in (7, 28, 42, 90):
        total = totals[days]
        duration = int(weekly_seconds * Decimal(days) / 7)
        strength_total = strength * Decimal(days) / 7
        windows.append(TrainingWindowSnapshot(
            days=days, start_date=START - timedelta(days=days), end_date=START - timedelta(days=1),
            activity_count=max(1, days // 2), training_days=max(1, days // 2),
            total_duration_seconds=duration, total_training_load=total + strength_total,
            endurance_load=total, strength_load=strength_total,
            load_coverage=coverage, load_quality=quality, load_days_available=max(1, days // 2),
            sports=sports(total, strength_total, duration),
        ))
    return tuple(windows)


def context(goals=None, *, windows=None, prefs=None, start=START, horizon=None, status=None):
    goals = tuple(goals or (goal(),))
    prefs = prefs or preferences()
    windows = historical_windows() if windows is None else windows
    request = PlanningRequest(
        athlete_id=UUID("10000000-0000-0000-0000-000000000001"),
        planning_date=start, timezone_name="Europe/Madrid",
        goal_ids=tuple(item.competition_goal_id for item in goals), start_date=start,
        horizon_end_date=horizon, preferences=prefs,
        algorithm_version="context-test", configuration_version="context-config",
    )
    training = AthleteTrainingSnapshot(
        planning_date=start, timezone_name="Europe/Madrid",
        observation_start=start - timedelta(days=90), observation_end=start - timedelta(days=1),
        observed_days=90, activities_available=bool(windows), status_available=status is not None,
        windows=windows,
    )
    versions = ContextVersions(
        planning_algorithm_version="context-test", configuration_version="context-config",
        training_load_algorithm_version="0.7b.1", load_aggregation_algorithm_version="0.7c.1",
        manual_strength_algorithm_version="0.7e.1", training_status_algorithm_version="0.7f.1",
    )
    return PlanningContext(
        request=request, preferences=prefs, goals=goals,
        performance=PerformanceSnapshot(), training=training, training_status=status,
        versions=versions, warnings=(), fingerprint="a" * 64,
    )


def plan(ctx, config=None):
    season = SeasonStructureBuilder(SeasonStructureConfig(version="season-1", algorithm_version="season-algorithm-1")).build(ctx)
    return build_weekly_budget_plan(ctx, season, config or WeeklyBudgetConfig(version="budget-1", algorithm_version="budget-algorithm-1"))


def test_stable_baseline_uses_robust_non_overlapping_bands():
    result = plan(context())
    assert result.baseline.weekly_load == Decimal("400.00")
    assert result.baseline.confidence is BudgetConfidence.HIGH
    assert result.baseline.load_samples == (Decimal("400.00"),) * 4
    assert result.budgets[0].load_floor <= result.budgets[0].target_load <= result.budgets[0].load_ceiling


def test_low_recent_week_and_high_outlier_do_not_dominate_baseline():
    low = plan(context(windows=historical_windows(recent=Decimal("40"))))
    high = plan(context(windows=historical_windows(prior14=Decimal("1600"))))
    assert low.baseline.weekly_load == Decimal("400.00")
    assert high.baseline.weekly_load == Decimal("400.00")


def test_known_zero_is_distinct_from_missing_load():
    zero = plan(context(windows=historical_windows(Decimal(0), Decimal(0), Decimal(0), Decimal(0))))
    missing = plan(context(windows=()))
    assert zero.baseline.weekly_load == 0 and zero.baseline.known_zero
    assert missing.baseline.weekly_load is None and not missing.baseline.known_zero
    assert all(item.target_load is None for item in missing.budgets)
    assert "WEEKLY_LOAD_BASELINE_UNAVAILABLE" in {item.code for item in missing.warnings}


def test_availability_cap_uses_athlete_load_per_minute_when_reliable():
    roomy = plan(context(prefs=preferences(600)))
    constrained = plan(context(prefs=preferences(180)))
    assert roomy.budgets[0].maximum_feasible_load > constrained.budgets[0].maximum_feasible_load
    assert constrained.budgets[0].load_ceiling < roomy.budgets[0].load_ceiling
    assert constrained.budgets[0].target_load <= constrained.budgets[0].maximum_feasible_load
    assert constrained.budgets[0].load_ceiling <= constrained.budgets[0].maximum_feasible_load
    assert "AVAILABILITY_CAP" in {item.code for item in constrained.budgets[0].adjustments}


def test_progression_is_bounded_deterministic_and_periodically_deloads():
    ctx = context(goals=(goal(days=140),))
    result = plan(ctx)
    repeated = plan(ctx)
    assert result == repeated
    normal = [item for item in result.budgets if not {"TAPER", "RECOVERY", "COMPETITION"} & {a.code for a in item.adjustments}]
    deload_index = next(index for index, item in enumerate(normal) if "DELOAD" in {a.code for a in item.adjustments})
    assert normal[deload_index + 1].target_load > normal[deload_index].target_load
    assert max(item.target_load for item in result.budgets if item.target_load is not None) <= Decimal("480.00")
    non_deload = [item for item in normal if "DELOAD" not in {a.code for a in item.adjustments}]
    for left, right in zip(non_deload, non_deload[1:]):
        assert right.target_load <= left.target_load * Decimal("1.25")


def test_taper_a_is_stronger_than_b_and_c_has_no_taper():
    a = plan(context(goals=(goal(days=28, priority="A"),)))
    b = plan(context(goals=(goal(days=28, priority="B"),)))
    c = plan(context(goals=(goal(days=28, priority="C"),)))
    taper_a = next(item for item in a.budgets if "TAPER" in {x.code for x in item.adjustments})
    taper_b = next(item for item in b.budgets if "TAPER" in {x.code for x in item.adjustments})
    assert taper_a.target_load < taper_b.target_load
    assert not any("TAPER" in {x.code for x in item.adjustments} for item in c.budgets)


def test_partial_taper_week_uses_daily_exposure():
    result = plan(context(goals=(goal(days=31, priority="A"),)))
    mixed = next(item for item in result.budgets if len(item.phase_exposure) > 1 and any(x.phase.value == "TAPER" for x in item.phase_exposure))
    taper = next(item for item in mixed.phase_exposure if item.phase.value == "TAPER")
    assert Decimal(0) < taper.share < Decimal(1)


def test_recovery_and_competition_are_date_exposed_not_iso_shifted():
    result = plan(context(goals=(goal(days=28, priority="A"),), horizon=START + timedelta(days=36)))
    competition = next(item for item in result.budgets if item.competition_reserved_capacity)
    recovery = next(item for item in result.budgets if "RECOVERY" in {x.code for x in item.adjustments})
    assert competition.competition_goal_ids
    assert any(item.phase.value == "RECOVERY" for item in recovery.phase_exposure)


def test_multiple_goals_remain_one_budget_trajectory_and_keep_warning():
    goals = (goal(1, 42, "B"), goal(2, 55, "A"), goal(3, 65, "A"))
    result = plan(context(goals=goals))
    assert len({(item.iso_year, item.iso_week) for item in result.budgets}) == len(result.budgets)
    assert "MULTIPLE_PRIMARY_GOALS_CLOSE" in {item.code for item in result.season_warnings}


def allocation(sports_sequence):
    result = plan(context(goals=(goal(sports=sports_sequence),)))
    return {item.discipline: item for item in result.budgets[0].disciplines}


def test_running_and_multisport_allocations_follow_goal_segments():
    running = allocation(("run",))
    triathlon = allocation(("swim", "bike", "run"))
    duathlon = allocation(("run", "bike", "run"))
    aquathlon = allocation(("swim", "run"))
    assert running["running"].target_share > Decimal("0.50")
    assert set(triathlon) == {"running", "cycling", "swimming"}
    assert duathlon["running"].target_share > duathlon["cycling"].target_share
    assert set(aquathlon) == {"running", "swimming"}
    for budgets in (running, triathlon, duathlon, aquathlon):
        assert sum(item.target_share for item in budgets.values()) == Decimal("1.00")
    triathlon_budget = plan(context(goals=(goal(sports=("swim", "bike", "run")),))).budgets[0]
    assert sum(item.target_load for item in triathlon_budget.disciplines) == triathlon_budget.target_load


def test_single_cycling_swimming_and_custom_segments_are_not_invented():
    cycling = allocation(("bike",))
    swimming = allocation(("swim",))
    custom = allocation(("swim", "run", "bike", "run"))
    assert set(cycling) == {"cycling"}
    assert set(swimming) == {"swimming"}
    assert set(custom) == {"running", "cycling", "swimming"}


def test_segment_time_not_raw_load_points_drives_multisport_share():
    source = goal(sports=("swim", "bike", "run")).model_copy(update={"segments":(
        PlanningGoalSegment(position=1, sport="swim", distance_m=1900),
        PlanningGoalSegment(position=2, sport="bike", distance_m=82000),
        PlanningGoalSegment(position=3, sport="run", distance_m=21000),
    )})
    budgets = plan(context(goals=(source,))).budgets[0].disciplines
    shares = {item.discipline:item.target_share for item in budgets}
    assert shares["cycling"] > shares["running"] > shares["swimming"]


def test_strength_is_reserved_without_invented_load_and_uses_history_when_known():
    unknown = plan(context(prefs=preferences(strength=2)))
    known = plan(context(prefs=preferences(strength=2), windows=historical_windows(strength=Decimal("40"))))
    unknown_strength = next(item for item in unknown.budgets[0].disciplines if item.discipline == "strength")
    known_strength = next(item for item in known.budgets[0].disciplines if item.discipline == "strength")
    assert unknown_strength.target_load is None
    assert sum(item.target_share for item in unknown.budgets[0].disciplines if item.target_share is not None) == Decimal("1.00")
    assert "STRENGTH_LOAD_BASELINE_UNAVAILABLE" in {item.code for item in unknown.warnings}
    assert known_strength.target_load is not None
    assert sum(item.target_share for item in known.budgets[0].disciplines) == Decimal("1.00")
    assert sum(item.target_load for item in known.budgets[0].disciplines) == known.budgets[0].target_load


def test_partial_week_year_boundary_and_timezone_are_explicit():
    start = date(2026, 12, 30)
    ctx = context(goals=(goal(days=365),), start=start, horizon=date(2027, 1, 5))
    result = plan(ctx)
    assert result.budgets[0].week_start == start
    assert result.budgets[0].week_end == date(2027, 1, 3)
    assert result.budgets[0].available_days_in_horizon == 5
    assert result.budgets[0].iso_year == 2026 and result.budgets[0].iso_week == 53
    assert result.timezone_name == "Europe/Madrid"


def test_status_is_only_a_first_week_guardrail_and_never_boosts():
    status = TrainingStatusSnapshot(
        local_date=START - timedelta(days=1), total_load=Decimal("500"),
        fitness=Decimal("100"), fatigue=Decimal("130"), form=Decimal("-30"),
        history_days=100, is_warmup=False,
        training_load_algorithm_version="0.7b.1", manual_strength_algorithm_version="0.7e.1",
        training_status_algorithm_version="0.7f.1",
    )
    moderated = plan(context(status=status))
    normal = plan(context())
    assert moderated.budgets[0].target_load < normal.budgets[0].target_load
    assert "STATUS_MODERATION" in {item.code for item in moderated.budgets[0].adjustments}
    assert not any("STATUS_MODERATION" in {x.code for x in item.adjustments} for item in moderated.budgets[1:])


def test_fingerprint_is_stable_and_config_versioned():
    ctx = context()
    first = plan(ctx)
    second = plan(ctx)
    changed = plan(ctx, WeeklyBudgetConfig(version="budget-2", algorithm_version="budget-algorithm-1", taper_factor_a=Decimal("0.65")))
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_low_coverage_is_not_presented_as_high_confidence():
    result = plan(context(windows=historical_windows(coverage="partial", quality="low")))
    assert result.baseline.confidence is not BudgetConfidence.HIGH
    assert result.baseline.robust_load_per_minute is None
    assert {"LOW_LOAD_COVERAGE", "AVAILABILITY_CAP_UNKNOWN"} <= {item.code for item in result.warnings}
