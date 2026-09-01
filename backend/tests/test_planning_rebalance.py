from datetime import date, timedelta
from decimal import Decimal

from app.domains.planning.contracts import AvailabilitySlot, PerformanceSnapshot, PlanningGoalSegment, PlanningPreferences
from app.domains.planning.preview import build_preview_artifact
from app.domains.planning.season_structure import SeasonPhase
from app.domains.planning.session_planning import SessionType, _swim_duration
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
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


def with_swim_history(minutes=34):
    result=[]
    for window in with_long_history():
        sports=tuple(item.model_copy(update={"activity_count":4,"training_days":4,"duration_seconds":4*minutes*60,"longest_duration_seconds":minutes*60}) if window.days==28 and item.sport=="swimming" else item for item in window.sports)
        result.append(window.model_copy(update={"sports":sports}))
    return tuple(result)


def triathlon_with_swim_distance(distance, *, days=49):
    result=multisport_goal(days=days)
    return result.model_copy(update={"segments":tuple(item.model_copy(update={"distance_m":distance}) if item.sport=="swim" else item for item in result.segments)})


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


def test_multisport_multiweek_sequence_rotates_quality_and_swim_without_macro_growth():
    secondary=goal(1,14,"B",("run",));primary=multisport_goal()
    result,_,_,_=build(context(goals=(secondary,primary),prefs=wide_preferences(),windows=with_long_history(),horizon=primary.event_date))
    sessions=[item for week in result.weeks for item in week.sessions]
    run_quality={item.session_type for item in sessions if item.session_type in {SessionType.RUN_TEMPO,SessionType.RUN_THRESHOLD,SessionType.RUN_INTERVAL} and item.phase not in {SeasonPhase.TAPER,SeasonPhase.RECOVERY}}
    bike_quality={item.session_type for item in sessions if item.session_type in {SessionType.BIKE_TEMPO,SessionType.BIKE_THRESHOLD,SessionType.BIKE_INTERVAL} and item.phase not in {SeasonPhase.TAPER,SeasonPhase.RECOVERY}}
    run_long_quality=any(item.session_type is SessionType.RUN_LONG and item.phase in {SeasonPhase.BUILD,SeasonPhase.SPECIFIC} and (item.target_duration_minutes or 0)>=75 for item in sessions)
    assert run_quality and (len(run_quality) >= 2 or run_long_quality)
    assert bike_quality or any(item.session_type is SessionType.BIKE_LONG and item.phase in {SeasonPhase.BUILD,SeasonPhase.SPECIFIC} for item in sessions)
    swim_types={item.session_type for item in sessions if item.discipline=="swimming"}
    assert {SessionType.SWIM_TECHNIQUE,SessionType.SWIM_AEROBIC} <= swim_types
    assert any(item.session_type in {SessionType.SWIM_AEROBIC,SessionType.SWIM_THRESHOLD} and item.phase is SeasonPhase.SPECIFIC for item in sessions)
    assert all(len(week.sessions)<=9 for week in result.weeks)


