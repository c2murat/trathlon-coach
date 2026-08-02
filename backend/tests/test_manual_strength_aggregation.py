from datetime import datetime, timezone
from decimal import Decimal

from app.domains.training_load_aggregation import ActivityLoadEntry, aggregate_daily_training_load, aggregate_weekly_training_load
from app.domains.training_load_aggregation.manual_strength import ManualStrengthLoadEntry, combine_daily_training_load, combine_weekly_training_load


def endurance(start, load=40):
    entries = (ActivityLoadEntry("activity", start, load, "0.7b.1", quality="high", duration_seconds=3600),)
    return aggregate_daily_training_load(entries, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")


def test_endurance_only_is_unchanged():
    original = endurance(datetime(2026, 8, 2, 8, tzinfo=timezone.utc))
    combined = combine_daily_training_load(original, (), timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    assert combined[0].endurance_load == combined[0].total_load == Decimal("40.00")
    assert combined[0].strength_load == 0
    assert combined[0].strength_session_count == 0


def test_strength_only_and_mixed_days_sum_components():
    start = datetime(2026, 8, 2, 8, tzinfo=timezone.utc)
    entries = (ManualStrengthLoadEntry("one", start, Decimal("25.00"), "0.7e.1"), ManualStrengthLoadEntry("two", start, Decimal("10.00"), "0.7e.1"))
    strength_only = combine_daily_training_load((), entries, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    mixed = combine_daily_training_load(endurance(start), entries, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    assert (strength_only[0].endurance_load, strength_only[0].strength_load, strength_only[0].total_load) == (0, 35, 35)
    assert mixed[0].total_load == mixed[0].endurance_load + mixed[0].strength_load == 75
    assert mixed[0].strength_session_count == 2


def test_wrong_version_is_excluded_and_session_is_not_duplicated():
    start = datetime(2026, 8, 2, 8, tzinfo=timezone.utc)
    entries = (ManualStrengthLoadEntry("same", start, 20, "0.7e.1"), ManualStrengthLoadEntry("same", start, 20, "0.7e.1"), ManualStrengthLoadEntry("other", start, 99, "future"))
    result = combine_daily_training_load((), entries, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    assert result[0].strength_load == 20
    assert result[0].strength_session_count == 1


def test_requested_timezone_controls_local_day_near_midnight_and_dst():
    entries = (
        ManualStrengthLoadEntry("midnight", datetime(2026, 8, 1, 22, 30, tzinfo=timezone.utc), 10, "0.7e.1"),
        ManualStrengthLoadEntry("dst", datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc), 10, "0.7e.1"),
    )
    result = combine_daily_training_load((), entries, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    assert [item.local_date.isoformat() for item in result] == ["2026-03-29", "2026-08-02"]


def test_weekly_is_sum_of_daily_components():
    start = datetime(2026, 8, 2, 8, tzinfo=timezone.utc)
    activities = (ActivityLoadEntry("activity", start, 40, "0.7b.1", quality="high", duration_seconds=1),)
    endurance_weekly = aggregate_weekly_training_load(activities, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    daily = combine_daily_training_load(aggregate_daily_training_load(activities, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1"), (ManualStrengthLoadEntry("strength", start, 25, "0.7e.1"),), timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    weekly = combine_weekly_training_load(endurance_weekly, daily, timezone_name="Europe/Madrid", source_algorithm_version="0.7b.1")
    assert weekly[0].total_load == weekly[0].endurance_load + weekly[0].strength_load == 65
    assert weekly[0].strength_session_count == 1
