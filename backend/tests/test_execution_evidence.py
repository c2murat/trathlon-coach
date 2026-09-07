from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.db.base import Base
from app.db.models import ActivityLap, AthleteProfile, CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession, StructuredWorkout
from app.domains.capability.analysis import LapEvidence
from app.domains.planning.execution_evidence import (
    ComparisonConfidence, CompletionStatus, EXECUTION_EVIDENCE_VERSION,
    LinkedActivityEvidence, PlannedSessionEvidence, TargetExecutionRelation,
    build_session_execution_evidence, build_summary,
)
from app.domains.planning.models import StructuredWorkoutDefinition


AS_OF = date(2026, 9, 7)
SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close(); engine.dispose()


def workout(sport="running", *, reps=8, work_seconds=120, work_meters=None, recovery_seconds=60, low=215, high=229, unit="seconds_per_km"):
    duration = {"mode": "distance", "meters": work_meters} if work_meters else {"mode": "time", "seconds": work_seconds}
    metric = "power" if unit == "watts" else "swim_pace" if unit == "seconds_per_100m" else "pace"
    reference = "FTP" if unit == "watts" else "CSS" if unit == "seconds_per_100m" else "threshold_pace"
    return StructuredWorkoutDefinition.model_validate({
        "schema_version": 1, "sport": sport, "steps": [{
            "kind": "repeat", "repetitions": reps, "steps": [
                {"kind": "step", "phase": "work", "duration": duration, "target": {
                    "metric": metric, "mode": "percent_reference", "reference": reference,
                    "minimum": .8, "maximum": 1.2, "reference_value": low,
                    "reference_unit": unit, "resolved_minimum": low,
                    "resolved_maximum": high, "resolved_unit": unit,
                }},
                {"kind": "step", "phase": "recovery", "duration": {"mode": "time", "seconds": recovery_seconds}, "target": {"metric": "none", "mode": "none"}},
            ],
        }],
    })


def lap(activity_id, sport, index, seconds, *, distance=None, power=None, elapsed=None, moving=None):
    return LapEvidence(
        activity_id=activity_id, sport=sport, local_date=AS_OF - timedelta(days=1), lap_index=index,
        duration_seconds=seconds, distance_m=Decimal(str(distance)) if distance else None,
        average_speed_mps=None, average_power_w=Decimal(str(power)) if power else None,
        elapsed_seconds=elapsed if elapsed is not None else seconds,
        moving_seconds=moving if moving is not None else seconds,
    )


def linked(sport="running", duration=2640, *, activity_id=None, laps=(), distance=None, source="manual"):
    return LinkedActivityEvidence(
        activity_id=activity_id or uuid4(), sport=sport, duration_seconds=duration,
        distance_m=Decimal(str(distance)) if distance else None, match_source=source,
        match_confidence="high", matching_algorithm_version=None if source == "manual" else "0.8G.1",
        laps=tuple(laps),
    )


def planned(*, sport="running", duration=2700, distance=None, activities=(), definition=None):
    return PlannedSessionEvidence(
        session_id=SESSION_ID, planned_date=AS_OF - timedelta(days=1), sport=sport,
        session_type="RUN_INTERVAL" if sport == "running" else "BIKE_INTERVAL" if sport == "cycling" else "SWIM_THRESHOLD",
        planned_duration_seconds=duration,
        planned_distance_m=Decimal(str(distance)) if distance else None,
        workout=definition, linked_activities=tuple(activities),
    )


def alternating(activity_id, sport, values, *, work_seconds=120, work_distance=None, recovery_seconds=60, anomaly=False):
    rows = []
    for index, value in enumerate(values):
        distance = work_distance
        seconds = work_seconds
        power = value if sport == "cycling" else None
        if sport in {"running", "swimming"}:
            scale = 1000 if sport == "running" else 100
            distance = work_distance or (Decimal(seconds) * Decimal(scale) / Decimal(str(value)))
        rows.append(lap(activity_id, sport, index * 2 + 1, seconds, distance=distance, power=power,
                        elapsed=300 if anomaly and index == len(values) - 1 else seconds,
                        moving=seconds))
        rows.append(lap(activity_id, sport, index * 2 + 2, recovery_seconds, distance=100 if sport != "cycling" else None, power=80 if sport == "cycling" else None))
    return tuple(rows)