def test_swim_duration_progresses_by_objective_phase_type_and_availability():
    secondary=goal(1,14,"B",("run",));primary=triathlon_with_swim_distance(1900)
    prefs=wide_preferences(minutes=60)
    ctx=context(goals=(secondary,primary),prefs=prefs,windows=with_swim_history(),horizon=primary.event_date)
    ctx=ctx.model_copy(update={"performance":PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110"))})
    result,_,budgets,_=build(ctx)
    swims=[item for week in result.weeks for item in week.sessions if item.discipline=="swimming"]
    durations=[item.target_duration_minutes for item in swims]
    assert len(set(durations))>1
    by_phase={phase:[item.target_duration_minutes for item in swims if item.phase is phase] for phase in SeasonPhase}
    assert max(by_phase[SeasonPhase.SPECIFIC])>=min(by_phase[SeasonPhase.MAINTENANCE])
    assert max(by_phase[SeasonPhase.TAPER])<max(by_phase[SeasonPhase.MAINTENANCE])
    slots={item.weekday:item for item in prefs.availability_slots}
    assert all(item.target_duration_minutes<=slots[item.date.weekday()].available_minutes for item in swims)
    assert all(len(week.sessions)<=budget.max_sessions for week,budget in zip(result.weeks,budgets.budgets))
    assert all(week.planned_load is None or budget.load_ceiling is None or week.planned_load<=budget.load_ceiling for week,budget in zip(result.weeks,budgets.budgets))


def test_swim_recovery_duration_is_reduced_from_specific():
    primary=triathlon_with_swim_distance(1900)
    ctx=context(goals=(primary,),prefs=wide_preferences(),windows=with_swim_history(),horizon=primary.event_date)
    ctx=ctx.model_copy(update={"performance":PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110"))})
    _,_,budgets,config=build(ctx)
    source=budgets.budgets[0]
    recovery=_swim_duration(ctx,source.model_copy(update={"dominant_phase":SeasonPhase.RECOVERY}),SessionType.SWIM_EASY,config,40)
    specific=_swim_duration(ctx,source.model_copy(update={"dominant_phase":SeasonPhase.SPECIFIC}),SessionType.SWIM_AEROBIC,config,40)
    assert recovery<specific


def test_swim_objective_distance_influences_duration_monotonically():
    maxima=[]
    for distance in (750,1900,3800):
        primary=triathlon_with_swim_distance(distance)
        ctx=context(goals=(primary,),prefs=wide_preferences(),windows=with_swim_history(),horizon=primary.event_date)
        ctx=ctx.model_copy(update={"performance":PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110"))})
        result,_,_,_=build(ctx)
        maxima.append(max(item.target_duration_minutes for week in result.weeks for item in week.sessions if item.discipline=="swimming"))
    assert maxima[0]<maxima[1]<maxima[2]


def test_real_b10k_plus_a1900m_regression_is_not_a_flat_34_minutes():
    start=date(2026,8,30)
    secondary=goal(1,14,"B",("run",)).model_copy(update={"event_date":date(2026,9,13)})
    primary=triathlon_with_swim_distance(1900).model_copy(update={"event_date":date(2026,10,17)})
    ctx=context(goals=(secondary,primary),start=start,horizon=primary.event_date,prefs=wide_preferences(),windows=with_swim_history())
    ctx=ctx.model_copy(update={"performance":PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110"))})
    result,_,_,_=build(ctx)
    swims=[item for week in result.weeks for item in week.sessions if item.discipline=="swimming"]
    durations=[item.target_duration_minutes for item in swims]
    assert durations and len(set(durations))>=3 and durations!=[34]*len(durations)
    assert max(item.target_duration_minutes for item in swims if item.phase is SeasonPhase.SPECIFIC)>=max(item.target_duration_minutes for item in swims if item.phase is SeasonPhase.MAINTENANCE)


def _workout_leaves(nodes):
    for node in nodes:
        if node.kind=="repeat": yield from _workout_leaves(node.steps)
        else: yield node


def test_multisport_preview_every_generated_leaf_has_explicit_title():
    secondary=goal(1,14,"B",("run",));primary=triathlon_with_swim_distance(1900)
    ctx=context(goals=(secondary,primary),prefs=wide_preferences(),windows=with_swim_history(),horizon=primary.event_date)
    ctx=ctx.model_copy(update={"performance":PerformanceSnapshot(cycling_ftp_watts=Decimal("200"),running_threshold_pace_seconds_per_km=Decimal("300"),swimming_css_seconds_per_100m=Decimal("110"))})
    result,_,_,_=build(ctx);config=WorkoutBuilderConfig(version="workouts-test",algorithm_version="workouts-test")
    drafts=[build_structured_workout(ctx,item,config) for week in result.weeks for item in week.sessions if item.session_type is not SessionType.COMPETITION]
    leaves=[leaf for draft in drafts for leaf in _workout_leaves(draft.definition.steps)]
    assert leaves and all(leaf.title is not None and leaf.title.strip() for leaf in leaves)


def test_cross_week_same_sport_longs_keep_prudent_spacing():
    event=goal(1,14,"B",("run",)).model_copy(update={"event_date":date(2026,9,13)})
    prefs=wide_preferences().model_copy(update={"preferred_long_run_day":2})
    result,_,_,_=build(context(goals=(event,),start=date(2026,8,30),horizon=date(2026,9,13),prefs=prefs,windows=with_long_history()))
    longs=sorted(item.date for week in result.weeks for item in week.sessions if item.session_type is SessionType.RUN_LONG)
    assert all((right-left).days>=5 for left,right in zip(longs,longs[1:]))


def test_strength_is_never_placed_d1_or_d2_before_any_priority_race():
    sunday=goal(1,14,"B",("run",)).model_copy(update={"event_date":date(2026,9,13)})
    result,_,_,_=build(context(goals=(sunday,),start=date(2026,8,30),horizon=sunday.event_date,prefs=wide_preferences(),windows=with_long_history()))
    strength=[item for week in result.weeks for item in week.sessions if item.discipline=="strength"]
    assert not any(timedelta(0)<sunday.event_date-item.date<=timedelta(days=2) for item in strength)


def test_quality_replacement_recomputes_budget_quota_from_final_session_types():
    secondary=goal(1,14,"B",("run",));primary=triathlon_with_swim_distance(1900)
    result,_,_,_=build(context(goals=(secondary,primary),prefs=wide_preferences(),windows=with_swim_history(),horizon=primary.event_date))
    week=next(week for week in result.weeks if any(item.session_type is SessionType.RUN_THRESHOLD for item in week.sessions))
    long=next(item for item in week.sessions if item.session_type is SessionType.BIKE_LONG)
    endurance=next(item for item in week.sessions if item.session_type is SessionType.BIKE_ENDURANCE)
    assert abs(long.target_load/endurance.target_load-Decimal("1.35"))<Decimal("0.01")


def test_single_b_and_b_plus_a_regressions_preserve_relative_roles_and_guards():
    single=goal(1,14,"B",("run",)).model_copy(update={"event_date":date(2026,9,13)})
    single_ctx=context(goals=(single,),start=date(2026,8,30),horizon=single.event_date,prefs=wide_preferences(),windows=with_long_history())
    single_plan,single_season,_,_=build(single_ctx)
    assert single_season.goals[0].role=="primary"
    single_sessions=[item for week in single_plan.weeks for item in week.sessions]
    assert any(item.session_type in {SessionType.RUN_TEMPO,SessionType.RUN_THRESHOLD,SessionType.RUN_INTERVAL,SessionType.RUN_LONG} for item in single_sessions)
    assert all((right-left).days>=5 for left,right in zip(sorted(item.date for item in single_sessions if item.session_type is SessionType.RUN_LONG),sorted(item.date for item in single_sessions if item.session_type is SessionType.RUN_LONG)[1:]))
    assert any(item.phase is SeasonPhase.TAPER for item in single_sessions)
    workout_config=WorkoutBuilderConfig(version="workouts-test",algorithm_version="workouts-test")
    single_leaves=[leaf for item in single_sessions if item.session_type is not SessionType.COMPETITION for leaf in _workout_leaves(build_structured_workout(single_ctx,item,workout_config).definition.steps)]
    assert single_leaves and all(leaf.title and leaf.title.strip() for leaf in single_leaves)
    assert not any(timedelta(0)<single.event_date-item.date<=timedelta(days=2) for item in single_sessions if item.discipline=="strength")
    primary=triathlon_with_swim_distance(1900).model_copy(update={"event_date":date(2026,10,17)})
    ctx=context(goals=(single,primary),start=date(2026,8,30),horizon=primary.event_date,prefs=wide_preferences(),windows=with_swim_history())
    ctx=ctx.model_copy(update={"performance":PerformanceSnapshot(cycling_ftp_watts=Decimal("200"),running_threshold_pace_seconds_per_km=Decimal("300"),swimming_css_seconds_per_100m=Decimal("110"))})
    plan,season,_,_=build(ctx)
    assert {item.priority:item.role for item in season.goals}=={"A":"primary","B":"supporting"}
    swims=[item.target_duration_minutes for week in plan.weeks for item in week.sessions if item.discipline=="swimming"]
    assert len(set(swims))>1
    assert not any(timedelta(0)<goal_date-item.date<=timedelta(days=2) for goal_date in (single.event_date,primary.event_date) for week in plan.weeks for item in week.sessions if item.discipline=="strength")


def test_single_b_complete_preview_checks_every_recursive_leaf_title():
    single=goal(1,14,"B",("run",)).model_copy(update={"event_date":date(2026,9,13)})
    ctx=context(goals=(single,),start=date(2026,8,30),horizon=single.event_date,prefs=wide_preferences(),windows=with_long_history())
    plan,season,budgets,_=build(ctx)
    config=WorkoutBuilderConfig(version="workouts-test",algorithm_version="workouts-test")
    prescriptions=tuple(item for week in plan.weeks for item in week.sessions)
    drafts=tuple(build_structured_workout(ctx,item,config) for item in prescriptions)
    artifact=build_preview_artifact(
        athlete_id=ctx.request.athlete_id,timezone_name=ctx.request.timezone_name,
        context_fingerprint_value=ctx.fingerprint,season=season,budgets=budgets,
        session_plan=plan,goals=ctx.goals,workout_drafts=drafts,
        algorithm_version="workouts-test",configuration_version="workouts-test",
    )
    session_types={item.prescription.session_type for item in artifact.sessions}
    assert {SessionType.RUN_LONG,SessionType.RUN_TEMPO,SessionType.RUN_EASY,SessionType.RUN_RECOVERY,SessionType.GENERAL_STRENGTH}<=session_types
    strength_phases={item.prescription.phase for item in artifact.sessions if item.prescription.session_type is SessionType.GENERAL_STRENGTH}
    assert {SeasonPhase.MAINTENANCE,SeasonPhase.TAPER}<=strength_phases
    leaves=[leaf for item in artifact.sessions if item.workout.definition for leaf in _workout_leaves(item.workout.definition.steps)]
    assert leaves and all(leaf.title is not None and leaf.title.strip() for leaf in leaves)


def test_realistic_b_plus_a_quality_zones_taper_and_macroplan_regression():
    secondary=goal(1,14,"B",("run",)).model_copy(update={"event_date":date(2026,9,13)})
    primary=triathlon_with_swim_distance(1900).model_copy(update={"event_date":date(2026,10,17)})
    base=context(goals=(secondary,primary),start=date(2026,8,30),horizon=primary.event_date,prefs=wide_preferences(),windows=with_swim_history())
    ctx=base.model_copy(update={"performance":PerformanceSnapshot(
        cycling_ftp_watts=Decimal("140"),running_threshold_pace_seconds_per_km=Decimal("260"),
        swimming_css_seconds_per_100m=Decimal("110"),
    )})
    plan,_,_,_=build(ctx);baseline,_,_,_=build(base)
    shape=lambda value:[(item.date,item.session_type,item.target_load) for week in value.weeks for item in week.sessions]
    assert shape(plan)==shape(baseline)
    config=WorkoutBuilderConfig(version="quality-test",algorithm_version="quality-test")
    built=[(item,build_structured_workout(ctx,item,config)) for week in plan.weeks for item in week.sessions if item.session_type is not SessionType.COMPETITION]
    by_type={}
    for item,draft in built: by_type.setdefault(item.session_type,[]).append((item,draft))
    bike_threshold=by_type[SessionType.BIKE_THRESHOLD][0][1]
    threshold_targets=[leaf.target for leaf in _workout_leaves(bike_threshold.definition.steps) if leaf.phase=="work"]
    assert any(target.minimum==.95 and target.maximum==1.05 and target.resolved_minimum==133 and target.resolved_maximum==147 for target in threshold_targets)
    assert all(not (leaf.target and leaf.target.minimum>=.95) for _,draft in by_type[SessionType.BIKE_LONG] for leaf in _workout_leaves(draft.definition.steps) if leaf.phase=="work")
    recovery=next(leaf.target for _,draft in by_type[SessionType.RUN_RECOVERY] for leaf in _workout_leaves(draft.definition.steps) if leaf.phase=="work")
    easy=next(leaf.target for _,draft in by_type[SessionType.RUN_EASY] for leaf in _workout_leaves(draft.definition.steps) if leaf.phase=="work" and leaf.title!="Activación corta")
    assert recovery.minimum>=easy.maximum
    source_run=next(item for item,_ in built if item.discipline=="running" and item.phase is not SeasonPhase.TAPER)
    tempo_draft=build_structured_workout(ctx,source_run.model_copy(update={"session_type":SessionType.RUN_TEMPO}),config)
    threshold_draft=build_structured_workout(ctx,source_run.model_copy(update={"session_type":SessionType.RUN_THRESHOLD}),config)
    tempo=next(leaf.target for leaf in _workout_leaves(tempo_draft.definition.steps) if leaf.phase=="work")
    threshold=next(leaf.target for leaf in _workout_leaves(threshold_draft.definition.steps) if leaf.phase=="work")
    assert tempo.minimum>threshold.minimum and tempo.maximum>threshold.maximum
    for kind in (SessionType.SWIM_AEROBIC,SessionType.SWIM_THRESHOLD):
        for _,draft in by_type.get(kind,[]):
            targets=[leaf.target for leaf in _workout_leaves(draft.definition.steps) if leaf.phase=="work" and leaf.target and leaf.target.metric=="swim_pace"]
            if kind is SessionType.SWIM_AEROBIC:
                assert any(target.minimum>=1.05 for target in targets)
                assert all(target.minimum>=1.05 or target.minimum<=1<=target.maximum for target in targets)
            else: assert any(target.minimum<=1<=target.maximum for target in targets)
    taper_activations=[leaf for item,draft in built if item.phase is SeasonPhase.TAPER for leaf in _workout_leaves(draft.definition.steps) if leaf.title=="Activación corta"]
    assert taper_activations and all(leaf.duration.seconds<=60 for leaf in taper_activations)
