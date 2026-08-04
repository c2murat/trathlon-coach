from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.application.training_load import (  # noqa: E402
    ALGORITHM_VERSION,
    TrainingLoadApplication,
)
from app.db.models import CompletedActivity  # noqa: E402
from app.db.models.training_load import ActivityTrainingLoad  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402


@dataclass(frozen=True, slots=True)
class BackfillOptions:
    athlete_id: UUID | None = None
    all_athletes: bool = False
    confirm_all_athletes: bool = False
    start_date: date | None = None
    end_date: date | None = None
    batch_size: int = 50
    algorithm_version: str = ALGORITHM_VERSION
    recalculate_existing: bool = False
    dry_run: bool = False

    def __post_init__(self) -> None:
        if (self.athlete_id is None) == (not self.all_athletes):
            raise ValueError("select exactly one of athlete_id or all_athletes")
        if self.all_athletes and not self.dry_run and not self.confirm_all_athletes:
            raise ValueError("confirm_all_athletes is required for a real global run")
        if self.batch_size < 1:
            raise ValueError("batch_size must be greater than zero")
        if not self.algorithm_version.strip():
            raise ValueError("algorithm_version must not be empty")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")


@dataclass(frozen=True, slots=True)
class BackfillResult:
    total_considered: int
    already_existing: int
    calculated: int
    unavailable: int
    errors: int
    last_processed_id: UUID | None


