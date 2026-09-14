"""Audit the real C.1 -> C.6 -> C.5 -> C.4 path without persisting a preview."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import event, select, text

from app.application.execution_evidence import PrescribedCompletedEvidenceAssembler
from app.application.planning_context import PlanningContextAssembler
from app.db.models import AthleteProfile, CompetitionGoal
from app.db.session import SessionLocal
from app.domains.planning.contracts import PlanningRequest
from app.domains.planning.execution_adaptation import build_execution_adaptation_context
from app.domains.planning.execution_proposals import build_execution_adaptation_proposal_context
from app.domains.planning.numeric_adaptation import resolve_numeric_adaptations
from app.domains.planning.prescription_intensity import PRESCRIPTION_INTENSITY_LEVEL_VERSION, build_prescription_intensity_ladder, TARGET_SEMANTICS
from app.domains.planning.planning_adaptation import normalize_numeric_planning_adaptation
from app.domains.planning.season_structure import SeasonStructureBuilder, SeasonStructureConfig
from app.domains.planning.session_planning import SessionPlanningConfig, build_session_plan
from app.domains.planning.weekly_budget import WeeklyBudgetConfig, build_weekly_budget_plan
from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
from scripts.audit_multi_athlete_integrity import audit


def validate(cutoff):
    report = {"cutoff": cutoff.isoformat(), "window_start": (cutoff - timedelta(days=84)).isoformat(),
              "numeric_policy_version": "0.8G.2C.5",
              "prescription_intensity_level_version": PRESCRIPTION_INTENSITY_LEVEL_VERSION, "athletes": []}
    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
            assert db.scalar(text("SHOW transaction_read_only")) == "on"
            athletes = db.scalars(select(AthleteProfile).where(AthleteProfile.deleted_at.is_(None)).order_by(AthleteProfile.id)).all()
            for athlete in athletes:
                queries = []

                def count(*args):
                    queries.append(1)

                event.listen(db.bind, "before_cursor_execute", count)
                try:
                    evidence = PrescribedCompletedEvidenceAssembler(db).assemble(athlete_profile_id=athlete.id, as_of_date=cutoff)
                    c1_queries = len(queries)
                    signals = build_execution_adaptation_context(evidence)
                    proposals = build_execution_adaptation_proposal_context(signals)
                    assert len(queries) == c1_queries <= 3
                finally:
                    event.remove(db.bind, "before_cursor_execute", count)
                row = {"athlete_id": str(athlete.id), "c1_sessions": len(evidence.sessions), "c1_queries": c1_queries,
                       "c2_signals": len(signals.sport_signals) + len(signals.session_type_signals) + len(signals.structured_target_signals),
                       "c2_global_signal": signals.global_signal.signal.value,
                       "c3_proposals": len(proposals.proposals),
                       "c3_directional": sum(p.proposal_kind.value in {"INCREASE_TARGET", "DECREASE_TARGET"} for p in proposals.proposals),
                       "c5_resolutions": 0, "RESOLVED": 0, "NO_SAFE_STEP": 0, "NOT_APPLICABLE": 0,
                       "GUARDED": 0, "UNSUPPORTED": 0, "CONFLICT": 0, "c4_APPLIED": 0, "targets": []}
                row.update(c6_catalog_attempts=0, c6_ladders=0, c6_current_levels=0, c6_adjacent_levels=0,
                           c6_no_supported_ladder=0, c6_resolutions=0)
                goals = db.scalars(select(CompetitionGoal).where(
                    CompetitionGoal.athlete_profile_id == athlete.id, CompetitionGoal.status == "active",
                    CompetitionGoal.event_date >= cutoff,
                ).order_by(CompetitionGoal.id)).all()
                if goals:
                    request = PlanningRequest(athlete_id=athlete.id, planning_date=cutoff, start_date=cutoff,
                                              timezone_name=athlete.timezone, goal_ids=tuple(goal.id for goal in goals),
                                              algorithm_version="0.8F.9", configuration_version="0.8F.9")
                    context = PlanningContextAssembler(db, training_load_algorithm_version="0.7b.1",
                                                       load_aggregation_algorithm_version="0.7c.1", manual_strength_algorithm_version="0.7e.1",
                                                       training_status_algorithm_version="0.7f.1").assemble(request, include_capability=True)
                    season = SeasonStructureBuilder(SeasonStructureConfig(version="0.8F.3", algorithm_version="0.8F.3")).build(context)
                    if any(warning.blocking for warning in season.warnings):
                        row["planning"] = "BLOCKED_SEASON"
                    else:
                        budgets = build_weekly_budget_plan(context, season, WeeklyBudgetConfig(version="0.8F.4", algorithm_version="0.8F.4"))
                        plan = build_session_plan(context, season, budgets, SessionPlanningConfig(version="0.8F.9", algorithm_version="0.8F.9"))
                        sessions = tuple(item for week in plan.weeks for item in week.sessions)
                        config = WorkoutBuilderConfig(version="0.8F.9", algorithm_version="0.8F.9")
                        drafts = tuple(build_structured_workout(context, item, config) for item in sessions)
                        event.listen(db.bind, "before_cursor_execute", count)
                        query_start = len(queries)
                        try:
                            keys = sorted({(item.discipline, item.session_type.value) for item in sessions
                                           if item.discipline in TARGET_SEMANTICS})
                            catalogs = [build_prescription_intensity_ladder(context=context, sport=sport,
                                        session_type=kind, target_kind=TARGET_SEMANTICS[sport][0]) for sport, kind in keys]
                            row["c6_catalog_attempts"] = len(catalogs)
                            row["c6_ladders"] = sum(item.ladder is not None for item in catalogs)
                            row["c6_no_supported_ladder"] = sum(item.status == "NO_SUPPORTED_LADDER" for item in catalogs)
                            numeric = resolve_numeric_adaptations(proposals=proposals, context=context, prescriptions=sessions, drafts=drafts)
                            projection = normalize_numeric_planning_adaptation(numeric)
                            assert len(queries) == query_start
                        finally:
                            event.remove(db.bind, "before_cursor_execute", count)
                        row["planning"] = "BUILT_IN_MEMORY"
                        row["c5_resolutions"] = len(numeric.resolutions)
                        levels = [item.level_resolution for item in numeric.resolutions if item.level_resolution is not None]
                        row["c6_resolutions"] = len(levels)
                        row["c6_current_levels"] = sum(item.level_before is not None for item in levels)
                        row["c6_adjacent_levels"] = sum(item.level_after is not None for item in levels)
                        row.update(Counter(item.status.value for item in numeric.resolutions))
                        # No step provider exists in this audited numeric policy.
                        assert projection.planning_input is None
                        row["targets"] = [dict(sport=item.sport, session_type=item.session_type,
                                               before=item.current_range.model_dump(mode="json") if item.current_range else None,
                                               proposed=None, after=item.current_range.model_dump(mode="json") if item.current_range else None)
                                          for item in numeric.resolutions]
                else:
                    row["planning"] = "NO_FUTURE_GOALS_NO_SYNTHETIC_CONTEXT"
                report["athletes"].append(row)
            integrity = audit(db)
            report["multiathlete_integrity"] = {"issue_count": integrity["issue_count"],
                                              "checks": {key: len(value) for key, value in integrity["checks"].items()}}
        finally:
            db.rollback()
    report["rollback"] = True
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    print(json.dumps(validate(parser.parse_args().cutoff), sort_keys=True, indent=2))
