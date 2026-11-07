from datetime import datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

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
from app.application.planned_session_rescheduling import (
    ManualStrengthLinkInvalidError, ManualStrengthLinkNotFoundError,
    PlannedSessionRescheduling, SessionRescheduleNotFoundError,
    SessionRescheduleOutsideWeekError, SessionReschedulePlanNotEditableError,
)
from app.db.models import CompletedActivity, ManualStrengthSession, PlannedSessionActivityLink, PlannedSessionManualStrengthLink
from app.db.session import get_db_session

router = APIRouter(prefix="/training-plans/sessions", tags=["planned-session-activity-links"])
read = require_athlete_capability(AthleteCapability.READ_TRAINING_PLANNING)
manage = require_athlete_capability(AthleteCapability.GENERATE_TRAINING_PLAN)


class ManualLinkRequest(BaseModel): completed_activity_id: UUID
class ManualStrengthLinkRequest(BaseModel): manual_strength_session_id: UUID
class RescheduleRequest(BaseModel):
    scheduled_date: datetime | None = None
    date: str | None = None


def _activity(row: CompletedActivity):
    duration = row.moving_time_s if row.moving_time_s is not None else row.elapsed_time_s
    return {"id": row.id, "name": row.name, "sport": row.sport, "started_at": row.start_at,
            "timezone": row.timezone, "duration_seconds": duration, "distance_meters": row.distance_m}


def _manual_strength_activity(row: ManualStrengthSession):
    return {"id": row.id, "name": "Fuerza manual", "sport": "strength", "started_at": row.started_at,
            "timezone": row.timezone_name, "duration_seconds": row.duration_minutes * 60, "distance_meters": None,
            "source_type": "manual_strength"}


def _link(row: PlannedSessionActivityLink, activity: CompletedActivity):
    return {"id": row.id, "planned_training_session_id": row.planned_training_session_id,
            "completed_activity_id": row.completed_activity_id, "match_source": row.match_source,
            "match_confidence": row.match_confidence, "created_at": row.created_at,
            "activity": _activity(activity)}


def _manual_strength_link(row: PlannedSessionManualStrengthLink, manual: ManualStrengthSession):
    return {"id": row.id, "planned_training_session_id": row.planned_training_session_id,
            "completed_activity_id": None, "manual_strength_session_id": row.manual_strength_session_id,
            "match_source": row.match_source, "match_confidence": row.match_confidence,
            "created_at": row.created_at, "activity": _manual_strength_activity(manual)}


def _raise(error: Exception):
    if isinstance(error, (SessionNotFoundError, ActivityNotFoundError)):
        raise HTTPException(404, detail={"code": error.code}) from None
    if isinstance(error, (SessionRescheduleNotFoundError, ManualStrengthLinkNotFoundError)):
        raise HTTPException(404, detail={"code": error.code}) from None
    if isinstance(error, (LinkConflictError, AmbiguousMatchError, NoMatchError)):
        raise HTTPException(409, detail={"code": error.code}) from None
    if isinstance(error, (SessionReschedulePlanNotEditableError, SessionRescheduleOutsideWeekError, ManualStrengthLinkInvalidError)):
        raise HTTPException(409, detail={"code": error.code}) from None
    raise error


def _week_bounds(day):
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=7)


def _local_date(value: datetime, timezone_name: str):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(timezone_name)).date()


@router.get("/{session_id}/activity-links")
def get_links(session_id: UUID, current: CurrentAthleteContext = Depends(read), session: Session = Depends(get_db_session)):
    app = PlannedSessionActivityMatching(session)
    try: app.session_for_athlete(current.athlete_id, session_id)
    except SessionNotFoundError as error: _raise(error)
    rows = session.execute(select(PlannedSessionActivityLink, CompletedActivity).join(CompletedActivity, CompletedActivity.id == PlannedSessionActivityLink.completed_activity_id).where(PlannedSessionActivityLink.athlete_profile_id == current.athlete_id, PlannedSessionActivityLink.planned_training_session_id == session_id).order_by(PlannedSessionActivityLink.created_at, PlannedSessionActivityLink.id)).all()
    manual_rows = session.execute(select(PlannedSessionManualStrengthLink, ManualStrengthSession).join(ManualStrengthSession, ManualStrengthSession.id == PlannedSessionManualStrengthLink.manual_strength_session_id).where(PlannedSessionManualStrengthLink.athlete_profile_id == current.athlete_id, PlannedSessionManualStrengthLink.planned_training_session_id == session_id).order_by(PlannedSessionManualStrengthLink.created_at, PlannedSessionManualStrengthLink.id)).all()
    return [_link(link, activity) for link, activity in rows] + [_manual_strength_link(link, manual) for link, manual in manual_rows]


