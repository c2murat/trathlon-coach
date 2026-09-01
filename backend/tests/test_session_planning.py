from datetime import timedelta
from decimal import Decimal

from app.domains.planning.contracts import AvailabilitySlot, PlanningPreferences
from app.domains.planning.season_structure import SeasonStructureBuilder, SeasonStructureConfig
from app.domains.planning.session_planning import (
    SessionPlanningConfig, SessionType, build_session_plan, validate_session_plan,
)
from app.domains.planning.weekly_budget import WeeklyBudgetConfig, build_weekly_budget_plan
from tests.test_weekly_budget import START, context, goal, historical_windows, preferences


def build(ctx, config=None):
    season = SeasonStructureBuilder(
        SeasonStructureConfig(version="season-1", algorithm_version="season-algorithm-1"),
    ).build(ctx)
    budgets = build_weekly_budget_plan(
        ctx, season, WeeklyBudgetConfig(version="budget-1", algorithm_version="budget-algorithm-1"),
    )
    config = config or SessionPlanningConfig(version="sessions-1", algorithm_version="sessions-algorithm-1")
    return build_session_plan(ctx, season, budgets, config), season, budgets, config


def with_running_frequency(activity_count=8):
    windows = historical_windows()
    updated = []
    for window in windows:
        sports = tuple(
            sport.model_copy(update={"activity_count": activity_count, "training_days": activity_count})
            if window.days == 28 and sport.sport == "running" else sport
            for sport in window.sports
        )
        updated.append(window.model_copy(update={"sports": sports}))
    return tuple(updated)


def constrained_budget_fixture():
    prefs = PlanningPreferences(
        availability_slots=(
            AvailabilitySlot(weekday=1, available_minutes=90, max_sessions=2),
            AvailabilitySlot(weekday=3, available_minutes=90, max_sessions=2),
        ),
        max_sessions_per_day=2, max_sessions_per_week=3,
        preferred_rest_days=(), strength_sessions_per_week=0,
    )
    ctx = context(prefs=prefs, windows=with_running_frequency())
    season = SeasonStructureBuilder(
        SeasonStructureConfig(version="season-1", algorithm_version="season-algorithm-1"),
    ).build(ctx)
    budgets = build_weekly_budget_plan(
        ctx, season, WeeklyBudgetConfig(version="budget-1", algorithm_version="budget-algorithm-1"),
    )
    first = budgets.budgets[0]
    running = first.disciplines[0].model_copy(update={"target_load": Decimal("120.00")})
    first = first.model_copy(update={
        "target_load": Decimal("120.00"), "load_floor": Decimal("100.00"),
        "load_ceiling": Decimal("130.00"), "disciplines": (running,),
    })
    budgets = budgets.model_copy(update={"budgets": (first, *budgets.budgets[1:])})
    config = SessionPlanningConfig(version="sessions-1", algorithm_version="sessions-algorithm-1")
    return ctx, season, budgets, config


def test_running_week_selects_long_quality_and_easy_with_spacing():
    result, _, _, _ = build(context(windows=with_running_frequency()))
    sessions = result.weeks[0].sessions
    assert {item.session_type for item in sessions} == {
        SessionType.RUN_LONG, SessionType.RUN_TEMPO, SessionType.RUN_EASY,
    }
    keys = sorted(item.date for item in sessions if item.key_session)
    assert (keys[1] - keys[0]).days >= 2


def test_multisport_representation_follows_goal_segments():
    for sports, expected in (
        (("swim", "bike", "run"), {"swimming", "cycling", "running"}),
        (("run", "bike", "run"), {"running", "cycling"}),
        (("swim", "run"), {"swimming", "running"}),
    ):
        result, _, _, _ = build(context(goals=(goal(sports=sports),)))
        represented = {item.discipline for item in result.weeks[0].sessions}
        assert expected <= represented


def test_strength_frequency_is_preserved_without_inventing_load():
    result, _, _, _ = build(context(prefs=preferences(strength=2)))
    strength = [item for item in result.weeks[0].sessions if item.discipline == "strength"]
    assert len(strength) == 2
    assert all(item.target_load is None for item in strength)
    quantified = sum((item.target_load for item in result.weeks[0].sessions if item.target_load is not None), Decimal(0))
    assert result.weeks[0].planned_load == quantified


def test_preferred_long_day_is_used_when_feasible():
    prefs = preferences().model_copy(update={"preferred_long_run_day": 5})
    result, _, _, _ = build(context(prefs=prefs))
    long_run = next(item for item in result.weeks[0].sessions if item.session_type is SessionType.RUN_LONG)
    assert long_run.date.weekday() == 5
    assert long_run.placement.preferred_date_used


def test_no_availability_places_no_training_and_emits_warnings():
    prefs = PlanningPreferences(
        availability_slots=(), max_sessions_per_day=1, max_sessions_per_week=1,
        preferred_rest_days=(), strength_sessions_per_week=0,
    )
    result, _, _, _ = build(context(prefs=prefs))
    assert not result.weeks[0].sessions
    assert "SESSION_PLACEMENT_CONSTRAINT" in {item.code for item in result.weeks[0].warnings}


