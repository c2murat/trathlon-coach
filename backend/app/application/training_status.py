from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from math import isfinite
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models.athlete import AthleteProfile
from app.db.models.training_load_aggregate import AthleteDailyTrainingLoad
from app.db.models.training_status import AthleteDailyTrainingStatus
from app.domains.training_status import (
    ALGORITHM_VERSION,
    DailyTrainingLoadInput,
    calculate_training_status_series,
)


class TrainingStatusApplicationError(Exception):
    """Base error for training-status application operations."""


class TrainingStatusAthleteNotFoundError(TrainingStatusApplicationError):
    pass


class InvalidTrainingStatusApplicationRangeError(TrainingStatusApplicationError):
    pass


class InvalidTrainingStatusTimezoneError(TrainingStatusApplicationError):
    pass


class InvalidTrainingStatusVersionError(TrainingStatusApplicationError):
    pass


class InvalidTrainingStatusSourceDataError(TrainingStatusApplicationError):
    pass


class DuplicateTrainingStatusSourceDateError(TrainingStatusApplicationError):
    pass


class TrainingStatusPersistenceError(TrainingStatusApplicationError):
    pass


class TrainingStatusApplication:
    def __init__(self, session, clock=None):
        self.session = session
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _validate_range(start_date: date, end_date: date) -> None:
        if type(start_date) is not date or type(end_date) is not date:
            raise InvalidTrainingStatusApplicationRangeError(
                "start_date and end_date must be dates"
            )
        if end_date < start_date:
            raise InvalidTrainingStatusApplicationRangeError(
                "start_date must be <= end_date"
            )

    @staticmethod
    def _validate_timezone(timezone_name: str) -> None:
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            raise InvalidTrainingStatusTimezoneError("timezone_name is required")
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
            raise InvalidTrainingStatusTimezoneError(
                "timezone_name is unknown"
            ) from error

    @staticmethod
    def _validate_versions(*versions: str) -> None:
        if any(not isinstance(version, str) or not version.strip() for version in versions):
            raise InvalidTrainingStatusVersionError(
                "algorithm versions must be non-empty strings"
            )

    def _validate_common(
        self,
        athlete_id,
        *,
        timezone_name: str,
        training_load_algorithm_version: str,
        manual_strength_algorithm_version: str,
        training_status_algorithm_version: str,
        require_athlete: bool = False,
    ) -> None:
        self._validate_timezone(timezone_name)
        self._validate_versions(
            training_load_algorithm_version,
            manual_strength_algorithm_version,
            training_status_algorithm_version,
        )
        if require_athlete and self.session.get(AthleteProfile, athlete_id) is None:
            raise TrainingStatusAthleteNotFoundError("athlete not found")

    @staticmethod
    def _source_load(row: AthleteDailyTrainingLoad) -> float:
        value = row.total_load
        if isinstance(value, bool):
            raise InvalidTrainingStatusSourceDataError("source total_load is invalid")
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError, InvalidOperation) as error:
            raise InvalidTrainingStatusSourceDataError(
                "source total_load is invalid"
            ) from error
        if not isfinite(numeric) or numeric < 0:
            raise InvalidTrainingStatusSourceDataError("source total_load is invalid")
        return numeric

    def _source_rows(
        self,
        athlete_id,
        timezone_name: str,
        training_load_algorithm_version: str,
        manual_strength_algorithm_version: str,
    ) -> tuple[AthleteDailyTrainingLoad, ...]:
        rows = tuple(
            self.session.scalars(
                select(AthleteDailyTrainingLoad)
                .where(
                    AthleteDailyTrainingLoad.athlete_profile_id == athlete_id,
                    AthleteDailyTrainingLoad.timezone_name == timezone_name,
                    AthleteDailyTrainingLoad.source_load_algorithm_version
                    == training_load_algorithm_version,
                    AthleteDailyTrainingLoad.manual_strength_algorithm_version
                    == manual_strength_algorithm_version,
                )
                .order_by(AthleteDailyTrainingLoad.local_date, AthleteDailyTrainingLoad.id)
            ).all()
        )
        seen: set[date] = set()
        for row in rows:
            if row.local_date in seen:
                raise DuplicateTrainingStatusSourceDateError(
                    f"duplicate source date: {row.local_date.isoformat()}"
                )
            seen.add(row.local_date)
            self._source_load(row)
        return rows

    @staticmethod
    def _combination_filter(
        athlete_id,
        timezone_name: str,
        training_load_algorithm_version: str,
        manual_strength_algorithm_version: str,
        training_status_algorithm_version: str,
    ):
        return (
            AthleteDailyTrainingStatus.athlete_profile_id == athlete_id,
            AthleteDailyTrainingStatus.timezone_name == timezone_name,
            AthleteDailyTrainingStatus.training_load_algorithm_version
            == training_load_algorithm_version,
            AthleteDailyTrainingStatus.manual_strength_algorithm_version
            == manual_strength_algorithm_version,
            AthleteDailyTrainingStatus.training_status_algorithm_version
            == training_status_algorithm_version,
        )

    def recalculate_training_status(
        self,
        athlete_id,
        *,
        start_date: date,
        end_date: date,
        timezone_name: str,
        training_load_algorithm_version: str,
        manual_strength_algorithm_version: str,
        training_status_algorithm_version: str = ALGORITHM_VERSION,
    ) -> tuple[AthleteDailyTrainingStatus, ...]:
        self._validate_range(start_date, end_date)
        self._validate_common(
            athlete_id,
            timezone_name=timezone_name,
            training_load_algorithm_version=training_load_algorithm_version,
            manual_strength_algorithm_version=manual_strength_algorithm_version,
            training_status_algorithm_version=training_status_algorithm_version,
            require_athlete=True,
        )
        if training_status_algorithm_version != ALGORITHM_VERSION:
            raise InvalidTrainingStatusVersionError(
                "unsupported training status algorithm version"
            )

        sources = tuple(
            sorted(
                self._source_rows(
                    athlete_id,
                    timezone_name,
                    training_load_algorithm_version,
                    manual_strength_algorithm_version,
                ),
                key=lambda row: (row.local_date, row.id),
            )
        )
        combination = self._combination_filter(
            athlete_id,
            timezone_name,
            training_load_algorithm_version,
            manual_strength_algorithm_version,
            training_status_algorithm_version,
        )
        existing = tuple(
            self.session.scalars(
                select(AthleteDailyTrainingStatus)
                .where(*combination)
                .order_by(AthleteDailyTrainingStatus.local_date)
            ).all()
        )

        if not sources:
            try:
                self.session.execute(delete(AthleteDailyTrainingStatus).where(*combination))
                self.session.flush()
            except SQLAlchemyError as error:
                raise TrainingStatusPersistenceError(
                    "could not remove obsolete training statuses"
                ) from error
            return ()

        first_source_date = sources[0].local_date
        latest_source_date = sources[-1].local_date
        latest_persisted_date = existing[-1].local_date if existing else first_source_date
        removed_loaded_tail = any(
            row.local_date > latest_source_date and row.total_load > 0
            for row in existing
        )
        if removed_loaded_tail and end_date <= latest_source_date:
            latest_persisted_date = latest_source_date
        effective_end_date = max(
            end_date,
            latest_source_date,
            latest_persisted_date,
        )
        entries = tuple(
            DailyTrainingLoadInput(row.local_date, self._source_load(row))
            for row in sources
            if row.local_date <= effective_end_date
        )
        series = calculate_training_status_series(
            entries,
            start_date=first_source_date,
            end_date=effective_end_date,
        )
        existing_by_date = {row.local_date: row for row in existing}
        generated_dates = {day.date for day in series.days}
        now = self.clock()

        try:
            for row in existing:
                if row.local_date not in generated_dates:
                    self.session.delete(row)
            for history_day_number, day in enumerate(series.days, start=1):
                row = existing_by_date.get(day.date)
                values = {
                    "total_load": Decimal(f"{day.total_load:.2f}"),
                    "fitness": Decimal(f"{day.fitness:.2f}"),
                    "fatigue": Decimal(f"{day.fatigue:.2f}"),
                    "form": Decimal(f"{day.form:.2f}"),
                    "history_day_number": history_day_number,
                    "is_warmup": day.is_warmup,
                    "calculated_at": now,
                }
                if row is None:
                    row = AthleteDailyTrainingStatus(
                        athlete_profile_id=athlete_id,
                        local_date=day.date,
                        timezone_name=timezone_name,
                        training_load_algorithm_version=training_load_algorithm_version,
                        manual_strength_algorithm_version=manual_strength_algorithm_version,
                        training_status_algorithm_version=day.algorithm_version,
                        **values,
                    )
                    self.session.add(row)
                else:
                    for field, value in values.items():
                        setattr(row, field, value)
            self.session.flush()
        except SQLAlchemyError as error:
            raise TrainingStatusPersistenceError(
                "could not persist training statuses"
            ) from error

        return self.list_training_status(
            athlete_id,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
            training_load_algorithm_version=training_load_algorithm_version,
            manual_strength_algorithm_version=manual_strength_algorithm_version,
            training_status_algorithm_version=training_status_algorithm_version,
        )

    def list_training_status(
        self,
        athlete_id,
        *,
        start_date: date,
        end_date: date,
        timezone_name: str,
        training_load_algorithm_version: str,
        manual_strength_algorithm_version: str,
        training_status_algorithm_version: str = ALGORITHM_VERSION,
    ) -> tuple[AthleteDailyTrainingStatus, ...]:
        self._validate_range(start_date, end_date)
        self._validate_common(
            athlete_id,
            timezone_name=timezone_name,
            training_load_algorithm_version=training_load_algorithm_version,
            manual_strength_algorithm_version=manual_strength_algorithm_version,
            training_status_algorithm_version=training_status_algorithm_version,
        )
        return tuple(
            self.session.scalars(
                select(AthleteDailyTrainingStatus)
                .where(
                    *self._combination_filter(
                        athlete_id,
                        timezone_name,
                        training_load_algorithm_version,
                        manual_strength_algorithm_version,
                        training_status_algorithm_version,
                    ),
                    AthleteDailyTrainingStatus.local_date.between(
                        start_date, end_date
                    ),
                )
                .order_by(AthleteDailyTrainingStatus.local_date)
            ).all()
        )

    def get_latest_training_status(
        self,
        athlete_id,
        *,
        timezone_name: str,
        training_load_algorithm_version: str,
        manual_strength_algorithm_version: str,
        training_status_algorithm_version: str = ALGORITHM_VERSION,
    ) -> AthleteDailyTrainingStatus | None:
        self._validate_common(
            athlete_id,
            timezone_name=timezone_name,
            training_load_algorithm_version=training_load_algorithm_version,
            manual_strength_algorithm_version=manual_strength_algorithm_version,
            training_status_algorithm_version=training_status_algorithm_version,
        )
        return self.session.scalar(
            select(AthleteDailyTrainingStatus)
            .where(
                *self._combination_filter(
                    athlete_id,
                    timezone_name,
                    training_load_algorithm_version,
                    manual_strength_algorithm_version,
                    training_status_algorithm_version,
                )
            )
            .order_by(AthleteDailyTrainingStatus.local_date.desc())
            .limit(1)
        )
