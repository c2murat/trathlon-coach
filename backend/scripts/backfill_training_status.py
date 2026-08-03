from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.application.training_status import TrainingStatusApplication
from app.db.models import AthleteDailyTrainingLoad, AthleteDailyTrainingStatus
from app.db.session import SessionLocal
from app.domains.training_status import ALGORITHM_VERSION


@dataclass(frozen=True, slots=True)
class BackfillTrainingStatusOptions:
    athlete_id: UUID
    timezone_name: str = "Europe/Madrid"
    training_load_algorithm_version: str = "0.7b.1"
    manual_strength_algorithm_version: str = "0.7e.1"
    training_status_algorithm_version: str = ALGORITHM_VERSION
    start_date: date | None = None
    end_date: date | None = None
    dry_run: bool = False

    def __post_init__(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be provided together")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")


@dataclass(frozen=True, slots=True)
class BackfillTrainingStatusResult:
    requested_start_date: date
    requested_end_date: date
    first_source_date: date | None
    effective_end_date: date | None
    existing_before: int
    persisted_after: int
    latest: AthleteDailyTrainingStatus | None
    dry_run: bool


def _filters(options: BackfillTrainingStatusOptions, model):
    load_field = (
        model.source_load_algorithm_version
        if model is AthleteDailyTrainingLoad
        else model.training_load_algorithm_version
    )
    return (
        model.athlete_profile_id == options.athlete_id,
        model.timezone_name == options.timezone_name,
        load_field == options.training_load_algorithm_version,
        model.manual_strength_algorithm_version
        == options.manual_strength_algorithm_version,
    )


def backfill_training_status(
    session: Session,
    options: BackfillTrainingStatusOptions,
    *,
    reporter: Callable[[str], None] = print,
    clock: Callable[[], datetime] = datetime.now,
) -> BackfillTrainingStatusResult:
    zone = ZoneInfo(options.timezone_name)
    first_source = session.scalar(
        select(func.min(AthleteDailyTrainingLoad.local_date)).where(
            *_filters(options, AthleteDailyTrainingLoad)
        )
    )
    start = options.start_date or first_source or clock().astimezone(zone).date()
    end = options.end_date or clock().astimezone(zone).date()
    existing_before = session.scalar(
        select(func.count()).select_from(AthleteDailyTrainingStatus).where(
            *_filters(options, AthleteDailyTrainingStatus),
            AthleteDailyTrainingStatus.training_status_algorithm_version
            == options.training_status_algorithm_version,
        )
    )
    application = TrainingStatusApplication(session)
    rows = application.recalculate_training_status(
        options.athlete_id,
        start_date=start,
        end_date=end,
        timezone_name=options.timezone_name,
        training_load_algorithm_version=options.training_load_algorithm_version,
        manual_strength_algorithm_version=options.manual_strength_algorithm_version,
        training_status_algorithm_version=options.training_status_algorithm_version,
    )
    latest = application.get_latest_training_status(
        options.athlete_id,
        timezone_name=options.timezone_name,
        training_load_algorithm_version=options.training_load_algorithm_version,
        manual_strength_algorithm_version=options.manual_strength_algorithm_version,
        training_status_algorithm_version=options.training_status_algorithm_version,
    )
    persisted_after = session.scalar(
        select(func.count()).select_from(AthleteDailyTrainingStatus).where(
            *_filters(options, AthleteDailyTrainingStatus),
            AthleteDailyTrainingStatus.training_status_algorithm_version
            == options.training_status_algorithm_version,
        )
    )
    effective_end = latest.local_date if latest else None
    reporter(f"Athlete: {options.athlete_id}")
    reporter(f"Timezone: {options.timezone_name}")
    reporter(
        "Versiones: "
        f"load={options.training_load_algorithm_version} "
        f"manual={options.manual_strength_algorithm_version} "
        f"status={options.training_status_algorithm_version}"
    )
    reporter(f"Rango solicitado: {start}..{end}")
    reporter(f"Primera fuente: {first_source or 'sin fuentes'}")
    reporter(f"Final efectivo: {effective_end or 'sin estados'}")
    reporter(f"Estados: antes={existing_before} después={persisted_after}")
    if latest:
        reporter(
            f"Último: {latest.local_date} fitness={latest.fitness} "
            f"fatigue={latest.fatigue} form={latest.form} "
            f"history_day_number={latest.history_day_number}"
        )
    reporter("Modo: dry-run" if options.dry_run else "Modo: ejecución real")
    result = BackfillTrainingStatusResult(
        start, end, first_source, effective_end, existing_before,
        persisted_after, latest, options.dry_run,
    )
    if options.dry_run:
        session.rollback()
    else:
        session.commit()
    return result


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from error


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use a valid UUID") from error


def build_parser():
    parser = argparse.ArgumentParser(description="Backfill histórico de Fitness, Fatiga y Forma.")
    parser.add_argument("--athlete-id", type=_uuid, required=True)
    parser.add_argument("--timezone-name", default="Europe/Madrid")
    parser.add_argument("--training-load-algorithm-version", default="0.7b.1")
    parser.add_argument("--manual-strength-algorithm-version", default="0.7e.1")
    parser.add_argument("--training-status-algorithm-version", default=ALGORITHM_VERSION)
    parser.add_argument("--start-date", type=_date)
    parser.add_argument("--end-date", type=_date)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    try:
        options = BackfillTrainingStatusOptions(
            athlete_id=arguments.athlete_id,
            timezone_name=arguments.timezone_name,
            training_load_algorithm_version=arguments.training_load_algorithm_version,
            manual_strength_algorithm_version=arguments.manual_strength_algorithm_version,
            training_status_algorithm_version=arguments.training_status_algorithm_version,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
            dry_run=arguments.dry_run,
        )
        with SessionLocal() as session:
            backfill_training_status(session, options)
        return 0
    except Exception as error:
        print(f"Backfill interrumpido: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())



