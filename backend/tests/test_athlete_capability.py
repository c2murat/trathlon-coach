from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.application.athlete_capability import AthleteCapabilityContextAssembler
from app.db.base import Base
from app.db.models import ActivityLap, ActivityStream, AthletePerformanceProfileVersion, AthleteProfile, CompletedActivity
from app.domains.capability.analysis import ActivityEvidence, LapEvidence, build_capability_context, capability_window
from app.domains.capability.models import CapabilityConfidence
from app.domains.planning.contracts import PerformanceSnapshot
from tests.test_planning_context_assembler import assembler, make_request, seed_identity_goal


AS_OF = date(2026, 8, 31)


def activity(athlete_id, sport, days, minutes=60, distance=None, power=None):
    return ActivityEvidence(athlete_id, sport, AS_OF-timedelta(days=days), minutes*60, Decimal(str(distance)) if distance else None, average_power_w=Decimal(str(power)) if power else None)


def lap(athlete_id, sport, days, index, seconds, distance=None, power=None, *, elapsed=None, moving=None):
    return LapEvidence(
        athlete_id, sport, AS_OF-timedelta(days=days), index, seconds,
        Decimal(str(distance)) if distance else None, None,
        Decimal(str(power)) if power else None, Decimal("1"),
        elapsed if elapsed is not None else seconds,
        moving if moving is not None else seconds,
    )


def context(athlete_id, activities=(), laps=(), performance=None):
    return build_capability_context(athlete_id=athlete_id, as_of_date=AS_OF, activities=tuple(activities), laps=tuple(laps), performance=performance or PerformanceSnapshot())


def test_window_is_inclusive_deterministic_84_days_and_empty_history_is_valid():
    athlete = uuid4()
    assert capability_window(AS_OF) == (date(2026, 6, 9), AS_OF)
    first = context(athlete)
    second = context(athlete)
    assert first == second
    assert first.window_weeks == 12 and first.available_history_days == 0
    assert first.confidence is CapabilityConfidence.INSUFFICIENT
    assert first.activity_count == first.weeks_with_training == 0


def test_running_same_threshold_but_recent_repeat_capability_differs_and_best_is_not_representative():
    a, b = uuid4(), uuid4()
    performance = PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("260"))
    efforts = [lap(a, "running", 7, i, 180, distance) for i, distance in enumerate((850, 857, 862, 865))]
    efforts.append(lap(a, "running", 7, 9, 180, 1000))  # isolated fast value
    result_a = context(a, [activity(a, "running", 7)], efforts, performance)
    result_b = context(b, [activity(b, "running", 7)], (), performance)
    point = next(item for item in result_a.running.duration_efforts if item.duration_seconds == 180)
    assert point.best_value < point.representative_value
    assert Decimal("205") <= point.representative_value <= Decimal("213")
    assert point.representative_support_count == 5
    assert not result_b.running.duration_efforts


def test_cycling_same_ftp_distinguishes_representative_three_minute_power():
    a, b = uuid4(), uuid4(); performance = PerformanceSnapshot(cycling_ftp_watts=Decimal("140"))
    laps_a = [lap(a, "cycling", 5, i, 180, power=p) for i, p in enumerate((175, 178, 180, 176))]
    laps_b = [lap(b, "cycling", 5, i, 180, power=p) for i, p in enumerate((148, 150, 152, 150))]
    pa = next(item for item in context(a, [activity(a,"cycling",5,power=160)], laps_a, performance).cycling.duration_efforts if item.duration_seconds == 180)
    pb = next(item for item in context(b, [activity(b,"cycling",5,power=145)], laps_b, performance).cycling.duration_efforts if item.duration_seconds == 180)
    assert pa.representative_value > pb.representative_value
    assert Decimal("175") <= pa.representative_value <= Decimal("180")


