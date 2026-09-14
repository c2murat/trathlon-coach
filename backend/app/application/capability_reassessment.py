"""On-demand C.7 assembly; no persistence and no Planning integration."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import literal, select, true
from sqlalchemy.orm import aliased

from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.db.models import AthletePerformanceProfileVersion, PlannedTrainingSession, StructuredWorkout
from app.domains.capability.models import AthleteCapabilityContext
from app.domains.capability.reassessment import (
    CapabilityTargetSnapshot, ReassessmentReferences, WINDOW_DAYS,
    build_capability_reassessment_context, snapshot_capability_target,
)
from app.domains.planning.contracts import PerformanceSnapshot


class CapabilityReassessmentAssembler:
    def __init__(self, session):
        self.session = session

    def assemble(self, *, athlete_profile_id, as_of_date: date, evidence=None, adaptation=None,
                 capability: AthleteCapabilityContext | ReassessmentReferences | None = None,
                 targets: tuple[CapabilityTargetSnapshot, ...] | None = None):
        for item in (evidence, adaptation, capability):
            if item is not None and (item.athlete_profile_id != athlete_profile_id or item.as_of_date != as_of_date):
                raise ValueError("capability reassessment athlete/cutoff mismatch")
        # SELECTs must not flush unrelated caller-owned pending changes.
        with self.session.no_autoflush:
            if evidence is None:
                evidence = PrescribedCompletedEvidenceAssembler(self.session).assemble(
                    athlete_profile_id=athlete_profile_id, as_of_date=as_of_date)
            if capability is None:
                references, loaded_targets = self._inputs(athlete_profile_id, as_of_date)
                if targets is None:
                    targets = loaded_targets
            elif isinstance(capability, AthleteCapabilityContext):
                references = ReassessmentReferences(athlete_profile_id=capability.athlete_profile_id,
                    as_of_date=capability.as_of_date, performance=capability.performance_references)
            else:
                references = capability
            return build_capability_reassessment_context(
                athlete_profile_id=athlete_profile_id, as_of_date=as_of_date,
                evidence=evidence, adaptation=adaptation, references=references, targets=targets or ())

    def _inputs(self, athlete_profile_id, as_of_date):
        """One statement for current profile plus missing C.1 target provenance.

        Singleton left joins preserve missing-profile and zero-session cases.
        No per-session lookup, activity query, or lap reconstruction.
        """
        profile_query = select(AthletePerformanceProfileVersion).where(
            AthletePerformanceProfileVersion.athlete_profile_id == athlete_profile_id,
            AthletePerformanceProfileVersion.effective_from < datetime.combine(as_of_date, time.min, timezone.utc),
        ).order_by(AthletePerformanceProfileVersion.effective_from.desc(),
                   AthletePerformanceProfileVersion.id.desc()).limit(1).subquery()
        profile = aliased(AthletePerformanceProfileVersion, profile_query)
        singleton = select(literal(1).label("singleton")).subquery()
        statement = select(profile, PlannedTrainingSession, StructuredWorkout).select_from(singleton).outerjoin(
            profile, true()).outerjoin(PlannedTrainingSession,
                (PlannedTrainingSession.athlete_profile_id == athlete_profile_id)
                & (PlannedTrainingSession.scheduled_date >= as_of_date - timedelta(days=WINDOW_DAYS))
                & (PlannedTrainingSession.scheduled_date < as_of_date)
            ).outerjoin(StructuredWorkout,
                StructuredWorkout.planned_training_session_id == PlannedTrainingSession.id
            ).order_by(PlannedTrainingSession.id)
        rows = self.session.execute(statement).all()
        current = rows[0][0]
        values = {} if current is None else {
            "profile_version_id": current.id, "effective_from": current.effective_from,
            "source": current.data_origin, "algorithm_version": current.algorithm_version,
            "cycling_ftp_watts": current.cycling_ftp_watts,
            "running_threshold_pace_seconds_per_km": current.running_threshold_pace_seconds_per_km,
            "swimming_css_seconds_per_100m": current.swimming_css_seconds_per_100m,
        }
        targets = []
        for _, planned, workout in rows:
            if planned is None or workout is None:
                continue
            target = snapshot_capability_target(athlete_profile_id=athlete_profile_id,
                planned_session_id=planned.id, planned_date=planned.scheduled_date,
                sport=planned.sport, session_type=planned.title, workout=workout.parsed_definition())
            if target is not None:
                targets.append(target)
        return ReassessmentReferences(athlete_profile_id=athlete_profile_id, as_of_date=as_of_date,
                                      performance=PerformanceSnapshot(**values)), tuple(targets)