@router.get("/{session_id}/activity-candidates")
def get_candidates(session_id: UUID, current: CurrentAthleteContext = Depends(read), session: Session = Depends(get_db_session)):
    app = PlannedSessionActivityMatching(session)
    try: planned = app.session_for_athlete(current.athlete_id, session_id)
    except SessionNotFoundError as error: _raise(error)
    candidates = [{**_activity(item.activity), "source_type": "completed_activity", "local_date": item.local_date, "confidence": item.confidence,
             "evidence": list(item.evidence)} for item in app.find_candidates(current.athlete_id, planned)]
    start, end = _week_bounds(planned.scheduled_date)
    left = datetime.combine(start - timedelta(days=1), time.min, timezone.utc)
    right = datetime.combine(end + timedelta(days=1), time.min, timezone.utc)
    if planned.sport == "strength":
        rows = session.scalars(select(ManualStrengthSession).where(
            ManualStrengthSession.athlete_id == current.athlete_id,
            ManualStrengthSession.started_at >= left,
            ManualStrengthSession.started_at < right,
        ).order_by(ManualStrengthSession.started_at, ManualStrengthSession.id)).all()
        for row in rows:
            local = _local_date(row.started_at, row.timezone_name)
            if start <= local < end:
                candidates.append({**_manual_strength_activity(row), "local_date": local, "confidence": "high", "evidence": ["same_week_manual_strength"]})
    return candidates


@router.post("/{session_id}/activity-links", status_code=status.HTTP_201_CREATED)
def manual_link(session_id: UUID, payload: ManualLinkRequest, current: CurrentAthleteContext = Depends(manage), session: Session = Depends(get_db_session)):
    app = PlannedSessionActivityMatching(session)
    try:
        row = app.create_link(current.athlete_id, session_id, payload.completed_activity_id, source="manual")
        session.commit(); activity = session.get(CompletedActivity, row.completed_activity_id); return _link(row, activity)
    except (SessionNotFoundError, ActivityNotFoundError, LinkConflictError) as error:
        session.rollback(); _raise(error)


@router.post("/{session_id}/manual-strength-links", status_code=status.HTTP_201_CREATED)
def manual_strength_link(session_id: UUID, payload: ManualStrengthLinkRequest, current: CurrentAthleteContext = Depends(manage), session: Session = Depends(get_db_session)):
    try:
        row = PlannedSessionRescheduling(session).link_manual_strength(
            athlete_id=current.athlete_id, session_id=session_id,
            manual_strength_session_id=payload.manual_strength_session_id,
            user_id=current.user_id,
        )
        session.commit()
        manual = session.get(ManualStrengthSession, row.manual_strength_session_id)
        return _manual_strength_link(row, manual)
    except (SessionRescheduleNotFoundError, ManualStrengthLinkNotFoundError, ManualStrengthLinkInvalidError) as error:
        session.rollback(); _raise(error)


@router.post("/{session_id}/reschedule")
def reschedule_session(session_id: UUID, payload: RescheduleRequest, current: CurrentAthleteContext = Depends(manage), session: Session = Depends(get_db_session)):
    try:
        if payload.scheduled_date is not None:
            new_date = payload.scheduled_date.date()
        elif payload.date is not None:
            from datetime import date as date_type
            new_date = date_type.fromisoformat(payload.date)
        else:
            raise HTTPException(422, detail={"code": "scheduled_date_required"})
        row = PlannedSessionRescheduling(session).reschedule(
            athlete_id=current.athlete_id, session_id=session_id,
            new_date=new_date, user_id=current.user_id,
        )
        session.commit()
        return {"id": row.id, "scheduled_date": row.scheduled_date}
    except ValueError as error:
        session.rollback()
        if isinstance(error, (SessionRescheduleNotFoundError, SessionReschedulePlanNotEditableError, SessionRescheduleOutsideWeekError)):
            _raise(error)
        raise HTTPException(422, detail={"code": "invalid_scheduled_date"}) from None


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