def test_swimming_same_css_distinguishes_repeated_200m_evidence():
    a, b = uuid4(), uuid4(); performance = PerformanceSnapshot(swimming_css_seconds_per_100m=Decimal("110"))
    laps = [lap(a, "swimming", 4, i, seconds, 200) for i, seconds in enumerate((220, 222, 219, 221, 220, 223))]
    result_a = context(a, [activity(a,"swimming",4,45,2400)], laps, performance)
    result_b = context(b, [activity(b,"swimming",4,45,2400)], (), performance)
    assert next(item for item in result_a.swimming.distance_efforts if item.distance_m == 200).representative_support_count == 6
    assert result_a.swimming.repeat_like_efforts
    assert not result_b.swimming.distance_efforts


def test_recent_evidence_has_higher_confidence_than_same_old_evidence():
    recent, old = uuid4(), uuid4()
    recent_laps = [lap(recent,"cycling",7,i,180,power=175) for i in range(4)]
    old_laps = [lap(old,"cycling",77,i,180,power=175) for i in range(4)]
    rp = context(recent,[activity(recent,"cycling",7)],recent_laps).cycling.duration_efforts[0]
    op = context(old,[activity(old,"cycling",77)],old_laps).cycling.duration_efforts[0]
    assert rp.representative_confidence is CapabilityConfidence.HIGH
    assert op.representative_confidence is CapabilityConfidence.LOW
    assert rp.representative_days_since_evidence < op.representative_days_since_evidence


def test_representative_effort_weights_recent_evidence_more_than_old_best_values():
    athlete=uuid4()
    rows=(
        lap(athlete,"running",75,0,180,900), lap(athlete,"running",70,1,180,895),
        lap(athlete,"running",7,2,180,818), lap(athlete,"running",5,3,180,814),
    )
    point=next(item for item in context(athlete,[activity(athlete,"running",5)],rows).running.duration_efforts if item.duration_seconds==180)
    assert point.best_value < Decimal("205")
    assert Decimal("219") <= point.representative_value <= Decimal("222")


def test_repeat_clustering_finds_six_800s_among_warmup_recoveries_and_cooldown():
    athlete = uuid4()
    rows = [lap(athlete, "running", 7, 0, 900, 3000)]
    for index, seconds in enumerate((181, 177, 173, 175, 175, 175), start=1):
        rows.append(lap(athlete, "running", 7, index * 2 - 1, seconds, 800))
        rows.append(lap(athlete, "running", 7, index * 2, 60, 95 + index))
    rows.append(lap(athlete, "running", 7, 20, 600, 1800))
    repeats = context(athlete, [activity(athlete, "running", 7)], rows).running.repeat_like_efforts
    assert repeats[0].repeat_count == 6
    assert repeats[0].typical_distance_m == 800
    assert Decimal("216") <= repeats[0].representative_value <= Decimal("226")
    assert repeats[0].confidence is CapabilityConfidence.HIGH


def test_repeat_clustering_rejects_heterogeneous_efforts_without_three_peers():
    athlete = uuid4()
    rows = [
        lap(athlete, "running", 3, 0, 120, 400),
        lap(athlete, "running", 3, 1, 180, 800),
        lap(athlete, "running", 3, 2, 300, 1200),
        lap(athlete, "running", 3, 3, 480, 1600),
    ]
    assert not context(athlete, [activity(athlete, "running", 3)], rows).running.repeat_like_efforts


def test_usable_curves_are_monotonic_without_overwriting_raw_representatives():
    athlete = uuid4()
    bike = [
        lap(athlete, "cycling", 4, 10001, 180, power=140),
        lap(athlete, "cycling", 4, 10002, 300, power=220),
        lap(athlete, "cycling", 4, 10003, 600, power=170),
    ]
    bike_points = context(athlete, [activity(athlete, "cycling", 4)], bike).cycling.duration_efforts
    assert [point.representative_value for point in bike_points] == [Decimal("140.00"), Decimal("220.00"), Decimal("170.00")]
    assert [point.usable_representative_value for point in bike_points] == [Decimal("180.00"), Decimal("180.00"), Decimal("170.00")]

    run = [
        lap(athlete, "running", 4, 10003, 120, 500),
        lap(athlete, "running", 4, 10004, 180, 900),
        lap(athlete, "running", 4, 10005, 300, 1200),
    ]
    run_points = context(athlete, [activity(athlete, "running", 4)], run).running.duration_efforts
    assert [point.representative_value for point in run_points] == [Decimal("240.00"), Decimal("200.00"), Decimal("250.00")]
    assert [point.usable_representative_value for point in run_points] == [Decimal("220.00"), Decimal("220.00"), Decimal("250.00")]


