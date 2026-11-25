from collections import Counter
from datetime import timedelta
from decimal import Decimal
import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import AvailabilitySlot, PlanningPreferences, context_fingerprint
from app.domains.planning.session_planning import SessionPlanningConfig
from tests.test_session_planning import build
from tests.test_weekly_budget import context, preferences, goal
from tests.test_planning_preferences import athlete_env, add_user, add_athlete, authenticated_client, mutation_headers, payload, H


def tri(target=None, unavailable=None):
    prefs = preferences(1800, strength=2).model_copy(update={
        'availability_slots': tuple(AvailabilitySlot(weekday=i, available_minutes=300, max_sessions=2) for i in range(7) if i != unavailable),
        'max_sessions_per_day': 2, 'max_sessions_per_week': 12,
        'preferred_rest_days': (0,), 'target_sessions_per_week': target,
    })
    return context(goals=(goal(sports=('swim','bike','run')),), prefs=prefs)


@pytest.mark.parametrize('target', [5,6,7])
def test_exact_explicit_frequency_and_multisport(target):
    ctx = tri(target)
    plan, *_ = build(ctx)
    week = plan.weeks[0]
    counts = Counter(s.discipline for s in week.sessions)
    assert len(week.sessions) == target
    assert counts['strength'] == 2
    assert all(counts[s] >= 1 for s in ('running','cycling','swimming'))
    assert len({s.date for s in week.sessions}) == min(target,6)
    assert week.frequency_decision['source'] == 'EXPLICIT'
    assert not any(s.placement.context.get('strength_adjacencies', 0) for s in week.sessions)
    assert all(s.date.weekday() != 0 for s in week.sessions)


def test_legacy_null_keeps_five_not_maximum_and_trace():
    week = build(tri())[0].weeks[0]
    assert len(week.sessions) == 5
    assert week.frequency_decision['source'] == 'LEGACY_FALLBACK'
    assert week.frequency_decision['target_sessions_per_week'] is None


@pytest.mark.parametrize('value', [0,29,13])
def test_invalid_intent(value):
    with pytest.raises(ValidationError):
        PlanningPreferences.model_validate({**tri().preferences.model_dump(), 'target_sessions_per_week': value})


def test_unavailability_is_hard_but_compatible_double_can_meet_target():
    plan, *_ = build(tri(7, unavailable=3))
    week = plan.weeks[0]
    assert len(week.sessions) == 7
    assert all(s.date.weekday() != 3 for s in week.sessions)
    assert 'FREQUENCY_TARGET_CONSTRAINED' not in {w.code for w in week.warnings}


def test_unavailability_with_daily_one_reports_unmet_target():
    ctx=tri(7,unavailable=3)
    ctx=ctx.model_copy(update={'preferences':ctx.preferences.model_copy(update={'max_sessions_per_day':1})})
    week=build(ctx)[0].weeks[0]
    assert len(week.sessions)==6
    assert 'FREQUENCY_TARGET_CONSTRAINED' in {w.code for w in week.warnings}


def test_determinism_frequency_fingerprints_and_volume():
    plans = [build(tri(t))[0] for t in (5,6,7)]
    assert plans[1] == build(tri(6))[0]
    assert len({p.fingerprint for p in plans}) == 3
    assert len({p.weeks[0].budget_target_load for p in plans}) == 1
    assert len({p.weeks[0].planned_load for p in plans}) == 1


def test_null_preserves_legacy_preference_hash():
    old = tri().preferences.model_dump(exclude={'target_sessions_per_week'})
    assert context_fingerprint(old) == context_fingerprint(tri().preferences)


def test_target_too_low_for_full_week_composition_is_explicit_error():
    with pytest.raises(ValueError, match='cannot_preserve'):
        build(tri(3))


def test_api_intent_versions_and_athlete_isolation(athlete_env):
    db, _, app = athlete_env
    user = add_user(db, 'frequency-intent-user', account_plan='athlete')
    a = add_athlete(db, user, 'A', role='athlete', default=True)
    b = add_athlete(db, user, 'B')
    client = authenticated_client(app, user)
    headers = mutation_headers(client, **{H: str(a.id)})
    legacy = client.put('/planning/preferences', json=payload(), headers=headers)
    assert legacy.status_code == 200
    assert legacy.json()['preferences']['target_sessions_per_week'] is None
    body = {**payload(), 'target_sessions_per_week': 6}
    explicit = client.put('/planning/preferences', json=body, headers=headers)
    assert explicit.status_code == 200
    assert explicit.json()['version_number'] == 2
    assert explicit.json()['preferences']['target_sessions_per_week'] == 6
    assert client.put('/planning/preferences', json=body, headers=headers).json()['id'] == explicit.json()['id']
    assert client.get('/planning/preferences', headers={H: str(b.id)}).status_code == 404
    for invalid in (0,7,29):
        assert client.put('/planning/preferences', json={**body, 'target_sessions_per_week': invalid}, headers=headers).status_code == 422
