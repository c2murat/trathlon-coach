from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.quality_exposure import QualityExposureAssembler
from app.db.base import Base
from app.db.models import (
    ActivityLap, ActivityTrainingLoad, AthleteProfile, CompletedActivity,
    PlannedSessionActivityLink, PlannedTrainingSession,
)
from app.domains.planning.quality_exposure import (
    QualityExposureEvidence, build_quality_exposure_snapshot, classify_structured_activity,
    classify_unlinked, recency_weight,
)
from app.domains.capability.analysis import LapEvidence
from app.domains.planning.contracts import PerformanceSnapshot


CUTOFF = date(2026, 9, 2)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine); session = Session(engine)
    yield session
    session.close(); engine.dispose()


def evidence(key, days, discipline="running", stimulus="INTERVAL", confidence="HIGH"):
    return QualityExposureEvidence(
        activity_id=key, local_date=CUTOFF - timedelta(days=days),
        discipline=discipline, stimulus=stimulus, confidence=confidence,
    )


def lap(sport, index, seconds, *, distance=None, power=None, elapsed=None, moving=None):
    return LapEvidence(
        activity_id="activity", sport=sport, local_date=CUTOFF, lap_index=index,
        duration_seconds=seconds, distance_m=Decimal(str(distance)) if distance else None,
        average_speed_mps=None, average_power_w=Decimal(str(power)) if power else None,
        elapsed_seconds=elapsed if elapsed is not None else seconds,
        moving_seconds=moving if moving is not None else seconds,
    )


def alternating(work):
    rows = []
    for index, item in enumerate(work):
        rows.extend((replace(item, lap_index=index * 2 + 1), lap(item.sport, index * 2 + 2, 60, distance=100 if item.sport != "cycling" else None, power=80 if item.sport == "cycling" else None)))
    return tuple(rows)


def test_structured_running_classifies_interval_threshold_and_tempo_without_hardcoded_distance():
    performance = PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250"))
    interval = alternating([lap("running", 0, 175, distance=760 + index * 3) for index in range(6)])
    assert classify_structured_activity(discipline="running", laps=interval, performance=performance).stimulus == "INTERVAL"
    threshold = alternating([lap("running", 0, 600, distance=2400 + index * 10) for index in range(3)])
    assert classify_structured_activity(discipline="running", laps=threshold, performance=performance).stimulus == "THRESHOLD"
    tempo = alternating([lap("running", 0, 720, distance=2600 + index * 10) for index in range(2)])
    assert classify_structured_activity(discipline="running", laps=tempo, performance=performance).stimulus == "TEMPO"


def test_continuous_fast_running_is_unknown_and_long_with_tempo_blocks_is_not_interval():
    performance = PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250"))
    continuous = tuple(lap("running", index, 230, distance=1000) for index in range(1, 7))
    assert classify_structured_activity(discipline="running", laps=continuous, performance=performance) is None
    sparse_without_recovery = tuple(lap("running", index, 240 if index in {1, 5} else 235, distance=1000) for index in range(1, 6))
    assert classify_structured_activity(discipline="running", laps=sparse_without_recovery, performance=performance) is None
    tempo = alternating([lap("running", 0, 900, distance=3300), lap("running", 0, 890, distance=3280)])
    result = classify_structured_activity(discipline="running", laps=tempo, performance=performance)
    assert result.stimulus == "TEMPO"


def test_structured_cycling_distinguishes_interval_threshold_and_sweet_spot():
    performance = PerformanceSnapshot(cycling_ftp_watts=Decimal("200"))
    interval = alternating([lap("cycling", 0, 180, power=245 + index) for index in range(5)])
    threshold = alternating([lap("cycling", 0, 900, power=198), lap("cycling", 0, 910, power=202)])
    sweet = alternating([lap("cycling", 0, 900, power=176), lap("cycling", 0, 910, power=178)])
    assert classify_structured_activity(discipline="cycling", laps=interval, performance=performance).stimulus == "INTERVAL"
    assert classify_structured_activity(discipline="cycling", laps=threshold, performance=performance).stimulus == "THRESHOLD"
    assert classify_structured_activity(discipline="cycling", laps=sweet, performance=performance).stimulus == "SWEET_SPOT"
    assert classify_structured_activity(discipline="cycling", laps=(lap("cycling", 1, 3600, power=230),), performance=performance) is None


def test_structured_swimming_filters_anomaly_and_never_infers_technique_from_pace():
    performance = PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110"))
    threshold = tuple(lap("swimming", index, 220, distance=200) for index in range(1, 5))
    aerobic = tuple(lap("swimming", index, 240, distance=200) for index in range(1, 5))
    anomalous = tuple(lap("swimming", index, 180, distance=200, elapsed=300, moving=180) for index in range(1, 5))
    assert classify_structured_activity(discipline="swimming", laps=threshold, performance=performance).stimulus == "THRESHOLD"
    assert classify_structured_activity(discipline="swimming", laps=aerobic, performance=performance).stimulus == "AEROBIC"
    assert classify_structured_activity(discipline="swimming", laps=anomalous, performance=performance) is None
    assert all(classify_structured_activity(discipline="swimming", laps=rows, performance=performance).stimulus != "TECHNIQUE" for rows in (threshold, aerobic))


