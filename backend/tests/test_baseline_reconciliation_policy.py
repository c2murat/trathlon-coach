"""Acceptance policy over estimates, not changes to prescribed workouts."""
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.application.planning_preview import PlanningPreviewApplication
from app.db.models import TrainingPlanPreview
from app.domains.planning.contracts import context_fingerprint
from app.domains.planning.prescribed_load import reconciliation_state
from app.domains.planning.preview import build_preview_artifact, preview_artifact_payload
from tests.test_load_reconciliation_guard import guarded_artifact
from tests.test_planning_preview_application import seeded


@pytest.mark.parametrize('quality,coverage,within,expected', [
    ('LOW','COMPLETE',False,'REVIEW_REQUIRED'),
    ('LOW','COMPLETE',True,'RECONCILED'),
    ('MEDIUM','COMPLETE',False,'REVIEW_REQUIRED'),
    ('HIGH','COMPLETE',False,'REVIEW_REQUIRED'),
    ('MEDIUM','COMPLETE',True,'RECONCILED'),
    ('LOW','PARTIAL',False,'INSUFFICIENT_QUALITY'),
    ('MEDIUM','PARTIAL',False,'INSUFFICIENT_QUALITY'),
    ('UNAVAILABLE','UNAVAILABLE',None,'INSUFFICIENT_QUALITY'),
    ('MEDIUM','COMPLETE',None,'INSUFFICIENT_QUALITY'),
])
def test_quality_coverage_and_variance_have_separate_semantics(quality, coverage, within, expected):
    assert reconciliation_state(within_tolerance=within, coverage=coverage, quality=quality, session_count=1) == expected


@pytest.mark.parametrize('quality,expected', [('LOW','REVIEW_REQUIRED'), ('MEDIUM','NOT_RECONCILED'), ('HIGH','NOT_RECONCILED')])
def test_hard_block_requires_separate_confidence_and_never_low(quality, expected):
    assert reconciliation_state(within_tolerance=False, coverage='COMPLETE', quality=quality, session_count=1, blocking_confidence=True) == expected


def low_quality_artifact():
    a = guarded_artifact('20')
    draft = a.sessions[0].workout
    definition = draft.definition.model_copy(deep=True)
    # Keep the calculator inputs/value, but time is estimated from a prescribed
    # distance. This genuinely triggers LOW in the estimator; do not spoof it.
    from app.domains.planning.models import WorkoutDuration
    definition.steps[0].duration = WorkoutDuration(mode='distance', meters=10000, estimated_seconds=3600)
    return build_preview_artifact(athlete_id=a.athlete_id, timezone_name=a.timezone_name,
        context_fingerprint_value=a.context_fingerprint, season=a.season_structure,
        budgets=a.weekly_budget_plan, session_plan=a.session_plan, goals=a.goals,
        workout_drafts=(draft.model_copy(update={'definition': definition}),),
        algorithm_version=a.algorithm_version, configuration_version=a.configuration_version)


def test_low_quality_excess_is_visible_but_http_acceptance_preserves_snapshot():
    from tests.test_planning_preview_api import client_fixture
    a = low_quality_artifact()
    week = a.load_reconciliation.weeks[0]
    assert week.variance_percent == 30
    assert week.coverage == 'COMPLETE' and week.quality == 'LOW'
    assert week.status == 'OUTSIDE_TOLERANCE'
    assert week.reconciliation_state == 'REVIEW_REQUIRED'
    assert week.quality_warning and not week.acceptance_blocked
    client, db, preview_id, _ = client_fixture()
    try:
        row = db.get(TrainingPlanPreview, preview_id)
        row.artifact = a.model_dump(mode='json', exclude_none=True)
        row.artifact_fingerprint = a.fingerprint
        db.commit()
        response = client.get(f'/planning/previews/{preview_id}')
        assert response.status_code == 200
        assert response.json()['artifact']['load_reconciliation']['weeks'][0]['reconciliation_state'] == 'REVIEW_REQUIRED'
        accepted = client.post(f'/planning/previews/{preview_id}/accept', json={'expected_fingerprint': a.fingerprint})
        assert accepted.status_code == 200
        assert PlanningPreviewApplication(db).artifact(row).fingerprint == a.fingerprint
    finally:
        db.close()


def test_diagnostic_policy_change_does_not_change_fingerprint():
    a = low_quality_artifact()
    changed = a.model_copy(update={'load_reconciliation': None})
    assert context_fingerprint(preview_artifact_payload(a)) == context_fingerprint(preview_artifact_payload(changed))
    engine, preview_id, _, _, _ = seeded(a)
    with Session(engine) as db:
        app = PlanningPreviewApplication(db)
        row = db.get(TrainingPlanPreview, preview_id)
        assert app.artifact(row) == app.artifact(row)
        assert app.artifact(row).fingerprint == a.fingerprint


def test_synthetic_policy_matrix_is_not_blocked_by_low_quality():
    reference = json.loads((Path(__file__).parent/'fixtures'/'baseline_reconciliation_reference.json').read_text(encoding='utf-8'))
    rows = reference['weeks']
    assert len(rows) == 50
    assert sum(w['baseline_outside'] for w in rows) == 19
    assert sum(w['e1_outside'] for w in rows) == 16
    assert sum(w['e1_outside'] and not w['baseline_outside'] for w in rows) == 0
    for w in rows:
        for label in ('baseline', 'e1_target5'):
            d = w[label]
            state = reconciliation_state(within_tolerance=d['within_tolerance'], coverage=d['coverage'], quality=d['quality'], session_count=d['sessions'])
            assert state != 'NOT_RECONCILED'
            if d['within_tolerance'] is False and d['coverage'] == 'COMPLETE':
                assert state == 'REVIEW_REQUIRED'