def test_limited_availability_never_exceeds_daily_capacity():
    prefs = PlanningPreferences(
        availability_slots=(AvailabilitySlot(weekday=2, available_minutes=60, max_sessions=1),),
        max_sessions_per_day=1, max_sessions_per_week=1,
        preferred_rest_days=(), strength_sessions_per_week=0,
    )
    result, _, _, _ = build(context(prefs=prefs, windows=with_running_frequency()))
    assert len(result.weeks[0].sessions) <= 1
    assert all(item.date.weekday() == 2 for item in result.weeks[0].sessions)


def test_competition_is_fixed_to_goal_date_without_invented_load_or_duration():
    event = goal(days=6)
    result, _, _, _ = build(context(goals=(event,), horizon=event.event_date))
    competition = next(item for item in result.weeks[0].sessions if item.session_type is SessionType.COMPETITION)
    assert competition.date == event.event_date
    assert competition.target_load is None and competition.target_duration_minutes is None
    assert sum(item.date == event.event_date for item in result.weeks[0].sessions) == 1


def test_partial_week_respects_horizon_dates():
    wednesday = START + timedelta(days=2)
    result, _, _, _ = build(context(start=wednesday, horizon=goal().event_date))
    assert result.weeks[0].week_start == wednesday
    assert all(item.date >= wednesday for item in result.weeks[0].sessions)


def test_missing_load_keeps_session_load_unknown():
    result, _, _, _ = build(context(windows=()))
    training = [item for item in result.weeks[0].sessions if item.session_type is not SessionType.COMPETITION]
    assert training and all(item.target_load is None for item in training)
    assert "SESSION_LOAD_TARGET_UNAVAILABLE" in {item.code for item in result.weeks[0].warnings}


def test_fingerprint_is_stable_input_only_and_config_versioned():
    ctx = context()
    first, _, _, _ = build(ctx)
    repeated, _, _, _ = build(ctx)
    changed, _, _, _ = build(ctx, SessionPlanningConfig(version="sessions-2", algorithm_version="sessions-algorithm-1"))
    assert first == repeated
    assert first.fingerprint != changed.fingerprint
    assert "fingerprint" not in {
        "context_fingerprint", "weekly_budget_fingerprint", "config",
    }


def test_0_8f_9_version_metadata_does_not_change_functional_output():
    ctx = context(windows=with_running_frequency())
    legacy, _, _, _ = build(ctx, SessionPlanningConfig(version="0.8F.8", algorithm_version="0.8F.8"))
    current, _, _, _ = build(ctx, SessionPlanningConfig(version="0.8F.9", algorithm_version="0.8F.9"))

    def without_version_metadata(plan):
        payload = plan.model_dump(mode="json")
        payload.pop("algorithm_version")
        payload.pop("configuration_version")
        payload.pop("fingerprint")
        for week in payload["weeks"]:
            for session in week["sessions"]:
                session.pop("rule_version")
        return payload

    assert current.configuration_version == "0.8F.9"
    assert current.algorithm_version == "0.8F.9"
    assert {session.rule_version for week in current.weeks for session in week.sessions} == {"0.8F.9"}
    assert without_version_metadata(current) == without_version_metadata(legacy)


def test_validator_detects_unavailable_overbook_excess_and_bad_competition():
    result, season, budgets, config = build(context())
    week = result.weeks[0]
    unavailable = week.sessions[0].model_copy(update={"date": week.week_start + timedelta(days=6)})
    overbook = week.sessions[0].model_copy(update={"target_duration_minutes": 1000})
    duplicate = week.sessions[0].model_copy(update={"session_type": SessionType.RUN_EASY})
    competition_week = next(item for item in result.weeks if any(s.session_type is SessionType.COMPETITION for s in item.sessions))
    competition = next(s for s in competition_week.sessions if s.session_type is SessionType.COMPETITION)
    bad_competition = competition.model_copy(update={"date": competition.date - timedelta(days=1)})
    changed = []
    for item in result.weeks:
        if item.week_start == week.week_start:
            changed.append(item.model_copy(update={"sessions": (unavailable, overbook, duplicate)}))
        elif item.week_start == competition_week.week_start:
            changed.append(item.model_copy(update={"sessions": (bad_competition,)}))
        else:
            changed.append(item)
    invalid = result.model_copy(update={"weeks": tuple(changed)})
    issues = validate_session_plan(invalid, context(), season, budgets, config)
    assert {
        "SESSION_ON_UNAVAILABLE_DAY", "DAILY_MINUTES_EXCEEDED",
        "DAILY_SESSION_LIMIT_EXCEEDED", "COMPETITION_DATE_INVALID",
    } <= {item.code for item in issues}


