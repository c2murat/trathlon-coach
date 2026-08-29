from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AthleteProfile, CompletedActivity, PlannedSessionActivityLink, PlannedTrainingSession

ALGORITHM_VERSION = "0.8g.1"
DATE_WINDOW_DAYS = 1
MAX_CANDIDATES = 5
HIGH_THRESHOLD = 0.85
MINIMUM_THRESHOLD = 0.55
MINIMUM_MARGIN = 0.12

PLANNED_TO_COMPLETED_SPORTS = {
    "run": frozenset({"running"}), "running": frozenset({"running"}),
    "bike": frozenset({"cycling"}), "cycling": frozenset({"cycling"}),
    "swim": frozenset({"swimming"}), "swimming": frozenset({"swimming"}),
    "strength": frozenset({"strength"}),
    # Multisport remains manually reviewable in 0.8G.1.
    "multisport": frozenset({"multisport"}),
}


class MatchClassification(str, Enum):
    CLEAR_MATCH = "clear_match"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class Candidate:
    activity: CompletedActivity
    local_date: date
    actual_duration_seconds: int
    score: float
    confidence: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class MatchEvaluation:
    classification: MatchClassification
    candidates: tuple[Candidate, ...]
    reason: str


class LinkError(ValueError): code = "activity_link_error"
class SessionNotFoundError(LinkError): code = "planned_training_session_not_found"
class ActivityNotFoundError(LinkError): code = "activity_not_found"
class LinkConflictError(LinkError): code = "activity_link_conflict"
class AmbiguousMatchError(LinkError): code = "ambiguous_activity_match"
class NoMatchError(LinkError): code = "no_activity_match"


def _local_date(activity: CompletedActivity) -> date:
    try: zone = ZoneInfo(activity.timezone)
    except (ZoneInfoNotFoundError, ValueError): zone = timezone.utc
    value = activity.start_at
    if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone).date()


def _duration(activity: CompletedActivity) -> int:
    return activity.moving_time_s if activity.moving_time_s is not None else activity.elapsed_time_s


def _score(planned: PlannedTrainingSession, activity: CompletedActivity) -> Candidate:
    local = _local_date(activity); delta = abs((local - planned.scheduled_date).days)
    evidence = ["sport_compatible"]
    score = 0.2 + (0.6 if delta == 0 else 0.3)
    evidence.append("same_local_date" if delta == 0 else "adjacent_local_date")
    actual = _duration(activity)
    if planned.planned_duration_seconds and actual >= 0:
        error = abs(actual - planned.planned_duration_seconds) / planned.planned_duration_seconds
        score += 0.15 * max(0.0, 1.0 - min(error, 1.0)); evidence.append(f"duration_error:{error:.3f}")
    if planned.sport != "strength" and planned.planned_distance_meters and activity.distance_m is not None:
        error = abs(activity.distance_m - planned.planned_distance_meters) / planned.planned_distance_meters
        score += 0.05 * max(0.0, 1.0 - min(error, 1.0)); evidence.append(f"distance_error:{error:.3f}")
    score = round(score, 4)
    confidence = "high" if score >= HIGH_THRESHOLD else "medium" if score >= MINIMUM_THRESHOLD else "low"
    return Candidate(activity, local, actual, score, confidence, tuple(evidence))


