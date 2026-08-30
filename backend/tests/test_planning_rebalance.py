from datetime import timedelta

from app.domains.planning.contracts import AvailabilitySlot, PlanningGoalSegment, PlanningPreferences
from app.domains.planning.season_structure import SeasonPhase
from app.domains.planning.session_planning import SessionType
from tests.test_session_planning import build
from tests.test_weekly_budget import START, context, goal, historical_windows


def wide_preferences(*, rest=(0,), minutes=180):
    return PlanningPreferences(
        availability_slots=tuple(AvailabilitySlot(
            weekday=day, available_minutes=min(120 if day < 5 else 180, minutes), max_sessions=2,
        ) for day in range(7)),
        max_sessions_per_day=2, max_sessions_per_week=9,
        preferred_rest_days=rest, preferred_long_run_day=6,
        preferred_long_bike_day=5, strength_sessions_per_week=1,
    )


def multisport_goal(number=2, days=49, priority="A"):
    return goal(number, days, priority, ("swim", "bike", "run")).model_copy(update={"segments":(
        PlanningGoalSegment(position=1, sport="swim", distance_m=1900),
        PlanningGoalSegment(position=2, sport="bike", distance_m=82000),
        PlanningGoalSegment(position=3, sport="run", distance_m=21000),
    )})


def with_long_history(minutes=60):
    result=[]
    for window in historical_windows():
        sports=tuple(item.model_copy(update={"longest_duration_seconds":minutes*60}) if window.days==28 and item.sport in {"cycling","running"} else item for item in window.sports)
        result.append(window.model_copy(update={"sports":sports}))
    return tuple(result)


def test_generic_a_triathlon_and_nearby_b_regression_properties():
    secondary=goal(1,14,"B",("run",))
    primary=multisport_goal()
    result,_,_,_=build(context(goals=(secondary,primary),prefs=wide_preferences(),windows=with_long_history(),horizon=primary.event_date))
    full_non_race=[week for week in result.weeks if (week.week_end-week.week_start).days==6 and not any(item.session_type is SessionType.COMPETITION for item in week.sessions)]
    assert sum(bool(week.rest_dates) for week in full_non_race) > len(full_non_race)//2
    assert all(len(week.sessions)<9 for week in result.weeks)
    before_b=[item for week in result.weeks if week.week_start<secondary.event_date for item in week.sessions]
    assert {"running","cycling","swimming"} <= {item.discipline for item in before_b}
    long_bikes=[item.target_duration_minutes for week in result.weeks for item in week.sessions if item.session_type is SessionType.BIKE_LONG]
    assert max(long_bikes)>60 and len(set(long_bikes))>1
    long_runs=[item.target_duration_minutes for week in result.weeks for item in week.sessions if item.session_type is SessionType.RUN_LONG]
    assert max(long_runs)>60
    competitions=[item for week in result.weeks for item in week.sessions if item.session_type is SessionType.COMPETITION]
    assert {item.date for item in competitions}=={secondary.event_date,primary.event_date}
    assert not any(item.discipline=="strength" and timedelta(0)<primary.event_date-item.date<=timedelta(days=2) for week in result.weeks for item in week.sessions)


def test_rest_preference_is_reserved_and_impossible_case_warns():
    result,_,_,_=build(context(prefs=wide_preferences(rest=(0,))))
    assert all(item.date.weekday()!=0 for item in result.weeks[0].sessions)
    only=PlanningPreferences(availability_slots=(AvailabilitySlot(weekday=0,available_minutes=90,max_sessions=1),),max_sessions_per_day=1,max_sessions_per_week=3,preferred_rest_days=(0,),strength_sessions_per_week=0)
    constrained,_,_,_=build(context(prefs=only))
    assert "PREFERRED_REST_DAY_UNAVAILABLE" in {item.code for item in constrained.weeks[0].warnings}