def test_swim_temporal_coherence_excludes_autopause_anomaly_but_keeps_valid_fast_lap():
    athlete = uuid4()
    anomalous = lap(athlete, "swimming", 2, 0, 100, 200, elapsed=240, moving=100)
    valid_fast = lap(athlete, "swimming", 3, 1, 180, 200)
    typical = [lap(athlete, "swimming", 4, index + 2, seconds, 200) for index, seconds in enumerate((218, 220, 222, 224))]
    point = next(item for item in context(athlete, [activity(athlete, "swimming", 2)], [anomalous, valid_fast, *typical]).swimming.distance_efforts if item.distance_m == 200)
    assert point.best_value == Decimal("90.00")
    assert point.representative_support_count == 5
    assert Decimal("109") <= point.representative_value <= Decimal("112")


def test_point_traceability_separates_best_source_from_representative_recency_and_bounds_sources():
    athlete = uuid4()
    sources = [uuid4() for _ in range(6)]
    rows = [lap(source, "running", 60 - index * 10, 10003, 120, 600 if index == 0 else 500 + index * 5) for index, source in enumerate(sources)]
    point = next(item for item in context(athlete, [activity(athlete, "running", 1)], rows).running.duration_efforts if item.duration_seconds == 120)
    assert point.best_source_activity_id == sources[0]
    assert point.best_source_date == AS_OF - timedelta(days=60)
    assert point.representative_latest_evidence_date == AS_OF - timedelta(days=10)
    assert 1 <= len(point.representative_source_activity_ids) <= 4
    assert point.evidence_coverage == Decimal("1.00")


def test_impossible_run_and_isolated_power_spikes_are_excluded():
    athlete = uuid4()
    rows = (lap(athlete,"running",1,0,10,100), lap(athlete,"cycling",1,1,1,power=900))
    result = context(athlete,[activity(athlete,"running",1),activity(athlete,"cycling",1)],rows)
    assert not result.running.duration_efforts
    assert not result.cycling.duration_efforts


def test_two_activities_and_two_weeks_return_low_confidence_without_exception():
    athlete=uuid4(); result=context(athlete,[activity(athlete,"running",1),activity(athlete,"running",8)])
    assert result.activity_count == 2 and result.weeks_with_training == 2
    assert result.confidence is CapabilityConfidence.LOW


def test_long_summary_strength_volume_trend_and_reference_staleness_are_auditable():
    athlete=uuid4()
    activities=[activity(athlete,"running",days,minutes=70 if days<28 else 40) for days in (2,9,16,23,30,37,44,51)]
    activities += [activity(athlete,"strength",days,minutes=35) for days in (3,10,17,24)]
    threshold_laps=[lap(athlete,"running",days,index,1200,5000) for index,days in enumerate((2,9,16,23))]
    result=context(athlete,activities,threshold_laps,PerformanceSnapshot(running_threshold_pace_seconds_per_km=Decimal("260")))
    assert result.running.summary.trend == "increasing"
    assert result.running.summary.long_tolerance.long_session_count == 4
    assert result.strength.summary.activity_count == 4 and result.strength.summary.distance_per_week_m is None
    assert result.reference_staleness_signals[0].reference_type == "running_threshold_pace_seconds_per_km"


