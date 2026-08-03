from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.application.training_status import TrainingStatusApplication
from app.domains.training_status import ALGORITHM_VERSION


@dataclass(frozen=True, slots=True)
class TrainingStatusSyncCoordinate:
    athlete_id: object
    affected_start_date: date
    affected_end_date: date
    timezone_name: str
    training_load_algorithm_version: str
    manual_strength_algorithm_version: str
    training_status_algorithm_version: str = ALGORITHM_VERSION


def sync_training_status_after_load_change(
    session,
    *,
    athlete_id,
    affected_start_date: date,
    affected_end_date: date,
    timezone_name: str,
    training_load_algorithm_version: str,
    manual_strength_algorithm_version: str,
    training_status_algorithm_version: str = ALGORITHM_VERSION,
    through_date: date | None = None,
    clock=None,
):
    zone = ZoneInfo(timezone_name)
    current = clock() if clock else datetime.now(zone)
    local_today = through_date if through_date is not None else current.astimezone(zone).date()
    requested_end = max(affected_end_date, local_today)
    return TrainingStatusApplication(session).recalculate_training_status(
        athlete_id,
        start_date=affected_start_date,
        end_date=requested_end,
        timezone_name=timezone_name,
        training_load_algorithm_version=training_load_algorithm_version,
        manual_strength_algorithm_version=manual_strength_algorithm_version,
        training_status_algorithm_version=training_status_algorithm_version,
    )


def sync_training_status_coordinates(
    session,
    coordinates: tuple[TrainingStatusSyncCoordinate, ...],
    *,
    through_date: date | None = None,
    clock=None,
):
    grouped: dict[tuple, tuple[date, date]] = {}
    for item in coordinates:
        key = (
            item.athlete_id,
            item.timezone_name,
            item.training_load_algorithm_version,
            item.manual_strength_algorithm_version,
            item.training_status_algorithm_version,
        )
        previous = grouped.get(key)
        grouped[key] = (
            min(previous[0], item.affected_start_date) if previous else item.affected_start_date,
            max(previous[1], item.affected_end_date) if previous else item.affected_end_date,
        )
    results = []
    for key in sorted(grouped, key=lambda value: tuple(str(part) for part in value)):
        start, end = grouped[key]
        athlete, timezone_name, load_version, manual_version, status_version = key
        results.append(
            sync_training_status_after_load_change(
                session,
                athlete_id=athlete,
                affected_start_date=start,
                affected_end_date=end,
                timezone_name=timezone_name,
                training_load_algorithm_version=load_version,
                manual_strength_algorithm_version=manual_version,
                training_status_algorithm_version=status_version,
                through_date=through_date,
                clock=clock,
            )
        )
    return tuple(results)