def test_long_sessions_progress_are_availability_capped_and_taper_removes_them():
    primary=multisport_goal(days=70)
    roomy,_,_,_=build(context(goals=(primary,),prefs=wide_preferences(),windows=with_long_history(),horizon=primary.event_date))
    values=[item.target_duration_minutes for week in roomy.weeks for item in week.sessions if item.session_type is SessionType.BIKE_LONG]
    assert values[0]>60 and max(values)>values[0]
    limited,_,_,_=build(context(goals=(primary,),prefs=wide_preferences(minutes=60),windows=with_long_history(),horizon=primary.event_date))
    assert all(item.target_duration_minutes<=60 for week in limited.weeks for item in week.sessions if item.session_type is SessionType.BIKE_LONG)
    assert not any(item.session_type in {SessionType.BIKE_LONG,SessionType.RUN_LONG} and item.phase is SeasonPhase.TAPER for week in roomy.weeks for item in week.sessions)


def test_a_taper_reduces_frequency_more_than_b():
    a,_,_,_=build(context(goals=(goal(days=13,priority="A"),),prefs=wide_preferences(),horizon=START+timedelta(days=13)))
    b,_,_,_=build(context(goals=(goal(days=13,priority="B"),),prefs=wide_preferences(),horizon=START+timedelta(days=13)))
    a_taper=next(week for week in a.weeks if any(item.phase is SeasonPhase.TAPER for item in week.sessions))
    b_taper=next(week for week in b.weeks if any(item.phase is SeasonPhase.TAPER for item in week.sessions))
    assert len(a_taper.sessions)<len(b_taper.sessions)


def test_long_objective_caps_can_exceed_legacy_default_plateaus():
    primary=multisport_goal(days=70)
    result,_,_,_=build(context(goals=(primary,),prefs=wide_preferences(),windows=with_long_history(),horizon=primary.event_date))
    bike=[item.target_duration_minutes for week in result.weeks for item in week.sessions if item.session_type is SessionType.BIKE_LONG]
    run=[item.target_duration_minutes for week in result.weeks for item in week.sessions if item.session_type is SessionType.RUN_LONG]
    assert max(bike)>120
    assert max(run)>80


def test_specific_triathlon_preserves_structural_long_sessions_before_quality():
    primary=multisport_goal(days=70)
    result,_,_,_=build(context(goals=(primary,),prefs=wide_preferences(),windows=with_long_history(),horizon=primary.event_date))
    specific=[week for week in result.weeks if any(item.phase is SeasonPhase.SPECIFIC for item in week.sessions)]
    assert specific
    assert all(any(item.session_type is SessionType.BIKE_LONG for item in week.sessions) for week in specific)
    assert all(any(item.session_type is SessionType.RUN_LONG for item in week.sessions) for week in specific)


def test_strength_underrepresentation_uses_requested_frequency():
    satisfied,_,_,_=build(context(prefs=wide_preferences(),windows=with_long_history()))
    assert not any(item.code=="DISCIPLINE_UNDERREPRESENTED" and item.context.get("discipline")=="strength" for item in satisfied.weeks[0].warnings)
    none=wide_preferences().model_copy(update={"strength_sessions_per_week":0})
    absent,_,_,_=build(context(prefs=none,windows=with_long_history()))
    assert not any(item.code=="DISCIPLINE_UNDERREPRESENTED" and item.context.get("discipline")=="strength" for item in absent.weeks[0].warnings)


def test_one_day_partial_week_suppresses_non_evaluable_weekly_warnings():
    primary=multisport_goal()
    result,_,_,_=build(context(start=START+timedelta(days=6),goals=(primary,),prefs=wide_preferences(rest=(6,)),windows=with_long_history(),horizon=primary.event_date))
    suppressed={"DISCIPLINE_UNDERREPRESENTED","WEEKLY_LOAD_BUDGET_UNDERSHOT","PREFERRED_LONG_DAY_UNAVAILABLE","PREFERRED_REST_DAY_UNAVAILABLE"}
    assert not (suppressed & {item.code for item in result.weeks[0].warnings})


def test_competition_on_preferred_rest_day_is_not_a_rest_violation():
    event=goal(days=6,priority="B")
    prefs=wide_preferences(rest=(event.event_date.weekday(),))
    result,_,_,_=build(context(goals=(event,),prefs=prefs,horizon=event.event_date))
    race_week=next(week for week in result.weeks if any(item.session_type is SessionType.COMPETITION for item in week.sessions))
    assert "PREFERRED_REST_DAY_UNAVAILABLE" not in {item.code for item in race_week.warnings}
