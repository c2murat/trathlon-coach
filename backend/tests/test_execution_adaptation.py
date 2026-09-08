from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.execution_adaptation import ExecutionAdaptationContextAssembler
from app.db.base import Base
from app.db.models import AthleteProfile, CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession
from app.domains.planning.contracts import PlanningContext, context_fingerprint
from app.domains.planning.execution_adaptation import (
    AdaptationReasonCode, AdaptationSignalConfidence, AdaptationSignalKind,
    EXECUTION_ADAPTATION_VERSION, build_execution_adaptation_context,
)
from app.domains.planning.execution_evidence import (
    ComparisonConfidence, CompletionStatus, ExecutionHistorySummary,
    PrescribedCompletedEvidenceContext, SessionExecutionEvidence,
    TargetAdherenceEvidence, TargetExecutionRelation,
)


AS_OF = date(2026, 9, 7)
ATHLETE_ID = UUID("00000000-0000-0000-0000-000000000001")


def session(index, *, days=7, sport="running", session_type="RUN_INTERVAL", relation=TargetExecutionRelation.WITHIN_TARGET, confidence=ComparisonConfidence.HIGH, target=True, partial=False, actual=None):
    unit = "watts" if sport == "cycling" else "seconds_per_100m" if sport == "swimming" else "seconds_per_km"
    low, high = (164, 185) if unit == "watts" else (107, 113) if unit == "seconds_per_100m" else (215, 229)
    representative = Decimal(str(actual if actual is not None else (low + high) / 2))
    target_evidence = None if not target else TargetAdherenceEvidence(
        planned_target_min=Decimal(low), planned_target_max=Decimal(high), unit=unit,
        planned_repetitions=5, matched_repetitions=3 if partial else 5,
        actual_representative_value=representative, target_hit_fraction=Decimal("1") if relation == TargetExecutionRelation.WITHIN_TARGET else Decimal("0"),
        work_duration_similarity=Decimal("0.98"), recovery_similarity=Decimal("1"),
        execution_relation=relation, confidence=confidence,
    )
    return SessionExecutionEvidence(
        planned_session_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
        planned_date=AS_OF - timedelta(days=days), sport=sport, session_type=session_type,
        planned_duration_seconds=3600, link_count=1, completed_activity_count=1,
        sport_match=True, actual_duration_seconds=1800 if partial else 3540,
        duration_ratio=Decimal("0.50") if partial else Decimal("0.98"),
        completion_status=CompletionStatus.PARTIAL if partial else CompletionStatus.COMPLETED,
        comparison_confidence=confidence, target_comparison=target_evidence,
    )


def unmatched(index, *, sport="running", session_type="RUN_INTERVAL", days=10):
    return SessionExecutionEvidence(
        planned_session_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
        planned_date=AS_OF - timedelta(days=days), sport=sport, session_type=session_type,
        planned_duration_seconds=3600, link_count=0, completed_activity_count=0,
        completion_status=CompletionStatus.UNMATCHED,
        comparison_confidence=ComparisonConfidence.INSUFFICIENT,
    )


def context(rows=()):
    return PrescribedCompletedEvidenceContext(
        athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF,
        window_start_date=AS_OF - timedelta(days=84), sessions=tuple(rows),
        summary=ExecutionHistorySummary(),
    )


def only_signal(rows, collection="session_type_signals"):
    result = build_execution_adaptation_context(context(rows))
    return result, getattr(result, collection)[0]


def test_empty_and_single_session_are_first_class_insufficient_results():
    empty = build_execution_adaptation_context(context())
    assert empty.algorithm_version == EXECUTION_ADAPTATION_VERSION
    assert empty.global_summary.session_count == 0 and empty.sport_signals == ()
    assert empty.global_signal.signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE
    assert empty.global_signal.reason_codes == (AdaptationReasonCode.NO_EVIDENCE,)
    _, signal = only_signal((session(1),))
    assert signal.signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE
    assert signal.confidence == AdaptationSignalConfidence.INSUFFICIENT
    assert AdaptationReasonCode.BELOW_MINIMUM_EVALUABLE_SESSIONS in signal.reason_codes


def test_unknown_and_unmatched_majorities_never_become_negative_adaptation():
    unknown_rows = (session(1, target=False), session(2, target=False), session(3))
    _, unknown_signal = only_signal(unknown_rows)
    assert unknown_signal.signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE
    assert AdaptationReasonCode.UNKNOWN_MAJORITY in unknown_signal.reason_codes
    rows = tuple(session(index) for index in range(1, 4)) + tuple(unmatched(index) for index in range(4, 8))
    _, unmatched_signal = only_signal(rows)
    assert unmatched_signal.signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE
    assert AdaptationReasonCode.UNMATCHED_MAJORITY in unmatched_signal.reason_codes


