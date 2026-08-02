from __future__ import annotations

from datetime import datetime, timezone
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.db.models import AthleteProfile, ManualStrengthSession, ManualStrengthTrainingLoad
from app.domains.manual_strength import (
    ALGORITHM_VERSION,
    BodyRegion,
    InvalidManualStrengthInputError,
    ManualStrengthLoadInput,
    ManualStrengthLoadResult,
    calculate_manual_strength_load,
)

MAX_NOTES_LENGTH: Final = 2000
_UNSET: Final = object()


class ManualStrengthApplicationError(Exception):
    pass


class ManualStrengthSessionNotFoundError(ManualStrengthApplicationError):
    pass


class ManualStrengthAthleteNotFoundError(ManualStrengthApplicationError):
    pass


class InvalidManualStrengthSessionInputError(ManualStrengthApplicationError):
    pass


class InvalidManualStrengthTimezoneError(InvalidManualStrengthSessionInputError):
    pass


class NaiveManualStrengthDatetimeError(InvalidManualStrengthSessionInputError):
    pass


class ManualStrengthNotesTooLongError(InvalidManualStrengthSessionInputError):
    pass


def _require_aware(value: object, name: str = "started_at") -> datetime:
    if not isinstance(value, datetime):
        raise InvalidManualStrengthSessionInputError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise NaiveManualStrengthDatetimeError(f"{name} must include timezone information")
    return value


