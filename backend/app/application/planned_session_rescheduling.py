from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AthleteProfile,
    ManualStrengthSession,
    PlannedSessionManualStrengthLink,
    PlannedSessionScheduleChange,
    PlannedTrainingSession,
    TrainingPlan,
)


class SessionRescheduleError(ValueError):
    code = "session_reschedule_error"


class SessionRescheduleNotFoundError(SessionRescheduleError):
    code = "planned_training_session_not_found"


class SessionReschedulePlanNotEditableError(SessionRescheduleError):
    code = "training_plan_not_editable"


class SessionRescheduleOutsideWeekError(SessionRescheduleError):
    code = "new_date_outside_session_week"


class ManualStrengthLinkNotFoundError(SessionRescheduleError):
    code = "manual_strength_session_not_found"


class ManualStrengthLinkInvalidError(SessionRescheduleError):
    code = "manual_strength_link_invalid"


def _week_start(value: date) -> date:
    return date.fromordinal(value.toordinal() - value.weekday())


def _manual_local_date(row: ManualStrengthSession) -> date:
    value = row.started_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(row.timezone_name)).date()


class PlannedSessionRescheduling:
    def __init__(self, session: Session):
        self.session = session

    def _session_and_plan(self, *, athlete_id: UUID, session_id: UUID, lock: bool = False):
        query = (
            select(PlannedTrainingSession, TrainingPlan)
            .join(TrainingPlan, TrainingPlan.id == PlannedTrainingSession.training_plan_id)
            .where(
                PlannedTrainingSession.id == session_id,
                PlannedTrainingSession.athlete_profile_id == athlete_id,
                TrainingPlan.athlete_profile_id == athlete_id,
            )
        )
        row = self.session.execute(query.with_for_update() if lock else query).first()
        if row is None:
            raise SessionRescheduleNotFoundError()
        return row

    def reschedule(self, *, athlete_id: UUID, session_id: UUID, new_date: date, user_id: UUID, reason: str | None = None) -> PlannedTrainingSession:
        athlete = self.session.scalar(select(AthleteProfile).where(AthleteProfile.id == athlete_id).with_for_update())
        if athlete is None:
            raise SessionRescheduleNotFoundError()
        planned, plan = self._session_and_plan(athlete_id=athlete_id, session_id=session_id, lock=True)
        if plan.status not in {"draft", "active"}:
            raise SessionReschedulePlanNotEditableError()
        if _week_start(planned.scheduled_date) != _week_start(new_date):
            raise SessionRescheduleOutsideWeekError()
        if planned.scheduled_date == new_date:
            return planned
        previous = planned.scheduled_date
        planned.scheduled_date = new_date
        self.session.add(PlannedSessionScheduleChange(
            athlete_profile_id=athlete_id,
            planned_training_session_id=planned.id,
            training_plan_id=plan.id,
            previous_scheduled_date=previous,
            new_scheduled_date=new_date,
            changed_by_user_id=user_id,
            changed_at=datetime.now(timezone.utc),
            reason=reason,
        ))
        self.session.flush()
        return planned

    def link_manual_strength(self, *, athlete_id: UUID, session_id: UUID, manual_strength_session_id: UUID, user_id: UUID) -> PlannedSessionManualStrengthLink:
        planned, plan = self._session_and_plan(athlete_id=athlete_id, session_id=session_id, lock=True)
        if planned.sport != "strength":
            raise ManualStrengthLinkInvalidError()
        manual = self.session.scalar(select(ManualStrengthSession).where(
            ManualStrengthSession.id == manual_strength_session_id,
            ManualStrengthSession.athlete_id == athlete_id,
        ).with_for_update())
        if manual is None:
            raise ManualStrengthLinkNotFoundError()
        if _week_start(planned.scheduled_date) != _week_start(_manual_local_date(manual)):
            raise ManualStrengthLinkInvalidError()
        existing = self.session.scalar(select(PlannedSessionManualStrengthLink).where(
            PlannedSessionManualStrengthLink.planned_training_session_id == session_id,
            PlannedSessionManualStrengthLink.manual_strength_session_id == manual_strength_session_id,
        ))
        if existing is not None:
            return existing
        link = PlannedSessionManualStrengthLink(
            athlete_profile_id=athlete_id,
            planned_training_session_id=session_id,
            manual_strength_session_id=manual_strength_session_id,
            match_source="manual",
            match_confidence="high",
            created_by_user_id=user_id,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(link)
        self.session.flush()
        return link