def test_stream_windows_require_sustained_duration_and_produce_one_support_per_activity(db):
    athlete=AthleteProfile(display_name="Stream",timezone="UTC",unit_system="metric");db.add(athlete);db.flush()
    row=CompletedActivity(athlete_id=athlete.id,source_summary="manual",sport="running",name="Tempo",start_at=datetime(2026,8,24,10,tzinfo=timezone.utc),timezone="UTC",elapsed_time_s=300,moving_time_s=300,distance_m=1500)
    db.add(row);db.flush()
    times=list(range(0,301,10));distances=[value*5 for value in times]
    for kind,values in (("time",times),("distance",distances)):
        db.add(ActivityStream(completed_activity_id=row.id,stream_type=kind,original_resolution="high",original_series_type="time",original_sample_count=len(values),sample_count=len(values),values=values,fetched_at=datetime(2026,8,25,tzinfo=timezone.utc),retention_class="performance",checksum=f"{kind}-checksum",version=1))
    db.flush()
    result=AthleteCapabilityContextAssembler(db).assemble(athlete_profile_id=athlete.id,as_of_date=AS_OF,timezone_name="UTC")
    point=next(item for item in result.running.duration_efforts if item.duration_seconds==180)
    assert point.representative_support_count == 1 and point.representative_value == Decimal("200.00")


@pytest.fixture
def db():
    engine=create_engine("sqlite+pysqlite:///:memory:",poolclass=StaticPool);Base.metadata.create_all(engine);session=Session(engine)
    try: yield session
    finally: session.close();engine.dispose()


def _db_athlete(session, name, power):
    athlete=AthleteProfile(display_name=name,timezone="UTC",unit_system="metric");session.add(athlete);session.flush()
    session.add(AthletePerformanceProfileVersion(athlete_profile_id=athlete.id,effective_from=datetime(2026,1,1,tzinfo=timezone.utc),data_origin="manual",algorithm_version="profile",cycling_ftp_watts=Decimal("140")))
    row=CompletedActivity(athlete_id=athlete.id,source_summary="manual",sport="cycling",name="Intervals",start_at=datetime(2026,8,24,10,tzinfo=timezone.utc),timezone="UTC",elapsed_time_s=3600,moving_time_s=3600)
    session.add(row);session.flush()
    for index in range(4): session.add(ActivityLap(completed_activity_id=row.id,provider_index=index,lap_index=index,elapsed_time_seconds=180,moving_time_seconds=180,average_watts=power))
    session.flush();return athlete


def test_application_queries_are_strictly_cross_athlete_isolated(db):
    a=_db_athlete(db,"A",150);b=_db_athlete(db,"B",180)
    service=AthleteCapabilityContextAssembler(db)
    ca=service.assemble(athlete_profile_id=a.id,as_of_date=AS_OF,timezone_name="UTC")
    cb=service.assemble(athlete_profile_id=b.id,as_of_date=AS_OF,timezone_name="UTC")
    pa=next(item for item in ca.cycling.duration_efforts if item.duration_seconds==180)
    pb=next(item for item in cb.cycling.duration_efforts if item.duration_seconds==180)
    assert pa.representative_value==Decimal("150.00") and pb.representative_value==Decimal("180.00")
    assert pa.best_source_activity_id != pb.best_source_activity_id


def test_planning_context_and_fingerprint_do_not_change_after_read_only_capability(db):
    athlete, goal = seed_identity_goal(db)
    request=make_request(athlete,goal)
    before=assembler(db).assemble(request)
    capability=assembler(db).assemble_capability(request)
    after=assembler(db).assemble(request)
    assert before == after and before.fingerprint == after.fingerprint
    assert capability.athlete_profile_id == athlete.id


def test_adaptive_planning_context_computes_capability_once_and_fingerprints_snapshot(db, monkeypatch):
    athlete, goal = seed_identity_goal(db)
    request = make_request(athlete, goal)
    service = assembler(db)
    baseline = service.assemble(request)
    original = AthleteCapabilityContextAssembler.assemble
    calls = []
    def counted(self, **kwargs):
        calls.append(kwargs["athlete_profile_id"])
        return original(self, **kwargs)
    monkeypatch.setattr(AthleteCapabilityContextAssembler, "assemble", counted)
    adaptive = service.assemble(request, include_capability=True)
    assert calls == [athlete.id]
    assert adaptive.adaptive_capability is not None
    assert adaptive.adaptive_capability.cutoff_date == request.planning_date
    assert adaptive.fingerprint != baseline.fingerprint