def _validate_timezone(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise InvalidManualStrengthTimezoneError("timezone_name must be a non-empty canonical name")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise InvalidManualStrengthTimezoneError("timezone_name is unknown") from error
    return value


def _normalize_notes(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidManualStrengthSessionInputError("notes must be a string or None")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_NOTES_LENGTH:
        raise ManualStrengthNotesTooLongError(
            f"notes must not exceed {MAX_NOTES_LENGTH} characters"
        )
    return normalized


def _normalize_regions(value: object) -> tuple[BodyRegion, ...]:
    if not isinstance(value, tuple):
        raise InvalidManualStrengthSessionInputError("body_regions must be a tuple")
    regions: list[BodyRegion] = []
    for item in value:
        if isinstance(item, BodyRegion):
            regions.append(item)
        elif isinstance(item, str):
            try:
                regions.append(BodyRegion(item))
            except ValueError as error:
                raise InvalidManualStrengthSessionInputError("unknown body region") from error
        else:
            raise InvalidManualStrengthSessionInputError("unknown body region")
    return tuple(regions)


def _load_input(
    duration_minutes: object, body_regions: object, perceived_exertion: object
) -> ManualStrengthLoadInput:
    try:
        return ManualStrengthLoadInput(
            duration_minutes=duration_minutes,  # type: ignore[arg-type]
            body_regions=_normalize_regions(body_regions),
            perceived_exertion=perceived_exertion,  # type: ignore[arg-type]
        )
    except InvalidManualStrengthInputError as error:
        raise InvalidManualStrengthSessionInputError(str(error)) from error


class ManualStrengthApplication:
    def __init__(self, session, clock=None):
        self.session = session
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _athlete(self, athlete_id: object) -> AthleteProfile:
        if not isinstance(athlete_id, UUID):
            raise InvalidManualStrengthSessionInputError("athlete_id must be a UUID")
        athlete = self.session.get(AthleteProfile, athlete_id)
        if athlete is None:
            raise ManualStrengthAthleteNotFoundError("athlete not found")
        return athlete

    def _owned_session(
        self, athlete_id: object, session_id: object
    ) -> ManualStrengthSession:
        if not isinstance(athlete_id, UUID) or not isinstance(session_id, UUID):
            raise InvalidManualStrengthSessionInputError(
                "athlete_id and session_id must be UUIDs"
            )
        row = self.session.scalar(
            select(ManualStrengthSession).where(
                ManualStrengthSession.id == session_id,
                ManualStrengthSession.athlete_id == athlete_id,
            )
        )
        if row is None:
            raise ManualStrengthSessionNotFoundError(
                "manual strength session not found"
            )
        return row

    def _sync_load(
        self, session_row: ManualStrengthSession, result: ManualStrengthLoadResult
    ) -> ManualStrengthTrainingLoad:
        row = self.session.scalar(
            select(ManualStrengthTrainingLoad).where(
                ManualStrengthTrainingLoad.session_id == session_row.id,
                ManualStrengthTrainingLoad.algorithm_version == ALGORITHM_VERSION,
            )
        )
        values = {
            "load_value": result.load_value,
            "method": result.method.value,
            "unit": result.unit.value,
            "quality": result.quality.value,
            "warnings": [warning.value for warning in result.warnings],
            "calculated_at": _require_aware(self.clock(), "calculated_at"),
        }
        if row is None:
            row = ManualStrengthTrainingLoad(
                session_id=session_row.id,
                algorithm_version=ALGORITHM_VERSION,
                **values,
            )
            self.session.add(row)
        else:
            for name, value in values.items():
                setattr(row, name, value)
        return row

    def create_manual_strength_session(
        self,
        athlete_id: UUID,
        *,
        started_at: datetime,
        timezone_name: str,
        duration_minutes: int,
        body_regions: tuple[BodyRegion | str, ...],
        perceived_exertion: int | None = None,
        notes: str | None = None,
    ) -> ManualStrengthSession:
        self._athlete(athlete_id)
        validated_started_at = _require_aware(started_at)
        validated_timezone = _validate_timezone(timezone_name)
        validated_notes = _normalize_notes(notes)
        input_data = _load_input(duration_minutes, body_regions, perceived_exertion)
        result = calculate_manual_strength_load(input_data)
        now = _require_aware(self.clock(), "created_at")
        row = ManualStrengthSession(
            athlete_id=athlete_id,
            started_at=validated_started_at,
            timezone_name=validated_timezone,
            duration_minutes=input_data.duration_minutes,
            body_regions=[region.value for region in input_data.body_regions],
            perceived_exertion=input_data.perceived_exertion,
            notes=validated_notes,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        self._sync_load(row, result)
        self.session.flush()
        return row

    def get_manual_strength_session(
        self, athlete_id: UUID, session_id: UUID
    ) -> ManualStrengthSession:
        return self._owned_session(athlete_id, session_id)

    def list_manual_strength_sessions(
        self,
        athlete_id: UUID,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> tuple[ManualStrengthSession, ...]:
        self._athlete(athlete_id)
        statement = select(ManualStrengthSession).where(
            ManualStrengthSession.athlete_id == athlete_id
        )
        if start_at is not None:
            statement = statement.where(
                ManualStrengthSession.started_at >= _require_aware(start_at, "start_at")
            )
        if end_at is not None:
            statement = statement.where(
                ManualStrengthSession.started_at <= _require_aware(end_at, "end_at")
            )
        statement = statement.order_by(
            ManualStrengthSession.started_at.desc(), ManualStrengthSession.id.desc()
        )
        return tuple(self.session.scalars(statement).all())

    def update_manual_strength_session(
        self,
        athlete_id: UUID,
        session_id: UUID,
        *,
        started_at: datetime | object = _UNSET,
        timezone_name: str | object = _UNSET,
        duration_minutes: int | object = _UNSET,
        body_regions: tuple[BodyRegion | str, ...] | object = _UNSET,
        perceived_exertion: int | None | object = _UNSET,
        notes: str | None | object = _UNSET,
    ) -> ManualStrengthSession:
        row = self._owned_session(athlete_id, session_id)
        final_started_at = row.started_at if started_at is _UNSET else _require_aware(started_at)
        final_timezone = row.timezone_name if timezone_name is _UNSET else _validate_timezone(timezone_name)
        final_notes = row.notes if notes is _UNSET else _normalize_notes(notes)
        final_duration = row.duration_minutes if duration_minutes is _UNSET else duration_minutes
        final_regions = tuple(row.body_regions) if body_regions is _UNSET else body_regions
        final_rpe = row.perceived_exertion if perceived_exertion is _UNSET else perceived_exertion
        input_data = _load_input(final_duration, final_regions, final_rpe)
        result = calculate_manual_strength_load(input_data)

        row.started_at = final_started_at
        row.timezone_name = final_timezone
        row.duration_minutes = input_data.duration_minutes
        row.body_regions = [region.value for region in input_data.body_regions]
        row.perceived_exertion = input_data.perceived_exertion
        row.notes = final_notes
        stale_loads = self.session.scalars(
            select(ManualStrengthTrainingLoad).where(
                ManualStrengthTrainingLoad.session_id == row.id,
                ManualStrengthTrainingLoad.algorithm_version != ALGORITHM_VERSION,
            )
        ).all()
        for stale_load in stale_loads:
            self.session.delete(stale_load)
        row.updated_at = _require_aware(self.clock(), "updated_at")
        self._sync_load(row, result)
        self.session.flush()
        return row

    def recalculate_manual_strength_load(
        self, athlete_id: UUID, session_id: UUID
    ) -> ManualStrengthTrainingLoad:
        row = self._owned_session(athlete_id, session_id)
        input_data = _load_input(
            row.duration_minutes, tuple(row.body_regions), row.perceived_exertion
        )
        load = self._sync_load(row, calculate_manual_strength_load(input_data))
        self.session.flush()
        return load

    def delete_manual_strength_session(
        self, athlete_id: UUID, session_id: UUID
    ) -> None:
        self.session.delete(self._owned_session(athlete_id, session_id))
        self.session.flush()


def create_manual_strength_session(session, athlete_id: UUID, **values):
    return ManualStrengthApplication(session).create_manual_strength_session(
        athlete_id, **values
    )


def get_manual_strength_session(session, athlete_id: UUID, session_id: UUID):
    return ManualStrengthApplication(session).get_manual_strength_session(
        athlete_id, session_id
    )


def list_manual_strength_sessions(session, athlete_id: UUID, **filters):
    return ManualStrengthApplication(session).list_manual_strength_sessions(
        athlete_id, **filters
    )


def update_manual_strength_session(
    session, athlete_id: UUID, session_id: UUID, **values
):
    return ManualStrengthApplication(session).update_manual_strength_session(
        athlete_id, session_id, **values
    )


def delete_manual_strength_session(session, athlete_id: UUID, session_id: UUID):
    return ManualStrengthApplication(session).delete_manual_strength_session(
        athlete_id, session_id
    )


def recalculate_manual_strength_load(session, athlete_id: UUID, session_id: UUID):
    return ManualStrengthApplication(session).recalculate_manual_strength_load(
        athlete_id, session_id
    )
