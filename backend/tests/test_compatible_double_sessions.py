from collections import Counter
from datetime import timedelta
from unittest.mock import patch
from functools import lru_cache

import pytest

from app.domains.planning.contracts import AvailabilitySlot
from app.domains.planning.session_planning import SessionType
from app.domains.planning.session_compatibility import pair_cost
from app.domains.planning.weekly_distribution import distribute_week, MAX_SEARCH_NODES
from app.domains.planning.workout_builder import build_structured_workout, WorkoutBuilderConfig
from tests.test_frequency_intent import tri
from tests.test_session_planning import build
from tests.test_weekly_budget import goal


def content(week):
    return sorted(str(s.model_dump(exclude={'date','placement'})) for s in week.sessions)


def test_six_total_can_use_five_days_and_keep_preferred_monday_free():
    ctx = tri(6, unavailable=3)
    with patch('app.domains.planning.weekly_distribution.distribute_week', side_effect=lambda w,*a:w):
        before, *_, config = build(ctx)
    after = build(ctx)[0]
    week = after.weeks[0]
    assert len(week.sessions) == 6  # Includes two strength; never 6 + 2.
    assert sum(s.discipline == 'strength' for s in week.sessions) == 2
    assert len({s.date for s in week.sessions}) == 5
    assert all(s.date.weekday() not in {0,3} for s in week.sessions)
    assert not any(w.code=='PREFERRED_REST_DAY_UNAVAILABLE' for w in week.warnings)
    assert max(Counter(s.date for s in week.sessions).values()) == 2
    assert content(week) == content(before.weeks[0])
    assert after == build(ctx)[0]
    assert all(s.placement.context.get('search_nodes',0) <= MAX_SEARCH_NODES for s in week.sessions)
    for day in {s.date for s in week.sessions}:
        group = [s for s in week.sessions if s.date==day]
        assert sum(s.key_session for s in group) <= 1
        if len(group)>1:
            assert pair_cost(*group,ctx) is not None


def test_seven_can_keep_monday_free_without_adding_sessions():
    ctx = tri(7)
    week = build(ctx)[0].weeks[0]
    assert len(week.sessions)==7
    assert all(s.date.weekday()!=0 for s in week.sessions)
    assert len({s.date for s in week.sessions})==6


@lru_cache(maxsize=1)
def shared_tri_plan():
    return build(tri(6))


def pair_week(sports, category, legs, minutes=120, daily=2, days=(1,)):
    ctx = tri(6)
    week = shared_tri_plan()[0].weeks[0]
    slots = tuple(AvailabilitySlot(weekday=d,available_minutes=minutes,max_sessions=2) for d in days)
    ctx = ctx.model_copy(update={'goals':(goal(sports=legs).model_copy(update={'category':category}),),
        'preferences':ctx.preferences.model_copy(update={'availability_slots':slots,'max_sessions_per_day':daily,'preferred_rest_days':(),'preferred_long_run_day':None,'preferred_long_bike_day':None})})
    mapping={'strength':'GENERAL_STRENGTH','swimming':'SWIM_TECHNIQUE','running':'RUN_EASY','cycling':'BIKE_EASY'}
    sessions=tuple(week.sessions[0].model_copy(update={'date':week.week_start+timedelta(days=days[i%len(days)]),
        'discipline':sport,'session_type':SessionType(mapping[sport]),'key_session':False,'target_duration_minutes':30}) for i,sport in enumerate(sports))
    return ctx,week.model_copy(update={'sessions':sessions}),shared_tri_plan()[3]


@pytest.mark.parametrize('sports,category,legs',[
    (('swimming','strength'),'triathlon',('swim','bike','run')),
    (('cycling','running'),'triathlon',('swim','bike','run')),
    (('cycling','running'),'duathlon',('run','bike','run')),
    (('swimming','running'),'aquathlon',('swim','run')),
])
def test_supported_pairs_can_share_one_day(sports,category,legs):
    ctx,week,config=pair_week(sports,category,legs)
    assert pair_cost(*week.sessions,ctx) is not None
    after=distribute_week(week,ctx,config)
    assert len(after.sessions)==2
    assert len({s.date for s in after.sessions})==1
    assert content(after)==content(week)