def test_recency_bands_weight_recent_exposure_more_than_old_exposure():
    assert recency_weight(5) == Decimal("1.00")
    assert recency_weight(40) == Decimal("0.60")
    assert recency_weight(70) == Decimal("0.30")
    snapshot = build_quality_exposure_snapshot(
        cutoff_date=CUTOFF, evidence=(evidence("recent", 5), evidence("old", 70)),
    )
    signal = snapshot.signals[0]
    assert signal.weighted_exposure == Decimal("1.30")
    assert (signal.count_0_27d, signal.count_28_55d, signal.count_56_83d) == (1, 0, 1)
    assert signal.days_since_last == 5


def test_snapshot_is_compact_deterministic_and_keeps_classification_confidence():
    rows = (evidence("a", 8, stimulus="TEMPO", confidence="MEDIUM"), evidence("b", 4, stimulus="TEMPO"))
    first = build_quality_exposure_snapshot(cutoff_date=CUTOFF, evidence=rows)
    assert first == build_quality_exposure_snapshot(cutoff_date=CUTOFF, evidence=reversed(rows))
    assert first.algorithm_version == "0.8G.2B.3.2"
    assert first.signals[0].confidence == "HIGH"
    assert not hasattr(first.signals[0], "activity_ids")


def test_unlinked_classification_is_conservative_and_reference_relative():
    assert classify_unlinked(discipline="running", effective_intensity=1.08) == "INTERVAL"
    assert classify_unlinked(discipline="running", effective_intensity=.98) == "THRESHOLD"
    assert classify_unlinked(discipline="cycling", effective_intensity=.91) == "SWEET_SPOT"
    assert classify_unlinked(discipline="running", effective_intensity=.65) is None
    assert classify_unlinked(discipline="swimming", effective_intensity=1.2) is None
    assert classify_unlinked(discipline="running", effective_intensity=None) is None


def test_one_activity_contributes_at_most_once_to_snapshot():
    linked = evidence("same", 3, stimulus="THRESHOLD")
    snapshot = build_quality_exposure_snapshot(cutoff_date=CUTOFF, evidence=(linked,))
    assert snapshot.signals[0].count_0_27d == 1


def test_linked_session_has_precedence_over_unlinked_heuristic_without_n_plus_one(db):
    from datetime import datetime, timezone
    athlete = AthleteProfile(display_name="Synthetic", timezone="Europe/Madrid", unit_system="metric")
    db.add(athlete); db.flush()
    activity = CompletedActivity(
        athlete_id=athlete.id, source_summary="manual", sport="running", name="Synthetic quality",
        start_at=datetime(2026, 8, 30, 8, tzinfo=timezone.utc), timezone="Europe/Madrid",
        elapsed_time_s=2700, moving_time_s=2700, distance_m=8000,
    )
    planned = PlannedTrainingSession(
        athlete_profile_id=athlete.id, scheduled_date=date(2026, 8, 30), timezone="Europe/Madrid",
        sport="running", title="RUN_INTERVAL", planned_duration_seconds=2700,
        status="planned", origin="ai",
    )
    db.add_all((activity, planned)); db.flush()
    for index in range(6):
        db.add_all((
            ActivityLap(completed_activity_id=activity.id, provider_index=index * 2, lap_index=index * 2 + 1, elapsed_time_seconds=175, moving_time_seconds=175, distance_metres=800),
            ActivityLap(completed_activity_id=activity.id, provider_index=index * 2 + 1, lap_index=index * 2 + 2, elapsed_time_seconds=60, moving_time_seconds=60, distance_metres=100),
        ))
    db.add_all((
        PlannedSessionActivityLink(
            athlete_profile_id=athlete.id, planned_training_session_id=planned.id,
            completed_activity_id=activity.id, match_source="manual", match_confidence="high",
        ),
        ActivityTrainingLoad(
            completed_activity_id=activity.id, load_value=50, method="pace", unit="load_points",
            coverage="complete", quality="high", reason=None, algorithm_version="0.7b.1",
            duration_seconds=2700, effective_intensity=.82, reference_value=250,
            reference_metric="seconds_per_km", source_metrics={}, warnings=[],
            calculated_at=datetime(2026, 8, 30, 10, tzinfo=timezone.utc),
        ),
    )); db.flush()
    statements = []
    @event.listens_for(db.bind, "before_cursor_execute")
    def count_queries(*args): statements.append(args[2])
    snapshot = QualityExposureAssembler(db).assemble(
        athlete_profile_id=athlete.id, as_of_date=CUTOFF, timezone_name="Europe/Madrid",
        performance=PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("250")),
    )
    assert [(item.stimulus, item.confidence) for item in snapshot.signals] == [("INTERVAL", "HIGH")]
    assert len(statements) == 4
