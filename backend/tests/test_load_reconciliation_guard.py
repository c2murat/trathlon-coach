from decimal import Decimal

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.domains.planning.prescribed_load import reconcile_plan_load
from app.domains.planning.preview import build_preview_artifact
from app.application.planning_preview import PlanningPreviewApplication, PlanningPreviewLoadNotReconciledError
from app.db.models import TrainingPlan, TrainingPlanPreview, PlannedTrainingSession, StructuredWorkout
from tests.test_planning_preview_artifact import artifact
from tests.test_planning_preview_application import seeded
from tests.test_prescribed_load import power_workout
from app.domains.planning.session_planning import SessionType


def guarded_artifact(budget):
    source = artifact()
    week = source.session_plan.weeks[0]
    prescription = week.sessions[0].model_copy(update={"discipline": "cycling", "session_type": SessionType.BIKE_EASY})
    # Single complete numeric prescription, with a deliberately controlled
    # budget. Existing calculator gives 26 units for this power interval.
    draft = source.sessions[0].workout.model_copy(update={'definition': power_workout(), 'session_type': SessionType.BIKE_EASY})
    plan = source.session_plan.model_copy(update={
        'weeks': (week.model_copy(update={'sessions': (prescription,), 'budget_target_load': Decimal(budget)}),),
        'planning_end': week.week_end,
    })
    return build_preview_artifact(athlete_id=source.athlete_id, timezone_name=source.timezone_name,
        context_fingerprint_value=source.context_fingerprint, season=source.season_structure,
        budgets=source.weekly_budget_plan, session_plan=plan, goals=source.goals,
        workout_drafts=(draft,), algorithm_version=source.algorithm_version,
        configuration_version=source.configuration_version)


@pytest.mark.parametrize('budget,expected', [('26','RECONCILED'), ('22.61','RECONCILED'), ('22.60','REVIEW_REQUIRED'), ('40','REVIEW_REQUIRED')])
def test_generic_threshold_and_both_variance_directions(budget, expected):
    a = guarded_artifact(budget)
    w = a.load_reconciliation.weeks[0]
    assert w.reconciliation_state == expected
    assert w.acceptance_blocked == (expected == 'NOT_RECONCILED')


def test_exact_tolerance_boundary_is_inclusive():
    a = guarded_artifact('100')
    definition = power_workout(4140)
    definition.steps[0].target.resolved_minimum = 200
    definition.steps[0].target.resolved_maximum = 200
    definition.steps[0].target.minimum = 1
    definition.steps[0].target.maximum = 1
    draft = a.sessions[0].workout.model_copy(update={'definition': definition})
    result = reconcile_plan_load(a.session_plan, (draft,))
    assert result.weeks[0].prescribed_estimated_total == 115
    assert result.weeks[0].variance_percent == 15
    assert result.weeks[0].reconciliation_state == 'RECONCILED'


def test_low_complete_keeps_quality_warning_without_hiding_known_variance():
    from app.domains.planning.prescribed_load import reconciliation_state
    for within, state in [(True,'RECONCILED'), (False,'REVIEW_REQUIRED')]:
        assert reconciliation_state(within_tolerance=within, coverage='COMPLETE', quality='LOW', session_count=1) == state
    a = artifact()
    assert all(w.quality_warning for w in a.load_reconciliation.weeks)
    assert any(w.reconciliation_state == 'INSUFFICIENT_QUALITY' for w in a.load_reconciliation.weeks)


def calibrated_policy_test_double(source):
    """Future server evidence, not a promotion of today's estimator quality."""
    from app.domains.planning.prescribed_load import reconciliation_state
    weeks = tuple(w.model_copy(update={
        'blocking_confidence': True,
        'reconciliation_state': reconciliation_state(within_tolerance=w.within_tolerance,
            coverage=w.coverage, quality=w.quality, session_count=len(w.sessions), blocking_confidence=True),
        'acceptance_blocked': not w.within_tolerance,
    }) for w in source.load_reconciliation.weeks)
    return source.model_copy(update={'load_reconciliation': source.load_reconciliation.model_copy(update={'weeks': weeks})})


def test_verified_future_server_policy_guard_preserves_atomic_rollback(monkeypatch):
    a = guarded_artifact('20')
    engine, preview_id, athlete_id, user_id, _ = seeded(a)
    with Session(engine) as session:
        row = session.get(TrainingPlanPreview, preview_id)
        payload = dict(row.artifact)
        payload.pop('load_reconciliation')  # Client/stored metadata cannot bypass guard.
        row.artifact = payload
        session.commit()
        before = row.artifact
        app = PlanningPreviewApplication(session)
        # First verify real reconstruction: current estimates cannot block.
        assert not app.artifact(row).load_reconciliation.acceptance_blocked
        verified = app.artifact
        monkeypatch.setattr(app, 'artifact', lambda r: calibrated_policy_test_double(verified(r)))
        assert app.artifact(row).load_reconciliation.acceptance_blocked
        assert row.artifact == before  # Read-only reconstruction.
        with pytest.raises(PlanningPreviewLoadNotReconciledError) as exc:
            app.accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role='athlete')
        assert exc.value.blocked_weeks == (str(a.session_plan.weeks[0].week_start),)
        assert session.get(TrainingPlanPreview, preview_id).status == 'pending'
        for model in (TrainingPlan, PlannedTrainingSession, StructuredWorkout):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_reconciled_acceptance_preserves_snapshot_and_idempotence():
    engine, preview_id, athlete_id, user_id, source = seeded(guarded_artifact('26'))
    with Session(engine) as session:
        app = PlanningPreviewApplication(session)
        accepted = app.accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role='athlete')
        assert app.accept(preview_id=preview_id, athlete_id=athlete_id, user_id=user_id, role='athlete').id == accepted.id
        assert app.artifact(session.get(TrainingPlanPreview, preview_id)).fingerprint == source.fingerprint


def test_guard_maps_to_explicit_http_conflict():
    from fastapi import HTTPException
    from app.api.v1.routes.planning_previews import _raise
    with pytest.raises(HTTPException) as exc:
        _raise(PlanningPreviewLoadNotReconciledError(guarded_artifact('20').load_reconciliation))
    assert exc.value.status_code == 409
    assert exc.value.detail['code'] == 'planning_preview_load_not_reconciled'


def test_api_enforces_independent_future_server_guard_and_get_is_read_only(monkeypatch):
    from tests.test_planning_preview_api import client_fixture
    client, session, preview_id, _ = client_fixture()
    try:
        verified = PlanningPreviewApplication.artifact
        monkeypatch.setattr(PlanningPreviewApplication, 'artifact', lambda self, row: calibrated_policy_test_double(verified(self, row)))
        source = guarded_artifact('20')
        row = session.get(TrainingPlanPreview, preview_id)
        # Keep the fixture's ownership/goals and replace its prescription.
        row.artifact = source.model_dump(mode='json', exclude_none=True)
        row.artifact_fingerprint = source.fingerprint
        session.commit()
        before = row.artifact
        response = client.get(f'/planning/previews/{preview_id}')
        assert response.status_code == 200
        assert response.json()['artifact']['load_reconciliation']['weeks'][0]['acceptance_blocked']
        assert row.artifact == before
        response = client.post(f'/planning/previews/{preview_id}/accept', json={'expected_fingerprint': source.fingerprint})
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'planning_preview_load_not_reconciled'
        assert session.scalar(select(func.count()).select_from(TrainingPlan)) == 0
        assert session.get(TrainingPlanPreview, preview_id).status == 'pending'
    finally:
        session.close()
