from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CompletedActivity


class MultiAthleteIntegrityError(Exception):
    """Persisted or proposed data crosses an athlete boundary."""


def validate_activity_ids(session: Session, *, athlete_id: UUID, activity_ids: list | tuple) -> None:
    normalized = [UUID(str(value)) for value in activity_ids]
    if len(set(normalized)) != len(normalized):
        raise MultiAthleteIntegrityError("duplicate_activity_id")
    rows = list(session.execute(select(CompletedActivity.id, CompletedActivity.athlete_id).where(CompletedActivity.id.in_(normalized))).all())
    if len(rows) != len(normalized):
        raise MultiAthleteIntegrityError("activity_not_found")
    if any(row.athlete_id != athlete_id for row in rows):
        raise MultiAthleteIntegrityError("activity_tenant_mismatch")


def validate_aggregate_rows(session: Session, rows) -> None:
    for row in rows:
        validate_activity_ids(session, athlete_id=row.athlete_profile_id, activity_ids=row.activity_ids)