def test_taper_and_recovery_use_budget_without_a_second_load_multiplier():
    result, _, budgets, _ = build(context(goals=(goal(days=28),), horizon=START + timedelta(days=36)))
    by_week = {(item.iso_year, item.iso_week): item for item in budgets.budgets}
    taper = next(item for item in result.weeks if any(session.phase.value == "TAPER" for session in item.sessions))
    recovery = next(item for item in result.weeks if any(session.phase.value == "RECOVERY" for session in item.sessions))
    assert taper.budget_target_load == by_week[(taper.iso_year, taper.iso_week)].target_load
    assert recovery.budget_target_load == by_week[(recovery.iso_year, recovery.iso_week)].target_load
    assert not any(
        session.session_type in {SessionType.RUN_LONG, SessionType.RUN_THRESHOLD, SessionType.RUN_INTERVAL}
        for session in taper.sessions
    )
    assert all(
        session.session_type in {SessionType.RUN_RECOVERY, SessionType.COMPETITION}
        for session in recovery.sessions
    )


def test_load_allocation_is_exact_when_all_discipline_loads_are_known():
    result, _, budgets, _ = build(context(windows=historical_windows(strength=Decimal("40")), prefs=preferences(strength=1)))
    assert result.weeks[0].planned_load == budgets.budgets[0].target_load
    assert result.weeks[0].load_delta == Decimal("0.00")


def test_dropped_session_load_is_not_redistributed_and_floor_yields_warning():
    ctx, season, budgets, config = constrained_budget_fixture()
    result = build_session_plan(ctx, season, budgets, config)
    week = result.weeks[0]
    quantified = sum((item.target_load for item in week.sessions if item.target_load is not None), Decimal(0))
    assert len(week.sessions) == 2
    assert quantified == week.planned_load < week.budget_target_load
    assert week.load_delta == week.planned_load - week.budget_target_load
    assert week.planned_load < budgets.budgets[0].load_floor
    assert "WEEKLY_LOAD_BUDGET_UNDERSHOT" in {item.code for item in week.warnings}


def test_validator_detects_ceiling_and_missing_materialization_warning():
    ctx, season, budgets, config = constrained_budget_fixture()
    result = build_session_plan(ctx, season, budgets, config)
    week = result.weeks[0]
    excessive = week.sessions[0].model_copy(update={"target_load": Decimal("131.00")})
    invalid_week = week.model_copy(update={
        "sessions": (excessive,), "planned_load": Decimal("131.00"),
        "load_delta": Decimal("11.00"), "warnings": (),
    })
    invalid = result.model_copy(update={"weeks": (invalid_week, *result.weeks[1:])})
    codes = {item.code for item in validate_session_plan(invalid, ctx, season, budgets, config)}
    assert "WEEKLY_LOAD_CEILING_EXCEEDED" in codes

    missing_warning_week = week.model_copy(update={"warnings": ()})
    missing_warning = result.model_copy(update={"weeks": (missing_warning_week, *result.weeks[1:])})
    codes = {item.code for item in validate_session_plan(missing_warning, ctx, season, budgets, config)}
    assert "WEEKLY_LOAD_WARNING_MISSING" in codes

    mismatched_week = week.model_copy(update={
        "iso_week": week.iso_week + 1,
        "budget_target_load": week.budget_target_load + Decimal("1.00"),
    })
    mismatched = result.model_copy(update={"weeks": (mismatched_week, *result.weeks[1:])})
    codes = {item.code for item in validate_session_plan(mismatched, ctx, season, budgets, config)}
    assert {"WEEK_BUDGET_IDENTITY_MISMATCH", "WEEK_BUDGET_TARGET_MISMATCH"} <= codes


def test_competition_consumes_weekly_capacity_and_keeps_day_exclusive():
    prefs = preferences().model_copy(update={"max_sessions_per_week": 4})
    event = goal(days=6)
    ctx = context(goals=(event,), prefs=prefs, windows=with_running_frequency(activity_count=12), horizon=event.event_date)
    result, season, budgets, config = build(ctx, SessionPlanningConfig(
        version="sessions-1", algorithm_version="sessions-algorithm-1", allow_double_sessions=True,
    ))
    week = result.weeks[0]
    assert len(week.sessions) < 4  # A taper reduces frequency instead of filling the limit.
    competition = next(item for item in week.sessions if item.session_type is SessionType.COMPETITION)
    assert sum(item.date == competition.date for item in week.sessions) == 1

    extra = next(item for item in week.sessions if item.session_type is not SessionType.COMPETITION).model_copy(
        update={"date": competition.date},
    )
    invalid_week = week.model_copy(update={"sessions": (*week.sessions, extra, extra, extra)})
    invalid = result.model_copy(update={"weeks": (invalid_week,)})
    codes = {item.code for item in validate_session_plan(invalid, ctx, season, budgets, config)}
    assert "WEEKLY_SESSION_LIMIT_EXCEEDED" in codes
    assert "COMPETITION_DAY_NOT_EXCLUSIVE" in codes
