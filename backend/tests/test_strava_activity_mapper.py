from datetime import timezone

import pytest

from app.providers.base import InvalidPayloadError
from app.providers.strava.activity_mapper import (
    StravaActivityMapper,
    StravaActivityOwnershipError,
)


def summary(**overrides):
    value = {
        "id": 123,
        "athlete": {"id": 456},
        "name": "Morning ride",
        "sport_type": "Ride",
        "start_date": "2026-07-01T06:00:00Z",
        "timezone": "(GMT+01:00) Europe/Madrid",
        "elapsed_time": 3600,
        "moving_time": 3500,
        "distance": 30000.5,
        "total_elevation_gain": 250.0,
        "average_heartrate": 145.0,
        "max_heartrate": 180.0,
        "average_speed": 8.5,
        "max_speed": 15.0,
        "average_cadence": 88.0,
        "average_watts": 210.0,
        "max_watts": 700.0,
        "weighted_average_watts": 225.0,
        "trainer": False,
        "commute": True,
        "manual": False,
        "visibility": "followers_only",
    }
    value.update(overrides)
    return value


def test_mapper_maps_supported_summary_fields_and_metric_units():
    mapped = StravaActivityMapper().map_summary(
        summary(), external_account_id="456", athlete_timezone="UTC"
    )
    assert mapped.external_activity_id == "123"
    assert mapped.sport == "cycling"
    assert mapped.start_at.tzinfo == timezone.utc
    assert mapped.timezone == "Europe/Madrid"
    assert mapped.distance_m == 30000.5
    assert mapped.weighted_average_power_w == 225.0
    assert mapped.visibility == "followers_only"


@pytest.mark.parametrize(
    ("provider_type", "expected"),
    [
        ("Swim", "swimming"),
        ("Run", "running"),
        ("WeightTraining", "strength"),
        ("Multisport", "multisport"),
        ("Kayaking", "other"),
    ],
)
def test_mapper_normalizes_supported_sports(provider_type, expected):
    mapped = StravaActivityMapper().map_summary(
        summary(sport_type=provider_type),
        external_account_id="456",
        athlete_timezone="UTC",
    )
    assert mapped.sport == expected


def test_mapper_handles_missing_optional_values_without_inventing_metrics():
    mapped = StravaActivityMapper().map_summary(
        {
            "id": 123,
            "sport_type": "Run",
            "start_date": "2026-07-01T06:00:00Z",
            "elapsed_time": 60,
        },
        external_account_id="456",
        athlete_timezone="Europe/Madrid",
    )
    assert mapped.distance_m is None
    assert mapped.average_heart_rate_bpm is None
    assert mapped.timezone == "Europe/Madrid"


def test_mapper_rejects_malformed_and_wrong_owner_summaries():
    mapper = StravaActivityMapper()
    with pytest.raises(InvalidPayloadError):
        mapper.map_summary(
            summary(elapsed_time=-1),
            external_account_id="456",
            athlete_timezone="UTC",
        )
    with pytest.raises(StravaActivityOwnershipError):
        mapper.map_summary(
            summary(athlete={"id": 999}),
            external_account_id="456",
            athlete_timezone="UTC",
        )


def test_detail_mapper_preserves_zero_false_and_provider_units():
    mapped = StravaActivityMapper().map_detail({"id":42,"athlete":{"id":456},"description":" Provider note ","calories":0,"average_temp":-2.5,"device_watts":False,"has_heartrate":False,"max_watts":315,"total_work":120000,"kilojoules":120.0,"achievement_count":0}, expected_external_activity_id="42", external_account_id="456")
    assert mapped.provider_description == "Provider note"
    assert mapped.calories_kcal == 0 and mapped.average_temperature_c == -2.5
    assert mapped.has_power_meter is False and mapped.has_heartrate is False
    assert mapped.max_power_w == 315 and mapped.total_work_j == 120000
    assert mapped.achievement_count == 0


def test_detail_mapper_accepts_missing_optional_fields_and_validates_identity():
    mapped = StravaActivityMapper().map_detail({"id":42,"athlete":{"id":456}}, expected_external_activity_id="42", external_account_id="456")
    assert all(value is None for key,value in mapped.provider_fields().items())
    with pytest.raises(InvalidPayloadError):
        StravaActivityMapper().map_detail({"id":43,"athlete":{"id":456}}, expected_external_activity_id="42", external_account_id="456")
    with pytest.raises(StravaActivityOwnershipError):
        StravaActivityMapper().map_detail({"id":42,"athlete":{"id":999}}, expected_external_activity_id="42", external_account_id="456")


def test_detail_mapper_accepts_integral_float_suffer_score_from_real_provider_shape():
    mapped = StravaActivityMapper().map_detail(
        {"id": 19304480601, "athlete": {"id": 456}, "suffer_score": 71.0},
        expected_external_activity_id="19304480601",
        external_account_id="456",
    )
    assert mapped.suffer_score == 71
    assert isinstance(mapped.suffer_score, int)


def test_detail_mapper_rejects_fractional_integer_metric():
    with pytest.raises(InvalidPayloadError):
        StravaActivityMapper().map_detail(
            {"id": 42, "athlete": {"id": 456}, "suffer_score": 71.5},
            expected_external_activity_id="42",
            external_account_id="456",
        )
