from collections import Counter
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.domains.planning.contracts import AvailabilitySlot, context_fingerprint
from app.domains.planning.session_planning import SessionType, SessionPlanningConfig
from app.domains.planning.weekly_distribution import distribute_week
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from tests.test_session_planning import build
from tests.test_weekly_budget import context, preferences


@pytest.fixture
def sample():
    ctx = context(prefs=preferences(strength=2))
    # Baseline generation remains available for date-only conservation checks.
    with patch('app.domains.planning.weekly_distribution.distribute_week', side_effect=lambda w, *a: w):
        plan, _, _, config = build(ctx)
    return ctx, plan.weeks[0], config


def fixture_week(sample, types, valid_days=range(5), doubles=False):
    ctx, week, config = sample
    slots = tuple(AvailabilitySlot(weekday=d, available_minutes=600, max_sessions=2 if doubles else 1) for d in valid_days)
    ctx = ctx.model_copy(update={'preferences': ctx.preferences.model_copy(update={
        'availability_slots': slots, 'max_sessions_per_day': 2 if doubles else 1,
        'preferred_rest_days': (), 'preferred_long_run_day': None, 'preferred_long_bike_day': None})})
    disciplines = {'GENERAL_STRENGTH': 'strength', 'RUN_LONG': 'running', 'RUN_EASY': 'running',
                   'RUN_RECOVERY': 'running', 'BIKE_LONG': 'cycling'}
    source = week.sessions[0]
    days = tuple(valid_days)
    sessions = tuple(source.model_copy(update={'date': week.week_start + timedelta(days=days[i % len(days)]),
        'session_type': SessionType(t), 'discipline': disciplines[t], 'target_duration_minutes': 30,
        'key_session': False}) for i, t in enumerate(types))
    return ctx, week.model_copy(update={'sessions': sessions}), config.model_copy(update={'allow_double_sessions': doubles})


@pytest.mark.parametrize('count,days', [(2, range(5)), (2, range(2)), (3, range(5)), (1, range(5))])
def test_strength_spacing(sample, count, days):
    ctx, week, config = fixture_week(sample, ['GENERAL_STRENGTH'] * count, days)
    result = distribute_week(week, ctx, config)
    dates = sorted(s.date for s in result.sessions)
    assert len(dates) == count
    assert all((b-a).days >= (2 if len(days) > 2 else 1) for a, b in zip(dates, dates[1:]))


@pytest.mark.parametrize('types', [(['RUN_EASY'] * 2), ['RUN_EASY', 'RUN_RECOVERY'], ['RUN_LONG', 'BIKE_LONG']])
def test_structural_adjacency(sample, types):
    ctx, week, config = fixture_week(sample, types)
    result = distribute_week(week, ctx, config)
    assert abs((result.sessions[1].date-result.sessions[0].date).days) > 1


def test_unavailable_and_competition(sample):
    ctx, week, config = fixture_week(sample, ['RUN_EASY'] * 2, [0, 2, 4])
    ctx = ctx.model_copy(update={'goals': (ctx.goals[0].model_copy(update={'event_date': week.week_start}),)})
    result = distribute_week(week, ctx, config)
    assert {s.date.weekday() for s in result.sessions} == {2, 4}


@pytest.mark.parametrize('start,end', [(2,6), (0,3)])
def test_partial_weeks(sample, start, end):
    ctx, week, config = fixture_week(sample, ['GENERAL_STRENGTH'] * 2, range(start,end+1))
    week = week.model_copy(update={'week_start': week.week_start+timedelta(days=start),
                                   'week_end': week.week_start+timedelta(days=end)})
    result = distribute_week(week, ctx, config)
    assert all(week.week_start <= s.date <= week.week_end for s in result.sessions)


def test_fixed_manual_session_is_untouched(sample):
    ctx, week, config = fixture_week(sample, ['GENERAL_STRENGTH'] * 2)
    fixed = week.sessions[0].model_copy(update={'flexible': False})
    week = week.model_copy(update={'sessions': (fixed, week.sessions[1])})
    result = distribute_week(week, ctx, config)
    assert fixed in result.sessions


def test_doubles(sample):
    ctx, week, config = fixture_week(sample, ['RUN_EASY'] * 2, [0], True)
    result = distribute_week(week, ctx, config)
    assert len(result.sessions) == 2
    assert len({s.date for s in result.sessions}) == 1


def test_determinism_and_fingerprints(sample):
    ctx, week, config = fixture_week(sample, ['GENERAL_STRENGTH'] * 2)
    a = distribute_week(week, ctx, config)
    b = distribute_week(week, ctx, config)
    assert a == b
    assert context_fingerprint(a) == context_fingerprint(b)
    assert context_fingerprint(a) != context_fingerprint(week)


def test_unchanged_calendar_has_unchanged_metadata(sample):
    ctx, week, config = fixture_week(sample, ['GENERAL_STRENGTH'] * 2, [0, 1])
    assert distribute_week(week, ctx, config) is week


@pytest.mark.parametrize('field', ['target_duration_minutes', 'target_load', 'load_floor', 'load_ceiling', 'purpose', 'intensity'])
def test_content_conserved(sample, field):
    ctx, week, config = sample
    result = distribute_week(week, ctx, config)
    assert Counter(getattr(s, field) for s in result.sessions) == Counter(getattr(s, field) for s in week.sessions)


def test_workouts_and_targets_conserved(sample):
    ctx, week, config = sample
    result = distribute_week(week, ctx, config)
    wc = WorkoutBuilderConfig(version='test', algorithm_version='test')
    def definitions(w):
        return sorted(str(build_structured_workout(ctx, s, wc).definition) for s in w.sessions)
    assert definitions(week) == definitions(result)


def test_explicit_date_override_uses_new_date_for_workout(sample):
    ctx, week, config = fixture_week(sample, ['GENERAL_STRENGTH'] * 2)
    result = distribute_week(week, ctx, config)
    source = result.sessions[0]
    copied = source.model_copy(update={'date': source.date + timedelta(days=7)})
    clean = copied.model_copy(update={'placement': week.sessions[0].placement})
    wc = WorkoutBuilderConfig(version='test', algorithm_version='test')
    assert build_structured_workout(ctx, copied, wc).definition == build_structured_workout(ctx, clean, wc).definition


def test_full_plan_content_and_volume_conserved():
    ctx = context(prefs=preferences(strength=2))
    with patch('app.domains.planning.weekly_distribution.distribute_week', side_effect=lambda w, *a: w):
        before, *_ = build(ctx)
    after, *_ = build(ctx)
    for a, b in zip(before.weeks, after.weeks):
        def content(w):
            return sorted(str(s.model_dump(exclude={'date', 'placement'})) for s in w.sessions)
        assert content(a) == content(b)
        assert a.planned_load == b.planned_load
    assert after.fingerprint != before.fingerprint


def test_unchanged_final_calendar_keeps_session_plan_fingerprint():
    prefs = preferences().model_copy(update={
        'availability_slots': (AvailabilitySlot(weekday=0, available_minutes=600, max_sessions=1),),
        'max_sessions_per_week': 1, 'strength_sessions_per_week': 0,
    })
    ctx = context(prefs=prefs)
    with patch('app.domains.planning.weekly_distribution.distribute_week', side_effect=lambda w, *a: w):
        before, *_ = build(ctx)
    after, *_ = build(ctx)
    repeated, *_ = build(ctx)
    assert before == after == repeated
    assert before.fingerprint == after.fingerprint == repeated.fingerprint
