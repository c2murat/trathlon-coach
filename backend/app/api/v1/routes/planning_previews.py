from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.athlete_permissions import AthleteCapability, require_athlete_capability
from app.api.dependencies.current_athlete import CurrentAthleteContext
from app.api.v1.schemas.planning_previews import (
    PlanningPreviewAccept, PlanningPreviewCreate, PlanningPreviewResponse,
    TrainingPlanAcceptedResponse,
)
from app.application.planning_preview import (
    PlanningPreviewApplication, PlanningPreviewAthleteMismatchError,
    PlanningPreviewBlockedError, PlanningPreviewFingerprintMismatchError,
    PlanningPreviewGoalInvalidError, PlanningPreviewNotFoundError,
    TrainingPlanOverlapError, VISIBLE_TRAINING_PLAN_STATUSES,
)
from app.db.session import get_db_session
from app.db.models import PlannedTrainingSession, StructuredWorkout, TrainingPlan, TrainingPlanGoal
from app.domains.planning.contracts import PlanningRequest


router = APIRouter(prefix="/planning/previews", tags=["planning-previews"])
training_plans_router = APIRouter(prefix="/training-plans", tags=["training-plans"])
read = require_athlete_capability(AthleteCapability.READ_TRAINING_PLANNING)
generate = require_athlete_capability(AthleteCapability.GENERATE_TRAINING_PLAN)


def _response(app: PlanningPreviewApplication, row) -> PlanningPreviewResponse:
    accepted_plan = row.accepted_training_plan
    return PlanningPreviewResponse(
        id=row.id, status=row.status, created_at=row.created_at,
        accepted_at=row.accepted_at,
        accepted_training_plan_id=accepted_plan.id if accepted_plan is not None else None,
        artifact=app.artifact(row),
    )


def _raise(error: Exception):
    if isinstance(error, PlanningPreviewNotFoundError):
        raise HTTPException(status_code=404, detail={"code": error.code}) from None
    if isinstance(error, PlanningPreviewAthleteMismatchError):
        raise HTTPException(status_code=403, detail={"code": error.code}) from None
    if isinstance(error, PlanningPreviewFingerprintMismatchError):
        raise HTTPException(status_code=409, detail={"code": error.code}) from None
    if isinstance(error, TrainingPlanOverlapError):
        raise HTTPException(status_code=409, detail={
            "code": error.code,
            "existing_training_plan_id": str(error.existing_training_plan_id),
            "existing_start_date": error.existing_start_date.isoformat(),
            "existing_end_date": error.existing_end_date.isoformat(),
        }) from None
    code = getattr(error, "code", "planning_preview_invalid")
    raise HTTPException(status_code=422, detail={"code": code}) from None


@router.post("", response_model=PlanningPreviewResponse, status_code=status.HTTP_201_CREATED)
def create_preview(payload: PlanningPreviewCreate, current: CurrentAthleteContext = Depends(generate), session: Session = Depends(get_db_session)):
    app = PlanningPreviewApplication(session)
    try:
        request = PlanningRequest(
            athlete_id=current.athlete_id, planning_date=payload.planning_date,
            timezone_name=current.athlete_profile.timezone, goal_ids=payload.goal_ids,
            start_date=payload.start_date, horizon_end_date=payload.horizon_end_date,
            preferences=payload.preferences, algorithm_version="0.8F.6",
            configuration_version="0.8F.6",
        )
        return _response(app, app.generate(request=request, user_id=current.user_id))
    except (ValueError, ValidationError, PlanningPreviewBlockedError) as error:
        session.rollback()
        _raise(error)


@router.get("/{preview_id}", response_model=PlanningPreviewResponse)
def get_preview(preview_id: UUID, current: CurrentAthleteContext = Depends(read), session: Session = Depends(get_db_session)):
    app = PlanningPreviewApplication(session)
    try:
        return _response(app, app.get(preview_id=preview_id, athlete_id=current.athlete_id))
    except (PlanningPreviewNotFoundError, PlanningPreviewAthleteMismatchError, PlanningPreviewFingerprintMismatchError) as error:
        _raise(error)