def _activity_query(options: BackfillOptions):
    query = select(CompletedActivity).where(CompletedActivity.deleted_at.is_(None))
    if options.athlete_id is not None:
        query = query.where(CompletedActivity.athlete_id == options.athlete_id)
    if options.start_date is not None:
        query = query.where(
            CompletedActivity.start_at
            >= datetime.combine(options.start_date, time.min, tzinfo=timezone.utc)
        )
    if options.end_date is not None:
        query = query.where(
            CompletedActivity.start_at
            < datetime.combine(
                options.end_date + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
        )
    return query.order_by(CompletedActivity.start_at, CompletedActivity.id)


def backfill_training_load(
    session: Session,
    options: BackfillOptions,
    *,
    reporter: Callable[[str], None] = print,
    application_factory: Callable[[Session], TrainingLoadApplication] = (
        TrainingLoadApplication
    ),
) -> BackfillResult:
    reporter("Modo: dry-run" if options.dry_run else "Modo: ejecución real")
    reporter(f"Alcance: {options.athlete_id or 'todos los atletas'}")
    reporter(f"Versión: {options.algorithm_version} | rango={options.start_date or '*'}..{options.end_date or '*'} | lote={options.batch_size}")
    if options.all_athletes:
        athlete_ids=list(session.scalars(select(CompletedActivity.athlete_id).distinct().order_by(CompletedActivity.athlete_id)).all())
        results=[]
        for athlete_id in athlete_ids:
            try:
                results.append(backfill_training_load(session,BackfillOptions(athlete_id=athlete_id,start_date=options.start_date,end_date=options.end_date,batch_size=options.batch_size,algorithm_version=options.algorithm_version,recalculate_existing=options.recalculate_existing,dry_run=options.dry_run),reporter=reporter,application_factory=application_factory))
            except Exception as error:
                session.rollback();reporter(f"ERROR athlete_id={athlete_id}: {type(error).__name__}: {error}");results.append(BackfillResult(0,0,0,0,1,None))
        return BackfillResult(sum(x.total_considered for x in results),sum(x.already_existing for x in results),sum(x.calculated for x in results),sum(x.unavailable for x in results),sum(x.errors for x in results),results[-1].last_processed_id if results else None)
    activities = list(session.scalars(_activity_query(options)).all())
    activity_ids = [activity.id for activity in activities]
    existing_ids: set[UUID] = set()
    if activity_ids:
        existing_ids = set(
            session.scalars(
                select(ActivityTrainingLoad.completed_activity_id).where(
                    ActivityTrainingLoad.completed_activity_id.in_(activity_ids),
                    ActivityTrainingLoad.algorithm_version
                    == options.algorithm_version,
                )
            ).all()
        )

    selected = (
        activities
        if options.recalculate_existing
        else [activity for activity in activities if activity.id not in existing_ids]
    )
    reporter(f"Total consideradas: {len(activities)}")
    reporter(f"Ya existentes: {len(existing_ids)}")
    reporter(f"Pendientes de procesamiento: {len(selected)}")

    if options.dry_run:
        reporter("Dry-run: no se calcularon cargas ni se escribieron datos.")
        reporter(
            "Progreso: 0/"
            f"{len(selected)} (100.0%) | calculadas=0 "
            "no_disponibles=0 errores=0 ultimo_id=None"
        )
        return BackfillResult(
            total_considered=len(activities),
            already_existing=len(existing_ids),
            calculated=0,
            unavailable=0,
            errors=0,
            last_processed_id=None,
        )

    calculated = unavailable = errors = 0
    last_processed_id: UUID | None = None
    application = application_factory(session)
    total_selected = len(selected)

    for offset in range(0, total_selected, options.batch_size):
        batch = selected[offset : offset + options.batch_size]
        for activity in batch:
            last_processed_id = activity.id
            try:
                with session.begin_nested():
                    result = application.calculate_for_activity(
                        activity.athlete_id,
                        activity.id,
                        options.algorithm_version,
                    )
                calculated += 1
                if result.load is None:
                    unavailable += 1
            except Exception as error:
                errors += 1
                reporter(
                    f"ERROR activity_id={activity.id}: "
                    f"{type(error).__name__}: {error}"
                )

        session.commit()
        processed = min(offset + len(batch), total_selected)
        percentage = 100.0 if not total_selected else processed / total_selected * 100
        reporter(
            f"Progreso: {processed}/{total_selected} ({percentage:.1f}%) | "
            f"calculadas={calculated} no_disponibles={unavailable} "
            f"errores={errors} ultimo_id={last_processed_id}"
        )

    if not total_selected:
        reporter("Progreso: 0/0 (100.0%); no habÃ­a actividades pendientes.")

    return BackfillResult(
        total_considered=len(activities),
        already_existing=len(existing_ids),
        calculated=calculated,
        unavailable=unavailable,
        errors=errors,
        last_processed_id=last_processed_id,
    )


def _date_argument(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use YYYY-MM-DD") from error


def _uuid_argument(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("use a valid UUID") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill histÃ³rico de ActivityTrainingLoad.",
    )
    scope=parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--athlete-id", type=_uuid_argument)
    scope.add_argument("--all-athletes", action="store_true")
    parser.add_argument("--confirm-all-athletes", action="store_true")
    parser.add_argument("--start-date", type=_date_argument)
    parser.add_argument("--end-date", type=_date_argument)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--algorithm-version", default=ALGORITHM_VERSION)
    parser.add_argument("--recalculate-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        options = BackfillOptions(
            athlete_id=arguments.athlete_id,
            all_athletes=arguments.all_athletes,
            confirm_all_athletes=arguments.confirm_all_athletes,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
            batch_size=arguments.batch_size,
            algorithm_version=arguments.algorithm_version,
            recalculate_existing=arguments.recalculate_existing,
            dry_run=arguments.dry_run,
        )
    except ValueError as error:
        print(f"ConfiguraciÃ³n invÃ¡lida: {error}", file=sys.stderr)
        return 2

    try:
        with SessionLocal() as session:
            result = backfill_training_load(session, options)
    except Exception as error:
        print(
            f"Backfill interrumpido: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    print(
        "Resumen final: "
        f"consideradas={result.total_considered} "
        f"existentes={result.already_existing} "
        f"calculadas={result.calculated} "
        f"no_disponibles={result.unavailable} "
        f"errores={result.errors} "
        f"ultimo_id={result.last_processed_id}"
    )
    return 0 if result.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