@pytest.mark.parametrize('minutes,daily',[(120,1),(50,2)])
def test_capacity_or_insufficient_minutes_prevents_double(minutes,daily):
    ctx,week,config=pair_week(('swimming','strength'),'triathlon',('swim','bike','run'),minutes,daily,(1,3))
    after=distribute_week(week,ctx,config)
    assert len({s.date for s in after.sessions})==2
    assert content(after)==content(week)


def test_two_key_sessions_stay_on_separate_days():
    ctx,week,config=pair_week(('cycling','running'),'duathlon',('run','bike','run'),days=(1,3,5))
    week=week.model_copy(update={'sessions':tuple(s.model_copy(update={'key_session':True}) for s in week.sessions)})
    assert pair_cost(*week.sessions,ctx) is None
    assert len({s.date for s in distribute_week(week,ctx,config).sessions})==2


@pytest.mark.parametrize('sports,category,legs', [
    (('swimming', 'strength'), 'TRIATHLON', ('swim', 'bike', 'run')),
    (('cycling', 'running'), 'TRIATHLON', ('run',)),
    (('cycling', 'running'), 'DUATHLON', ('run',)),
    (('swimming', 'running'), 'AQUATHLON', ('run',)),
])
def test_compatible_double_actually_frees_a_preferred_rest_day(sports, category, legs):
    ctx, week, config = pair_week(sports, category, legs, minutes=60, days=(0, 2))
    ctx = ctx.model_copy(update={'preferences': ctx.preferences.model_copy(update={
        'preferred_rest_days': (0,),
    })})
    assert len({s.date for s in week.sessions}) == 2
    after = distribute_week(week, ctx, config)
    assert len(after.sessions) == 2
    assert {s.date.weekday() for s in after.sessions} == {2}
    assert sum(s.target_duration_minutes for s in after.sessions) == 60
    assert content(after) == content(week)
    assert after == distribute_week(week, ctx, config)


def test_slot_limit_prevents_double_even_when_global_limit_allows_it():
    ctx, week, config = pair_week(('swimming', 'strength'), 'triathlon', ('swim', 'bike', 'run'), days=(0, 2))
    ctx = ctx.model_copy(update={'preferences': ctx.preferences.model_copy(update={
        'preferred_rest_days': (0,),
        'availability_slots': tuple(s.model_copy(update={'max_sessions': 1}) for s in ctx.preferences.availability_slots),
    })})
    after = distribute_week(week, ctx, config)
    assert len({s.date for s in after.sessions}) == 2


def test_incompatible_pair_cannot_free_a_preferred_rest_day():
    ctx, week, config = pair_week(('swimming', 'cycling'), 'triathlon', ('swim', 'bike', 'run'), days=(0, 2))
    ctx = ctx.model_copy(update={'preferences': ctx.preferences.model_copy(update={
        'preferred_rest_days': (0,),
    })})
    assert pair_cost(*week.sessions, ctx) is None
    assert len({s.date for s in distribute_week(week, ctx, config).sessions}) == 2


def test_doubles_are_not_used_when_separate_days_preserve_rest_and_spacing():
    ctx, week, config = pair_week(('swimming', 'strength'), 'triathlon', ('swim', 'bike', 'run'), days=(1, 4))
    assert len({s.date for s in distribute_week(week, ctx, config).sessions}) == 2


def test_legacy_null_keeps_its_calendar_and_identity():
    ctx=tri()
    before=build(ctx)[0]
    # The new placement policy is explicitly gated by declared frequency.
    assert before==build(ctx)[0]
    assert all(len({s.date for s in w.sessions})==len(w.sessions) for w in before.weeks)


def test_redistribution_of_an_existing_artifact_preserves_workout_anchor():
    ctx=tri(7)
    plan,*_,config=build(ctx)
    week=plan.weeks[0]
    wc=WorkoutBuilderConfig(version='test',algorithm_version='test')
    after=distribute_week(week,ctx,config)
    def definitions(w):
        return sorted(str(build_structured_workout(ctx,s,wc).definition) for s in w.sessions)
    assert definitions(after)==definitions(week)
    assert after==distribute_week(week,ctx,config)
