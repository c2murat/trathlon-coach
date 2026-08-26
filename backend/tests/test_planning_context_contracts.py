from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.domains.planning.contracts import (
    AvailabilitySlot,
    PlanningMode,
    PlanningPreferences,
    PlanningRequest,
    canonical_json,
    context_fingerprint,
)


ATHLETE_ID = UUID("00000000-0000-0000-0000-000000000001")
GOAL_ID = UUID("00000000-0000-0000-0000-000000000002")


def preferences(minutes=60):
    return PlanningPreferences(
        availability_slots=(AvailabilitySlot(weekday=1, available_minutes=minutes, max_sessions=1),),
        max_sessions_per_day=1,
        max_sessions_per_week=6,
        preferred_rest_days=(0,),
        preferred_long_run_day=6,
        preferred_long_bike_day=5,
        strength_sessions_per_week=2,
    )


def request(**changes):
    values = dict(
        athlete_id=ATHLETE_ID,
        planning_date=date(2026, 6, 10),
        timezone_name="Europe/Madrid",
        goal_ids=(GOAL_ID,),
        mode=PlanningMode.INITIAL_PLAN,
        start_date=date(2026, 6, 10),
        preferences=preferences(),
        algorithm_version="planning-test-1",
        configuration_version="config-test-1",
    )
    values.update(changes)
    return PlanningRequest(**values)


def test_contracts_are_frozen_and_validate_timezone_order_and_ranges():
    value = request()
    with pytest.raises(ValidationError):
        value.planning_date = date(2026, 6, 11)
    with pytest.raises(ValidationError):
        request(timezone_name="Mars/Olympus")
    with pytest.raises(ValidationError):
        request(goal_ids=(GOAL_ID, GOAL_ID))
    with pytest.raises(ValidationError):
        PlanningPreferences(
            availability_slots=(
                AvailabilitySlot(weekday=2, available_minutes=30, max_sessions=1),
                AvailabilitySlot(weekday=1, available_minutes=30, max_sessions=1),
            ),
            max_sessions_per_day=1,
            max_sessions_per_week=2,
            strength_sessions_per_week=0,
        )


def test_replan_mode_is_part_of_the_pure_request_contract():
    assert request(mode=PlanningMode.REPLAN_FROM_DATE).mode is PlanningMode.REPLAN_FROM_DATE


def test_canonical_json_ignores_dictionary_insertion_order():
    first = {"b": Decimal("1.20"), "a": {"y": 2, "x": 1}}
    second = {"a": {"x": 1, "y": 2}, "b": Decimal("1.20")}
    assert canonical_json(first) == canonical_json(second)
    assert context_fingerprint(first) == context_fingerprint(second)
    assert context_fingerprint({"value": Decimal("1.20")}) == context_fingerprint({"value": Decimal("1.2")})


@pytest.mark.parametrize(
    "field,changed",
    [
        ("ftp", Decimal("251")),
        ("goal_date", "2026-09-02"),
        ("segment_distance", 10001),
        ("training_load", Decimal("101")),
        ("status_form", Decimal("-4")),
        ("preference_minutes", 61),
        ("algorithm_version", "planning-test-2"),
    ],
)
def test_relevant_context_changes_change_fingerprint(field, changed):
    baseline = {
        "ftp": Decimal("250"),
        "goal_date": "2026-09-01",
        "segment_distance": 10000,
        "training_load": Decimal("100"),
        "status_form": Decimal("-3"),
        "preference_minutes": 60,
        "algorithm_version": "planning-test-1",
    }
    modified = dict(baseline)
    modified[field] = changed
    assert context_fingerprint(baseline) != context_fingerprint(modified)
