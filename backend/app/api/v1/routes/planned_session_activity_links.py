from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.athlete_permissions import AthleteCapability, require_athlete_capability
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.application.planned_session_activity_matching import (
    ActivityNotFoundError, AmbiguousMatchError, LinkConflictError, MatchClassification,
    NoMatchError, PlannedSessionActivityMatching, SessionNotFoundError,
)
from app.db.models import CompletedActivity, PlannedSessionActivityLink
from app.db.session import get_db_session

router = APIRouter(prefix="/training-plans/sessions", tags=["planned-session-activity-links"])
read = require_athlete_capability(AthleteCapability.READ_TRAINING_PLANNING)
manage = require_athlete_capability(AthleteCapability.GENERATE_TRAINING_PLAN)


class ManualLinkRequest(BaseModel): completed_activity_id: UUID


def _activity(row: CompletedActivity):
    duration = row.moving_time_s if row.moving_time_s is not None else row.elapsed_time_s
    return {"id": row.id, "name": row.name, "sport": row.sport, "started_at": row.start_at,
            "timezone": row.timezone, "duration_seconds": duration, "distance_meters": row.distance_m}


def _link(row: PlannedSessionActivityLink, activity: CompletedActivity):
    return {"id": row.id, "planned_training_session_id": row.planned_training_session_id,
            "completed_activity_id": row.completed_activity_id, "match_source": row.match_source,
            "match_confidence": row.match_confidence, "created_at": row.created_at,
            "activity": _activity(activity)}


def _raise(error: Exception):
    if isinstance(error, (SessionNotFoundError, ActivityNotFoundError)):
        raise HTTPException(404, detail={"code": error.code}) from None
    if isinstance(error, (LinkConflictError, AmbiguousMatchError, NoMatchError)):
        raise HTTPException(409, detail={"code": error.code}) from None
    raise error


@router.get("/{session_id}/activity-links")
def get_links(session_id: UUID, current: CurrentAthleteContext = Depends(read), session: Session = Depends(get_db_session)):
    app = PlannedSessionActivityMatching(session)
    try: app.session_for_athlete(current.athlete_id, session_id)
    except SessionNotFoundError as error: _raise(error)
    rows = session.execute(select(PlannedSessionActivityLink, CompletedActivity).join(CompletedActivity, CompletedActivity.id == PlannedSessionActivityLink.completed_activity_id).where(PlannedSessionActivityLink.athlete_profile_id == current.athlete_id, PlannedSessionActivityLink.planned_training_session_id == session_id).order_by(PlannedSessionActivityLink.created_at, PlannedSessionActivityLink.id)).all()
    return [_link(link, activity) for link, activity in rows]


@router.get("/{session_id}/activity-candidates")
def get_candidates(session_id: UUID, current: CurrentAthleteContext = Depends(read), session: Session = Depends(get_db_session)):
    app = PlannedSessionActivityMatching(session)
    try: planned = app.session_for_athlete(current.athlete_id, session_id)
    except SessionNotFoundError as error: _raise(error)
    return [{**_activity(item.activity), "local_date": item.local_date, "confidence": item.confidence,
             "evidence": list(item.evidence)} for item in app.find_candidates(current.athlete_id, planned)]


@router.post("/{session_id}/activity-links", status_code=status.HTTP_201_CREATED)
def manual_link(session_id: UUID, payload: ManualLinkRequest, current: CurrentAthleteContext = Depends(manage), session: Session = Depends(get_db_session)):
    app = PlannedSessionActivityMatching(session)
    try:
        row = app.create_link(current.athlete_id, session_id, payload.completed_activity_id, source="manual")
        session.commit(); activity = session.get(CompletedActivity, row.completed_activity_id); return _link(row, activity)
    except (SessionNotFoundError, ActivityNotFoundError, LinkConflictError) as error:
        session.rollback(); _raise(error)


@router.post("/{session_id}/auto-match")
def auto_match(session_id: UUID, current: CurrentAthleteContext = Depends(manage), session: Session = Depends(get_db_session)):
    app = PlannedSessionActivityMatching(session)
    try:
        evaluation, link = app.auto_match(current.athlete_id, session_id); session.commit()
        result = {"classification": evaluation.classification.value, "reason": evaluation.reason,
                  "candidates": [{**_activity(item.activity), "local_date": item.local_date, "confidence": item.confidence, "evidence": list(item.evidence)} for item in evaluation.candidates]}
        if link is not None: result["link"] = _link(link, session.get(CompletedActivity, link.completed_activity_id))
        else: result["link"] = None
        return result
    except (SessionNotFoundError, ActivityNotFoundError, LinkConflictError) as error:
        session.rollback(); _raise(error)


@router.delete("/{session_id}/activity-links/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink(session_id: UUID, activity_id: UUID, current: CurrentAthleteContext = Depends(manage), session: Session = Depends(get_db_session)):
    try:
        PlannedSessionActivityMatching(session).unlink(current.athlete_id, session_id, activity_id); session.commit(); return Response(status_code=204)
    except SessionNotFoundError as error:
        session.rollback(); _raise(error)