def test_repeated_within_target_produces_maintain_not_progression():
    rows = tuple(session(index, days=index * 4) for index in range(1, 5))
    result, signal = only_signal(rows)
    assert signal.signal == AdaptationSignalKind.MAINTAIN
    assert signal.supporting_metrics.within_target == 4
    assert result.structured_target_signals[0].signal == AdaptationSignalKind.MAINTAIN


@pytest.mark.parametrize(("sport", "relation", "actual"), [
    ("running", TargetExecutionRelation.FASTER_THAN_TARGET, 210),
    ("swimming", TargetExecutionRelation.FASTER_THAN_TARGET, 104),
    ("cycling", TargetExecutionRelation.ABOVE_POWER_TARGET, 190),
])
def test_repeated_moderate_faster_or_above_execution_is_progression_candidate(sport, relation, actual):
    rows = tuple(session(index, days=index * 5, sport=sport, session_type=f"{sport.upper()}_INTERVAL", relation=relation, actual=actual) for index in range(1, 4))
    _, signal = only_signal(rows)
    assert signal.signal == AdaptationSignalKind.PROGRESSION_CANDIDATE
    assert AdaptationReasonCode.REPEATED_ABOVE_OR_FASTER in signal.reason_codes


def test_extreme_overshoot_is_inconsistent_not_automatically_progression():
    rows = tuple(session(index, days=index * 4, sport="cycling", session_type="BIKE_INTERVAL", relation=TargetExecutionRelation.ABOVE_POWER_TARGET, actual=220) for index in range(1, 4))
    _, signal = only_signal(rows)
    assert signal.signal == AdaptationSignalKind.INCONSISTENT_EXECUTION
    assert AdaptationReasonCode.EXTREME_OVERSHOOT_PRESENT in signal.reason_codes


def test_recent_partial_execution_blocks_progression_even_at_allowed_global_fraction():
    rows = tuple(
        session(index, days=index * 4, relation=TargetExecutionRelation.FASTER_THAN_TARGET, actual=210, partial=index == 1)
        for index in range(1, 6)
    )
    _, signal = only_signal(rows)
    assert signal.supporting_metrics.recent_partial == 1
    assert signal.signal == AdaptationSignalKind.MAINTAIN


def test_repeated_slow_or_below_and_partial_execution_is_regression_candidate():
    rows = tuple(session(index, days=index * 5, relation=TargetExecutionRelation.SLOWER_THAN_TARGET, partial=True, actual=245) for index in range(1, 4))
    _, signal = only_signal(rows)
    assert signal.signal == AdaptationSignalKind.REGRESSION_CANDIDATE
    assert AdaptationReasonCode.REPEATED_BELOW_OR_SLOWER in signal.reason_codes
    assert AdaptationReasonCode.REPEATED_PARTIAL_EXECUTION in signal.reason_codes


def test_contradictory_target_directions_are_inconsistent():
    rows = (
        session(1, days=5, relation=TargetExecutionRelation.FASTER_THAN_TARGET, actual=210),
        session(2, days=10, relation=TargetExecutionRelation.SLOWER_THAN_TARGET, actual=245),
        session(3, days=15),
    )
    _, signal = only_signal(rows)
    assert signal.signal == AdaptationSignalKind.INCONSISTENT_EXECUTION
    assert AdaptationReasonCode.CONTRADICTORY_TARGET_DIRECTIONS in signal.reason_codes


def test_recent_four_weeks_are_explicit_and_background_cannot_replace_recent_minimum():
    sparse_recent = (session(1, days=7), session(2, days=35), session(3, days=70))
    _, signal = only_signal(sparse_recent)
    assert signal.signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE
    assert AdaptationReasonCode.BELOW_MINIMUM_RECENT_EVIDENCE in signal.reason_codes
    enough_recent = sparse_recent + (session(4, days=14),)
    _, signal = only_signal(enough_recent)
    assert signal.signal == AdaptationSignalKind.MAINTAIN
    assert signal.supporting_metrics.recent_structured_comparisons == 2
    assert signal.supporting_metrics.background_structured_comparisons == 2