@router.post("/{preview_id}/accept", response_model=TrainingPlanAcceptedResponse)
def accept_preview(preview_id: UUID, payload: PlanningPreviewAccept, current: CurrentAthleteContext = Depends(generate), session: Session = Depends(get_db_session)):
    try:
        plan = PlanningPreviewApplication(session).accept(
            preview_id=preview_id, athlete_id=current.athlete_id,
            user_id=current.user_id, role=current.role,
            expected_fingerprint=payload.expected_fingerprint,
        )
        return TrainingPlanAcceptedResponse(training_plan_id=plan.id, preview_id=preview_id, status=plan.status)
    except (PlanningPreviewNotFoundError, PlanningPreviewAthleteMismatchError, PlanningPreviewFingerprintMismatchError, PlanningPreviewGoalInvalidError, TrainingPlanOverlapError) as error:
        _raise(error)


@training_plans_router.get("/sessions")
def list_planned_training_sessions(start_date: date, end_date: date, current: CurrentAthleteContext = Depends(read), session: Session = Depends(get_db_session)):
    if end_date < start_date:
        raise HTTPException(status_code=422, detail={"code": "invalid_date_range"})
    rows = session.scalars(
        select(PlannedTrainingSession)
        .join(TrainingPlan, TrainingPlan.id == PlannedTrainingSession.training_plan_id)
        .where(
            TrainingPlan.athlete_profile_id == current.athlete_id,
            TrainingPlan.status.in_(VISIBLE_TRAINING_PLAN_STATUSES),
            PlannedTrainingSession.scheduled_date >= start_date,
            PlannedTrainingSession.scheduled_date <= end_date,
        )
        .order_by(PlannedTrainingSession.scheduled_date, PlannedTrainingSession.id)
    ).all()
    workout_rows = session.scalars(select(StructuredWorkout).where(StructuredWorkout.planned_training_session_id.in_(tuple(item.id for item in rows)))).all() if rows else ()
    workouts = {item.planned_training_session_id: item for item in workout_rows}
    return [{
        "id": item.id, "scheduled_date": item.scheduled_date, "sport": item.sport,
        "title": item.title, "description": item.description,
        "planned_duration_seconds": item.planned_duration_seconds,
        "workout": workouts[item.id].definition if item.id in workouts else None,
    } for item in rows]


@training_plans_router.get("/{plan_id}")
def get_training_plan(plan_id: UUID, current: CurrentAthleteContext = Depends(read), session: Session = Depends(get_db_session)):
    plan = session.get(TrainingPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "training_plan_not_found"})
    if plan.athlete_profile_id != current.athlete_id:
        raise HTTPException(status_code=403, detail={"code": "training_plan_athlete_mismatch"})
    goals = session.scalars(select(TrainingPlanGoal).where(TrainingPlanGoal.training_plan_id == plan.id).order_by(TrainingPlanGoal.competition_goal_id)).all()
    planned = session.scalars(select(PlannedTrainingSession).where(PlannedTrainingSession.training_plan_id == plan.id).order_by(PlannedTrainingSession.scheduled_date, PlannedTrainingSession.id)).all()
    workout_rows = session.scalars(select(StructuredWorkout).where(StructuredWorkout.planned_training_session_id.in_(tuple(item.id for item in planned)))).all() if planned else ()
    workouts = {item.planned_training_session_id: item for item in workout_rows}
    return {
        "id": plan.id, "athlete_profile_id": plan.athlete_profile_id,
        "title": plan.title, "start_date": plan.start_date, "end_date": plan.end_date,
        "status": plan.status, "origin": plan.origin,
        "algorithm_version": plan.algorithm_version,
        "goals": [{"competition_goal_id": item.competition_goal_id, "relationship": item.relationship} for item in goals],
        "sessions": [{
            "id": item.id, "scheduled_date": item.scheduled_date, "sport": item.sport,
            "title": item.title, "description": item.description,
            "planned_duration_seconds": item.planned_duration_seconds,
            "workout": workouts[item.id].definition if item.id in workouts else None,
        } for item in planned],
    }