def test_duration_bands_distance_and_simple_completed_without_invented_target():
    activity = linked(duration=2640, distance=9900)
    result = build_session_execution_evidence(planned(duration=2700, distance=10000, activities=(activity,)))
    assert result.duration_ratio == Decimal("0.98")
    assert result.distance_ratio == Decimal("0.99")
    assert result.completion_status == CompletionStatus.COMPLETED
    assert result.target_comparison is None
    assert result.algorithm_version == EXECUTION_EVIDENCE_VERSION
    assert build_session_execution_evidence(planned(duration=3600, activities=(linked(duration=2879),))).completion_status == CompletionStatus.PARTIAL
    assert build_session_execution_evidence(planned(duration=3600, activities=(linked(duration=2880),))).completion_status == CompletionStatus.COMPLETED
    assert build_session_execution_evidence(planned(duration=3600, activities=(linked(duration=4320),))).completion_status == CompletionStatus.COMPLETED
    assert build_session_execution_evidence(planned(duration=3600, activities=(linked(duration=4321),))).completion_status == CompletionStatus.OVER_DURATION
    zero = build_session_execution_evidence(planned(duration=None, activities=(linked(duration=100),)))
    assert zero.duration_ratio is None and zero.completion_status == CompletionStatus.UNKNOWN


def test_multi_activity_aggregation_deduplicates_and_preserves_manual_provenance():
    first = linked("cycling", 3000, distance=20000)
    second = linked("cycling", 2280, distance=15000)
    result = build_session_execution_evidence(planned(sport="cycling", duration=5400, distance=36000, activities=(second, first, first)))
    assert result.link_count == 2 and result.completed_activity_count == 2
    assert result.actual_duration_seconds == 5280 and result.duration_ratio == Decimal("0.98")
    assert result.actual_distance_m == Decimal("35000.00")
    assert all(item.match_source == "manual" for item in result.link_provenance)


def test_unmatched_is_not_failure_and_sport_mismatch_is_low_confidence():
    unmatched = build_session_execution_evidence(planned())
    assert unmatched.completion_status == CompletionStatus.UNMATCHED
    assert unmatched.comparison_confidence == ComparisonConfidence.INSUFFICIENT
    mismatch = build_session_execution_evidence(planned(activities=(linked("cycling"),), definition=workout()))
    assert mismatch.sport_match is False and mismatch.completion_status == CompletionStatus.UNKNOWN
    assert mismatch.comparison_confidence == ComparisonConfidence.LOW
    assert mismatch.target_comparison is None


def test_strength_compares_only_link_and_duration_and_low_match_confidence_is_preserved():
    strength = build_session_execution_evidence(planned(
        sport="strength", duration=2400,
        activities=(linked("strength", duration=2350, source="automatic").model_copy(update={"match_confidence": "low"}),),
    ))
    assert strength.completion_status == CompletionStatus.COMPLETED
    assert strength.comparison_confidence == ComparisonConfidence.LOW
    assert strength.target_comparison is None


@pytest.mark.parametrize(("pace", "relation"), [
    (200, TargetExecutionRelation.FASTER_THAN_TARGET),
    (245, TargetExecutionRelation.SLOWER_THAN_TARGET),
])
def test_running_repeat_alignment_and_pace_direction(pace, relation):
    activity_id = uuid4()
    rows = alternating(activity_id, "running", [pace] * 8)
    result = build_session_execution_evidence(planned(activities=(linked(activity_id=activity_id, laps=rows),), definition=workout()))
    assert result.target_comparison.matched_repetitions == 8
    assert result.target_comparison.actual_representative_value == Decimal(str(pace) + ".00")
    assert result.target_comparison.execution_relation == relation
    assert result.target_comparison.confidence == ComparisonConfidence.HIGH


def test_running_within_target_and_incomplete_repetitions_are_distinct_from_duration_completion():
    activity_id = uuid4()
    complete = build_session_execution_evidence(planned(activities=(linked(activity_id=activity_id, laps=alternating(activity_id, "running", [220] * 8)),), definition=workout()))
    assert complete.target_comparison.execution_relation == TargetExecutionRelation.WITHIN_TARGET
    assert complete.target_comparison.target_hit_fraction == Decimal("1.00")
    partial_id = uuid4()
    partial = build_session_execution_evidence(planned(activities=(linked(activity_id=partial_id, laps=alternating(partial_id, "running", [220] * 5)),), definition=workout()))
    assert partial.completion_status == CompletionStatus.COMPLETED
    assert partial.target_comparison.matched_repetitions == 5
    assert partial.target_comparison.confidence == ComparisonConfidence.MEDIUM
    assert build_summary((partial,)).groups[0].partial_count == 1


def test_bike_uses_work_lap_power_not_global_activity_average():
    activity_id = uuid4()
    definition = workout("cycling", reps=5, work_seconds=180, low=164, high=185, unit="watts")
    rows = alternating(activity_id, "cycling", [175] * 5, work_seconds=180)
    result = build_session_execution_evidence(planned(sport="cycling", activities=(linked("cycling", activity_id=activity_id, laps=rows),), definition=definition))
    assert result.target_comparison.actual_representative_value == Decimal("175.00")
    assert result.target_comparison.execution_relation == TargetExecutionRelation.WITHIN_TARGET