class PlannedSessionActivityMatching:
    def __init__(self, session: Session, *, today: date | None = None):
        self.session = session; self.today = today or datetime.now(timezone.utc).date()

    def session_for_athlete(self, athlete_id: UUID, session_id: UUID, *, lock: bool = False) -> PlannedTrainingSession:
        query = select(PlannedTrainingSession).where(PlannedTrainingSession.id == session_id, PlannedTrainingSession.athlete_profile_id == athlete_id)
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None: raise SessionNotFoundError()
        return row

    def find_candidates(self, athlete_id: UUID, planned: PlannedTrainingSession) -> tuple[Candidate, ...]:
        sports = PLANNED_TO_COMPLETED_SPORTS.get(planned.sport, frozenset())
        if not sports: return ()
        # Broad UTC bounds are narrowed with each activity's persisted timezone in Python.
        left = datetime.combine(planned.scheduled_date - timedelta(days=DATE_WINDOW_DAYS + 1), time.min, timezone.utc)
        right = datetime.combine(planned.scheduled_date + timedelta(days=DATE_WINDOW_DAYS + 2), time.min, timezone.utc)
        rows = self.session.scalars(select(CompletedActivity).where(
            CompletedActivity.athlete_id == athlete_id, CompletedActivity.sport.in_(sports),
            CompletedActivity.start_at >= left, CompletedActivity.start_at < right,
            CompletedActivity.deleted_at.is_(None), CompletedActivity.provider_deleted_at.is_(None),
        ).order_by(CompletedActivity.start_at, CompletedActivity.id)).all()
        candidates = [_score(planned, row) for row in rows if abs((_local_date(row) - planned.scheduled_date).days) <= DATE_WINDOW_DAYS]
        return tuple(sorted(candidates, key=lambda item: (-item.score, item.activity.start_at, str(item.activity.id)))[:MAX_CANDIDATES])

    def evaluate_match(self, athlete_id: UUID, planned: PlannedTrainingSession, candidates: tuple[Candidate, ...] | None = None) -> MatchEvaluation:
        items = candidates if candidates is not None else self.find_candidates(athlete_id, planned)
        if planned.scheduled_date > self.today: return MatchEvaluation(MatchClassification.NO_MATCH, items, "future_session")
        if not items or items[0].score < MINIMUM_THRESHOLD: return MatchEvaluation(MatchClassification.NO_MATCH, items, "threshold_not_met")
        existing = self.session.scalars(select(PlannedSessionActivityLink).where(or_(
            PlannedSessionActivityLink.planned_training_session_id == planned.id,
            PlannedSessionActivityLink.completed_activity_id.in_(tuple(item.activity.id for item in items)),
        ))).all()
        if existing: return MatchEvaluation(MatchClassification.AMBIGUOUS, items, "existing_link_conflict")
        relevant_sessions = self.session.scalars(select(PlannedTrainingSession).where(
            PlannedTrainingSession.athlete_profile_id == athlete_id, PlannedTrainingSession.id != planned.id,
            PlannedTrainingSession.scheduled_date >= planned.scheduled_date - timedelta(days=DATE_WINDOW_DAYS),
            PlannedTrainingSession.scheduled_date <= planned.scheduled_date + timedelta(days=DATE_WINDOW_DAYS),
            PlannedTrainingSession.sport == planned.sport,
        ).limit(1)).first()
        if relevant_sessions is not None: return MatchEvaluation(MatchClassification.AMBIGUOUS, items, "another_relevant_session")
        second = items[1].score if len(items) > 1 else 0.0
        if items[0].score < HIGH_THRESHOLD: return MatchEvaluation(MatchClassification.AMBIGUOUS, items, "high_threshold_not_met")
        if len(items) > 1 and items[0].score - second < MINIMUM_MARGIN: return MatchEvaluation(MatchClassification.AMBIGUOUS, items, "insufficient_margin")
        return MatchEvaluation(MatchClassification.CLEAR_MATCH, items, "clear_1_to_1_match")

    def _lock_athlete(self, athlete_id: UUID) -> None:
        if self.session.scalar(select(AthleteProfile.id).where(AthleteProfile.id == athlete_id).with_for_update()) is None:
            raise SessionNotFoundError()

    def create_link(self, athlete_id: UUID, session_id: UUID, activity_id: UUID, *, source: str, confidence: str = "high") -> PlannedSessionActivityLink:
        self._lock_athlete(athlete_id)
        planned = self.session_for_athlete(athlete_id, session_id, lock=True)
        activity = self.session.scalar(select(CompletedActivity).where(CompletedActivity.id == activity_id, CompletedActivity.athlete_id == athlete_id, CompletedActivity.deleted_at.is_(None), CompletedActivity.provider_deleted_at.is_(None)).with_for_update())
        if activity is None: raise ActivityNotFoundError()
        existing = self.session.scalar(select(PlannedSessionActivityLink).where(PlannedSessionActivityLink.planned_training_session_id == session_id, PlannedSessionActivityLink.completed_activity_id == activity_id))
        if existing:
            if source == "manual" and existing.match_source == "automatic":
                existing.match_source = "manual"
                existing.match_confidence = confidence
                existing.algorithm_version = None
                self.session.flush()
                return existing
            if source == "automatic" or existing.match_source == source: return existing
            raise LinkConflictError()
        if source == "automatic":
            evaluation = self.evaluate_match(athlete_id, planned)
            if evaluation.classification is MatchClassification.AMBIGUOUS: raise AmbiguousMatchError()
            if evaluation.classification is MatchClassification.NO_MATCH or evaluation.candidates[0].activity.id != activity_id: raise NoMatchError()
        link = PlannedSessionActivityLink(athlete_profile_id=athlete_id, planned_training_session_id=session_id, completed_activity_id=activity_id, match_source=source, match_confidence=confidence, algorithm_version=ALGORITHM_VERSION if source == "automatic" else None)
        self.session.add(link)
        try: self.session.flush()
        except IntegrityError: raise LinkConflictError() from None
        return link

    def auto_match(self, athlete_id: UUID, session_id: UUID) -> tuple[MatchEvaluation, PlannedSessionActivityLink | None]:
        self._lock_athlete(athlete_id); planned = self.session_for_athlete(athlete_id, session_id, lock=True)
        same = self.session.scalars(select(PlannedSessionActivityLink).where(PlannedSessionActivityLink.planned_training_session_id == session_id)).all()
        if same:
            if len(same) == 1:
                return MatchEvaluation(MatchClassification.CLEAR_MATCH, (), f"existing_{same[0].match_source}_link"), same[0]
            return MatchEvaluation(MatchClassification.AMBIGUOUS, (), "existing_link_conflict"), None
        evaluation = self.evaluate_match(athlete_id, planned)
        if evaluation.classification is not MatchClassification.CLEAR_MATCH: return evaluation, None
        return evaluation, self.create_link(athlete_id, session_id, evaluation.candidates[0].activity.id, source="automatic")

    def unlink(self, athlete_id: UUID, session_id: UUID, activity_id: UUID) -> None:
        self._lock_athlete(athlete_id); self.session_for_athlete(athlete_id, session_id, lock=True)
        row = self.session.scalar(select(PlannedSessionActivityLink).where(PlannedSessionActivityLink.athlete_profile_id == athlete_id, PlannedSessionActivityLink.planned_training_session_id == session_id, PlannedSessionActivityLink.completed_activity_id == activity_id).with_for_update())
        if row is not None: self.session.delete(row); self.session.flush()
