from decimal import Decimal
import pytest

from app.domains.planning.models import StructuredWorkoutDefinition, WorkoutNode, WorkoutDuration, WorkoutTarget
from app.domains.planning.prescribed_load import estimate_prescribed_load, reconcile_plan_load
from app.domains.planning.preview import preview_artifact_payload, build_preview_artifact
from app.domains.planning.contracts import context_fingerprint
from tests.test_planning_preview_artifact import artifact
from tests.test_session_planning import build
from tests.test_weekly_budget import historical_windows
from app.domains.planning.workout_builder import build_structured_workout, WorkoutBuilderConfig


def power_workout(seconds=3600):
    target = WorkoutTarget(metric='power', mode='percent_reference', reference='FTP', minimum=.4,maximum=.6,
        reference_value=200,reference_unit='watts',resolved_minimum=80,resolved_maximum=120,resolved_unit='watts')
    return StructuredWorkoutDefinition(schema_version=1,sport='cycling',steps=[
        WorkoutNode(kind='step',phase='work',title='Trabajo',duration=WorkoutDuration(mode='time',seconds=seconds),target=target)])


def test_reuses_existing_power_method_and_exposes_interval():
    result = estimate_prescribed_load(power_workout())
    assert (result.minimum, result.value, result.maximum) == (16,26,36)
    assert result.methods == ('cycling_power',)
    assert result.coverage == 'COMPLETE' and result.quality == 'MEDIUM'
    assert result == estimate_prescribed_load(power_workout())


def test_repetitions_are_counted_without_expanding_tree():
    source=power_workout()
    repeated=source.model_copy(update={'steps':[WorkoutNode(kind='repeat',repetitions=10,steps=source.steps)]})
    assert estimate_prescribed_load(repeated).value == 260


def test_distance_duration_is_explicitly_approximate():
    source=power_workout()
    source.steps[0].duration=WorkoutDuration(mode='distance',meters=1000,estimated_seconds=3600)
    result=estimate_prescribed_load(source)
    assert result.value == 26 and result.quality == 'LOW'
    assert result.estimated_duration_seconds == 3600


def test_unknown_duration_never_becomes_zero_load():
    source=power_workout()
    source.steps.append(source.steps[0].model_copy(update={'duration':WorkoutDuration(mode='open')}))
    result=estimate_prescribed_load(source)
    assert result.value is None and result.known_subtotal == 26
    assert result.coverage == 'PARTIAL' and result.unknown_steps == 1


def test_strength_uses_supported_rpe_proxy_only():
    source=power_workout()
    source.sport='strength'
    source.steps[0].target=WorkoutTarget(metric='rpe',mode='absolute_range',minimum=5,maximum=7)
    result=estimate_prescribed_load(source)
    assert (result.minimum,result.value,result.maximum) == (50,60,70)
    assert result.methods == ('strength_rpe',) and result.quality == 'LOW'


@pytest.mark.parametrize('metric', ['rpe','heart_rate'])
def test_unsupported_endurance_targets_do_not_invent_intensity(metric):
    source=power_workout()
    source.steps[0].target=WorkoutTarget(metric=metric,mode='absolute_range',minimum=5,maximum=7)
    result=estimate_prescribed_load(source)
    assert result.value == 50 and result.methods == ('duration_only',)
    assert result.quality == 'LOW' and result.coverage == 'PARTIAL'


def test_allocated_reduction_cannot_reduce_estimated_load():
    a=artifact()
    drafts=tuple(s.workout for s in a.sessions)
    before=reconcile_plan_load(a.session_plan,drafts)
    weeks=tuple(w.model_copy(update={'sessions':tuple(s.model_copy(update={'target_load':Decimal('0.01')}) for s in w.sessions)}) for w in a.session_plan.weeks)
    after=reconcile_plan_load(a.session_plan.model_copy(update={'weeks':weeks}),drafts)
    assert [w.prescribed_estimated_total for w in before.weeks] == [w.prescribed_estimated_total for w in after.weeks]
    assert before.weeks[0].allocated_total != after.weeks[0].allocated_total


def test_diagnostic_metadata_does_not_change_prescription_identity():
    a=artifact()
    without=a.model_copy(update={'load_reconciliation':None})
    assert a.load_reconciliation is not None
    assert context_fingerprint(preview_artifact_payload(a)) == context_fingerprint(preview_artifact_payload(without))
    assert a.fingerprint == without.fingerprint


@pytest.mark.parametrize('change', ['duration','target','workout','date','count'])
def test_prescription_changes_still_change_preview_fingerprint(change):
    from datetime import timedelta
    a=artifact()
    week=a.session_plan.weeks[0]
    prescriptions=list(week.sessions)
    drafts=[s.workout for s in a.sessions]
    s=prescriptions[0]
    draft=drafts[0]
    definition=draft.definition.model_copy(deep=True)
    if change == 'duration':
        prescriptions[0]=s.model_copy(update={'target_duration_minutes':s.target_duration_minutes+1})
        definition.steps[0].duration.seconds += 60
    elif change == 'target':
        target=definition.steps[0].target
        target.minimum = target.minimum * .99
        if target.resolved_minimum is not None:
            target.resolved_minimum *= .99
    elif change == 'workout':
        definition.steps[0].instructions='Instrucción revisada'
    elif change == 'date':
        prescriptions[0]=s.model_copy(update={'date':s.date+timedelta(days=-1 if s.date.weekday()==6 else 1)})
    else:
        prescriptions.append(s)
        drafts.insert(len(week.sessions),draft)
    drafts[0]=draft.model_copy(update={'definition':definition})
    plan=a.session_plan.model_copy(update={'weeks':(week.model_copy(update={'sessions':tuple(prescriptions)}),*a.session_plan.weeks[1:])})
    b=build_preview_artifact(athlete_id=a.athlete_id,timezone_name=a.timezone_name,
        context_fingerprint_value=a.context_fingerprint,season=a.season_structure,
        budgets=a.weekly_budget_plan,session_plan=plan,goals=a.goals,workout_drafts=tuple(drafts),
        algorithm_version=a.algorithm_version,configuration_version=a.configuration_version)
    assert b.fingerprint != a.fingerprint