def test_swim_uses_reliable_laps_and_ignores_anomalous_lap():
    activity_id = uuid4()
    definition = workout("swimming", reps=5, work_meters=300, low=107, high=113, unit="seconds_per_100m")
    rows = alternating(activity_id, "swimming", [110] * 5, work_seconds=330, work_distance=300)
    anomalous = lap(activity_id, "swimming", 99, 270, distance=300, elapsed=500, moving=270)
    result = build_session_execution_evidence(planned(sport="swimming", activities=(linked("swimming", activity_id=activity_id, laps=rows + (anomalous,)),), definition=definition))
    assert result.target_comparison.matched_repetitions == 5
    assert result.target_comparison.execution_relation == TargetExecutionRelation.WITHIN_TARGET


def test_interval_without_laps_has_duration_evidence_but_unknown_target():
    result = build_session_execution_evidence(planned(activities=(linked(),), definition=workout()))
    assert result.duration_ratio is not None and result.target_comparison is None


def add_session(db, athlete, *, day, sport="running", duration=2700, with_activity=True, definition=None):
    row = PlannedTrainingSession(
        athlete_profile_id=athlete.id, scheduled_date=day, timezone="UTC", sport=sport,
        title="RUN_INTERVAL", planned_duration_seconds=duration, status="planned", origin="ai",
    )
    db.add(row); db.flush()
    if definition:
        db.add(StructuredWorkout(planned_training_session_id=row.id, schema_version=1, definition=definition.model_dump(mode="json", exclude_none=True)))
    if with_activity:
        activity = CompletedActivity(
            athlete_id=athlete.id, source_summary="manual", sport=sport, name="Anonymous",
            start_at=datetime.combine(day, datetime.min.time(), timezone.utc), timezone="UTC",
            elapsed_time_s=duration, moving_time_s=duration, distance_m=10000,
        )
        db.add(activity); db.flush()
        db.add(PlannedSessionActivityLink(
            athlete_profile_id=athlete.id, planned_training_session_id=row.id,
            completed_activity_id=activity.id, match_source="manual", match_confidence="high",
        ))
    db.flush()
    return row


def test_assembler_excludes_future_and_other_athletes_is_deterministic_and_three_queries(db):
    athlete_a = AthleteProfile(display_name="A", timezone="UTC", unit_system="metric")
    athlete_b = AthleteProfile(display_name="B", timezone="UTC", unit_system="metric")
    db.add_all((athlete_a, athlete_b)); db.flush()
    add_session(db, athlete_a, day=AS_OF - timedelta(days=1))
    add_session(db, athlete_a, day=AS_OF + timedelta(days=1))
    add_session(db, athlete_b, day=AS_OF - timedelta(days=1))
    statements = []
    @event.listens_for(db.bind, "before_cursor_execute")
    def count_queries(*args): statements.append(args[2])
    first = PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=athlete_a.id, as_of_date=AS_OF)
    assert len(statements) == 3
    event.remove(db.bind, "before_cursor_execute", count_queries)
    second = PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=athlete_a.id, as_of_date=AS_OF)
    assert first.model_dump_json() == second.model_dump_json()
    assert len(first.sessions) == 1 and first.sessions[0].sport_match is True
    assert first.summary.groups[0].matched_count == 1


def test_assembler_keeps_past_unmatched_as_no_evidence(db):
    athlete = AthleteProfile(display_name="A", timezone="UTC", unit_system="metric")
    db.add(athlete); db.flush()
    add_session(db, athlete, day=AS_OF - timedelta(days=2), with_activity=False)
    context = PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=athlete.id, as_of_date=AS_OF)
    assert context.sessions[0].completion_status == CompletionStatus.UNMATCHED
    assert context.summary.groups[0].unmatched_past_count == 1


def test_context_is_immutable_serializable_and_not_part_of_planning_fingerprint_contract(db):
    from pydantic import ValidationError
    from app.domains.planning.contracts import PlanningContext

    athlete = AthleteProfile(display_name="A", timezone="UTC", unit_system="metric")
    db.add(athlete); db.flush()
    context = PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=athlete.id, as_of_date=AS_OF)
    assert '"algorithm_version":"0.8G.2C.1"' in context.model_dump_json()
    with pytest.raises(ValidationError):
        context.algorithm_version = "changed"
    assert "execution_evidence" not in PlanningContext.model_fields