def test_strength_never_infers_load_progression_from_duration():
    rows = tuple(session(index, days=index * 5, sport="strength", session_type="STRENGTH_A", target=False) for index in range(1, 5))
    _, signal = only_signal(rows)
    assert signal.signal == AdaptationSignalKind.INSUFFICIENT_EVIDENCE
    assert signal.reason_codes == (AdaptationReasonCode.STRENGTH_INTENSITY_NOT_OBSERVED,)


def test_context_is_deterministic_immutable_and_separates_sports_session_types_and_targets():
    rows = (
        session(1, sport="running", session_type="RUN_INTERVAL"),
        session(2, sport="running", session_type="RUN_THRESHOLD"),
        session(3, sport="cycling", session_type="BIKE_INTERVAL"),
    )
    first = build_execution_adaptation_context(context(rows))
    second = build_execution_adaptation_context(context(reversed(rows)))
    assert first.model_dump_json() == second.model_dump_json()
    assert len(first.sport_signals) == 2 and len(first.session_type_signals) == 3 and len(first.structured_target_signals) == 3
    with pytest.raises(ValidationError):
        first.algorithm_version = "changed"


def test_application_reuses_c1_context_in_memory_and_preserves_athlete_scope():
    class NoDatabase:
        pass

    service = ExecutionAdaptationContextAssembler(NoDatabase())
    expected = context((session(1), session(2), session(3)))
    calls = []
    service.evidence.assemble = lambda **kwargs: calls.append(kwargs) or expected
    result = service.assemble(athlete_profile_id=ATHLETE_ID, as_of_date=AS_OF)
    assert calls == [{"athlete_profile_id": ATHLETE_ID, "as_of_date": AS_OF}]
    assert result.athlete_profile_id == ATHLETE_ID
    assert all(identifier.int in {1, 2, 3} for signal in result.session_type_signals for identifier in signal.supporting_session_ids)


def test_real_assembler_adds_no_queries_and_cross_athlete_rows_cannot_influence_c2():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = Session(engine)
    try:
        athlete_a = AthleteProfile(display_name="A", timezone="UTC", unit_system="metric")
        athlete_b = AthleteProfile(display_name="B", timezone="UTC", unit_system="metric")
        db.add_all((athlete_a, athlete_b)); db.flush()
        for athlete, count in ((athlete_a, 3), (athlete_b, 4)):
            for index in range(count):
                planned = PlannedTrainingSession(
                    athlete_profile_id=athlete.id, scheduled_date=AS_OF - timedelta(days=index + 1),
                    timezone="UTC", sport="running", title="RUN_EASY",
                    planned_duration_seconds=3600, status="planned", origin="ai",
                )
                db.add(planned); db.flush()
                activities = []
                for split, duration in enumerate((1800, 1740) if index == 0 else (3540,)):
                    activity = CompletedActivity(
                        athlete_id=athlete.id, source_summary="manual", sport="running", name="Anonymous",
                        start_at=datetime.combine(planned.scheduled_date, time.min, timezone.utc),
                        timezone="UTC", elapsed_time_s=duration, moving_time_s=duration,
                    )
                    db.add(activity); db.flush(); activities.append(activity)
                    db.add(PlannedSessionActivityLink(
                        athlete_profile_id=athlete.id, planned_training_session_id=planned.id,
                        completed_activity_id=activity.id, match_source="manual", match_confidence="high",
                    ))
        db.flush()
        statements = []
        @event.listens_for(engine, "before_cursor_execute")
        def count_queries(*args): statements.append(args[2])
        result = ExecutionAdaptationContextAssembler(db).assemble(athlete_profile_id=athlete_a.id, as_of_date=AS_OF)
        event.remove(engine, "before_cursor_execute", count_queries)
        assert len(statements) == 3
        assert result.global_summary.session_count == 3
        assert result.global_summary.duration_completed == 3
        assert result.session_type_signals[0].signal == AdaptationSignalKind.MAINTAIN
        assert all(signal.supporting_metrics.session_count <= 3 for signal in result.sport_signals + result.session_type_signals)
    finally:
        db.close(); engine.dispose()


def test_interpretation_does_not_enter_or_change_planning_fingerprint():
    planning_input = {"athlete_id": str(ATHLETE_ID), "algorithm_version": "0.8F.9", "sessions": ("RUN_EASY",)}
    before = context_fingerprint(planning_input)
    build_execution_adaptation_context(context((session(1), session(2), session(3))))
    assert context_fingerprint(planning_input) == before
    assert "execution_adaptation" not in PlanningContext.model_fields
