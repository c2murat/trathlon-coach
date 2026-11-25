"""Read-only athlete audit, with an isolated pre-change planner byte comparison.

Only writes local audit files. Does not call generate/accept, migrate or change
preferences. Worker processes consume one frozen context/proposal snapshot.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "informe"
sys.path.insert(0, str(ROOT / "backend"))


class LegacyPlannerLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, source):
        self.source = source

    def find_spec(self, fullname, path, target=None):
        if fullname == "app.domains.planning.session_planning":
            return importlib.util.spec_from_loader(fullname, self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = str(ROOT / "backend/app/domains/planning/session_planning.py")
        exec(compile(self.source.read_text(encoding="utf-8"), module.__file__, "exec"), module.__dict__)


def worker(snapshot_path, output, legacy_source):
    if legacy_source:
        sys.meta_path.insert(0, LegacyPlannerLoader(legacy_source))
    from app.domains.planning.contracts import PlanningContext
    from app.domains.planning.execution_proposals import ExecutionAdaptationProposalContext
    from app.domains.planning.season_structure import SeasonStructureBuilder, SeasonStructureConfig
    from app.domains.planning.weekly_budget import build_weekly_budget_plan, WeeklyBudgetConfig
    from app.domains.planning.session_planning import build_session_plan, SessionPlanningConfig
    from app.domains.planning.weekly_intent import build_session_plan_with_shadow
    from app.domains.planning.workout_builder import build_structured_workout, WorkoutBuilderConfig
    from app.domains.planning.numeric_adaptation import resolve_numeric_adaptations
    from app.domains.planning.planning_adaptation import normalize_numeric_planning_adaptation, with_planning_adaptation
    from app.domains.planning.preview import build_preview_artifact

    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ctx = PlanningContext.model_validate(data["context"])
    proposals = ExecutionAdaptationProposalContext.model_validate(data["proposals"])
    config = SessionPlanningConfig(version="0.8F.9", algorithm_version="0.8F.9")
    wc = WorkoutBuilderConfig(version="0.8F.9", algorithm_version="0.8F.9")

    def outputs(current):
        season = SeasonStructureBuilder(SeasonStructureConfig(version="0.8F.3", algorithm_version="0.8F.3")).build(current)
        budgets = build_weekly_budget_plan(current, season, WeeklyBudgetConfig(version="0.8F.4", algorithm_version="0.8F.4"))
        if legacy_source:
            plan = build_session_plan(current, season, budgets, config)
            report = None
        else:
            plan, report = build_session_plan_with_shadow(current, season, budgets, config)
        prescriptions = tuple(s for w in plan.weeks for s in w.sessions)
        drafts = tuple(build_structured_workout(current, s, wc) for s in prescriptions)
        return season, budgets, plan, prescriptions, drafts, report

    season, budgets, plan, prescriptions, drafts, report = outputs(ctx)
    adaptation = normalize_numeric_planning_adaptation(resolve_numeric_adaptations(
        proposals=proposals, context=ctx, prescriptions=prescriptions, drafts=drafts,
    )).planning_input
    if adaptation is not None:
        ctx = with_planning_adaptation(ctx, adaptation)
        season, budgets, plan, prescriptions, drafts, report = outputs(ctx)
    roles = {g.goal_id: g.role for g in season.goals}
    artifact = build_preview_artifact(
        athlete_id=ctx.request.athlete_id, timezone_name=ctx.request.timezone_name,
        context_fingerprint_value=ctx.fingerprint, season=season, budgets=budgets, session_plan=plan,
        goals=tuple(g.model_copy(update={"role": roles[g.competition_goal_id]}) for g in ctx.goals),
        workout_drafts=drafts, algorithm_version="0.8F.9", configuration_version="0.8F.9",
    )
    output.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
    if report is not None:
        output.with_suffix(".diagnostics.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def snapshot_live(planning_date):
    from uuid import UUID
    from sqlalchemy import text
    from app.db.session import SessionLocal
    from app.application.planning_context import PlanningContextAssembler
    from app.application.execution_proposals import ExecutionAdaptationProposalAssembler
    from app.application.planning_preferences import PlanningPreferencesApplication, preferences_from_row
    from app.domains.planning.contracts import PlanningRequest

    athlete = UUID("542a8eeb-5fca-4e21-b14e-0f6d02d0f54b")
    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            read_only = db.scalar(text("SHOW transaction_read_only"))
            revision = db.scalar(text("SELECT version_num FROM alembic_version"))
            row = PlanningPreferencesApplication(db).require_latest(athlete)
            prefs = preferences_from_row(row)  # EXACT persisted preferences, including null.
            request = PlanningRequest(
                athlete_id=athlete, planning_date=planning_date, start_date=planning_date,
                goal_ids=(UUID("7f911333-e2d2-4ba2-95ad-30867fb56e1d"),), timezone_name="Europe/Madrid",
                preferences=prefs, algorithm_version="0.8F.6", configuration_version="0.8F.6",
            )
            ctx = PlanningContextAssembler(
                db, training_load_algorithm_version="0.7b.1", load_aggregation_algorithm_version="0.7c.1",
                manual_strength_algorithm_version="0.7e.1", training_status_algorithm_version="0.7f.1",
            ).assemble(request, include_capability=True)
            assert ctx.goals[0].event_date == date(2027, 10, 16)
            proposals = ExecutionAdaptationProposalAssembler(db).assemble(
                athlete_profile_id=athlete, as_of_date=planning_date,
            )
            return {"context": ctx.model_dump(mode="json", exclude_none=True),
                    "proposals": proposals.model_dump(mode="json", exclude_none=True),
                    "source": {"transaction_read_only": read_only, "revision": revision, "preference_version": row.version_number,
                               "persisted_preferences": prefs.model_dump(mode="json"), "real_writes": 0, "preview_acceptances": 0}}
        finally:
            db.rollback()


def export_report(snapshot_path, legacy, current):
    from app.domains.planning.contracts import PlanningContext
    from app.domains.planning.preview import TrainingPlanPreviewArtifact, build_preview_artifact
    from app.domains.planning.session_planning import _frequency, SessionPlanningConfig
    from app.domains.planning.weekly_intent import PlanningIntentShadowReport

    assert legacy.read_bytes() == current.read_bytes(), "FAIL: shadow changed artifact bytes"
    a = TrainingPlanPreviewArtifact.model_validate_json(current.read_text(encoding="utf-8"))
    rebuilt = build_preview_artifact(
        athlete_id=a.athlete_id, timezone_name=a.timezone_name, context_fingerprint_value=a.context_fingerprint,
        season=a.season_structure, budgets=a.weekly_budget_plan, session_plan=a.session_plan, goals=a.goals,
        workout_drafts=tuple(s.workout for s in a.sessions), algorithm_version=a.algorithm_version,
        configuration_version=a.configuration_version,
    )
    assert rebuilt.fingerprint == a.fingerprint
    report = PlanningIntentShadowReport.model_validate_json(current.with_suffix(".diagnostics.json").read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ctx = PlanningContext.model_validate(snapshot["context"])
    assert report.athlete_id == ctx.request.athlete_id and report.plan_fingerprint == a.session_plan.fingerprint
    # Counterfactual frequency ONLY, not a persisted preference or a new plan.
    target6 = ctx.model_copy(update={"preferences": ctx.preferences.model_copy(update={"target_sessions_per_week": 6})})
    config = SessionPlanningConfig(version="0.8F.9", algorithm_version="0.8F.9")
    probes = []
    for budget in a.weekly_budget_plan.budgets:
        trace = {}
        counts = _frequency(target6, budget, config, trace)
        probes.append({"week_start": str(budget.week_start), "counts": counts,
                       "capacity": trace["capacity"], "horizon_adjusted": trace["horizon_adjusted_sessions"],
                       "reasons": [r.model_dump(mode="json") for r in trace["reasons"]]})
    run_cap = []; run_proposal_cap = []; strength24 = []; rows = []
    for shadow in report.weeks:
        intent = shadow.intent; comparison = shadow.comparison
        run = next((s for s in intent.session_intents if s.role == "RUN_LONG"), None)
        bike = next((s for s in intent.session_intents if s.role == "BIKE_LONG"), None)
        strength = [s for s in intent.session_intents if s.sport == "strength"]
        if run and run.progression.cap_minutes == 120:
            if run.progression.final_legacy_minutes == 120:
                run_cap.append(str(intent.week_start))
            if run.progression.proposed_minutes is not None and run.progression.proposed_minutes >= 120:
                run_proposal_cap.append(str(intent.week_start))
        if strength and all(s.progression.historical_mean_minutes == s.progression.final_legacy_minutes == 24 for s in strength):
            strength24.append(str(intent.week_start))
        rows.append({"week_start": str(intent.week_start), "phase": intent.phase, "frequency_source": intent.frequency_source,
                     "requested_sessions": intent.requested_sessions, "resolved_sessions": intent.resolved_sessions,
                     "actual_sessions": comparison.actual_sessions,
                     "desired_composition": {s.sport: s.sessions for s in intent.desired_composition},
                     "actual_composition": {s.name: s.value for s in comparison.actual_composition},
                     "weekly_minutes_intent": intent.weekly_minutes_target, "actual_minutes": comparison.actual_minutes,
                     "run_long_proposed": run.progression.proposed_minutes if run else None,
                     "run_long_final": run.progression.final_legacy_minutes if run else None,
                     "bike_long_proposed": bike.progression.proposed_minutes if bike else None,
                     "bike_long_final": bike.progression.final_legacy_minutes if bike else None,
                     "strength_source_final": [{"source": s.progression.progression_source, "minutes": s.progression.final_legacy_minutes} for s in strength],
                     "status": comparison.status, "discrepancies": [d.model_dump(mode="json") for d in comparison.discrepancies]})
    count = len(rows); full = sum(w.comparison.fully_satisfies_intent for w in report.weeks)
    summary = {
        "source": snapshot.get("source", {"offline": True}), "legacy_byte_equivalent": True,
        "artifact_fingerprint": a.fingerprint, "session_plan_fingerprint": a.session_plan.fingerprint,
        "artifact_sha256": hashlib.sha256(current.read_bytes()).hexdigest(), "weeks": count,
        "resolved_generation_matches": sum(w.comparison.resolved_generation_matches for w in report.weeks),
        "fully_satisfies_intent": full, "fully_satisfies_intent_percent": round(100 * full / count, 2) if count else None,
        "unknown_weekly_minutes_weeks": sum(w.intent.weekly_minutes_target is None for w in report.weeks),
        "run_long_final_at_cap120_weeks": run_cap, "run_long_proposed_at_or_above_cap120_weeks": run_proposal_cap,
        "historical_strength24_weeks": strength24,
        "status_counts": dict(Counter(w.comparison.status for w in report.weeks)),
        "discrepancy_counts": dict(sorted(Counter(d.code for w in report.weeks for d in w.comparison.discrepancies).items())),
        "target6_frequency_probe": probes, "table": rows,
    }
    (OUT / "weekly-intent-shadow-validation.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# WeeklyPlanningIntent — auditoría shadow del horizonte", "",
             "Preferencias persistidas exactas; no se fuerza target=6. As-of e inicio: " + str(ctx.request.planning_date) + ".",
             "El diagnóstico es externo al plan. Artefacto completo idéntico byte a byte al planner congelado antes del bloque.", "",
             f"Semanas: {count}. Coincidencia con las decisiones resueltas legacy: {summary['resolved_generation_matches']}/{count}. Cumplimiento completo: {full}/{count} ({summary['fully_satisfies_intent_percent']}%). Minutos semanales independientes desconocidos: {summary['unknown_weekly_minutes_weeks']}/{count}.", "",
             "El cumplimiento completo exige que no haya MISMATCH ni UNKNOWN. CAP_REACHED y la fuente histórica de fuerza son observaciones, no incumplimientos. Una semana con minutos/volumen desconocidos no se certifica coherente aunque reproduzca exactamente el legacy.", "",
             f"RUN_LONG final120: {len(run_cap)} semanas. Propuesta que toca/supera cap120: {len(run_proposal_cap)}; puede terminar por debajo por DELOAD. Fuerza histórica24: {len(strength24)} semanas.", "",
             "[Validación y fechas exactas](../informe/weekly-intent-shadow-validation.json). [Contratos y comparaciones completos](../informe/weekly-intent-shadow-current.diagnostics.json).", "",
             "Conteos R/B/N/F: carrera/bici/natación/fuerza. Las discrepancias por sesión, días y provenance completos están en JSON. UNKNOWN de volumen por deporte se resume aquí como SPORT_VOLUME_INTENT_UNKNOWN.", "",
             "| Semana | Fase | Requested | Resuelto/actual | Composición deseada/actual R/B/N/F | Min intento/actual | Run propuesto/final | Bike propuesto/final | Fuerza fuente/final | Discrepancias |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    sports = ("running", "cycling", "swimming", "strength")
    for row in rows:
        composition = "/".join(str(row["desired_composition"][s]) for s in sports) + " / " + "/".join(str(row["actual_composition"][s]) for s in sports)
        pair = lambda prefix: str(row[prefix + "_proposed"]) + "/" + str(row[prefix + "_final"]) if row[prefix + "_proposed"] is not None else "—"
        strength_text = "; ".join(s["source"] + ":" + str(s["minutes"]) for s in row["strength_source_final"]) or "—"
        codes = ", ".join(sorted({d["code"] for d in row["discrepancies"]})) or "—"
        lines.append("| " + " | ".join([row["week_start"], row["phase"], str(row["requested_sessions"]) if row["requested_sessions"] is not None else "NULL (legacy)",
                     f"{row['resolved_sessions']}/{row['actual_sessions']}", composition, f"UNKNOWN/{row['actual_minutes']}", pair("run_long"), pair("bike_long"), strength_text, codes]) + " |")
    lines += ["", "## Probe target=6, sin modificar preferencias", "",
              "Se llama a la MISMA regla de frecuencia con una copia target6 y los límites actuales; no se genera ni acepta otro plan. Si la capacidad, incluido el marcador de competición, baja a5, el intento mantiene requested6, la capacidad registra5 y el diagnóstico puede explicar la diferencia.", ""]
    for probe in probes:
        if sum(probe["counts"].values()) != probe["horizon_adjusted"]:
            lines.append(f"- {probe['week_start']}: horizon-adjusted={probe['horizon_adjusted']}, capacity={probe['capacity']}, resolved={sum(probe['counts'].values())}; razones completas en JSON.")
    (ROOT / "docs/weekly-intent-shadow-horizon.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"table", "target6_frequency_probe", "source", "run_long_final_at_cap120_weeks", "run_long_proposed_at_or_above_cap120_weeks", "historical_strength24_weeks"}}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--legacy-source", type=Path)
    parser.add_argument("--planning-date", type=date.fromisoformat, default=date(2026, 11, 9))
    args = parser.parse_args()
    if args.worker:
        worker(args.input, args.output, args.legacy_source)
        return
    legacy_source = args.legacy_source or OUT / "weekly-intent-shadow-legacy-source.txt"
    before = json.loads((OUT / "weekly-intent-shadow-before.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(legacy_source.read_bytes()).hexdigest() == before["source_hashes"]["backend/app/domains/planning/session_planning.py"]
    snapshot = args.input or OUT / "weekly-intent-shadow-input.json"
    if args.input is None:
        snapshot.write_text(json.dumps(snapshot_live(args.planning_date), indent=2), encoding="utf-8")
    legacy = OUT / "weekly-intent-shadow-legacy.json"
    current = OUT / "weekly-intent-shadow-current.json"
    print("Frozen input ready. Running isolated legacy and shadow workers.", flush=True)
    processes = [subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", "--input", str(snapshot.resolve()),
                                  "--output", str(output)] + (["--legacy-source", str(legacy_source.resolve())] if is_legacy else []), cwd=ROOT / "backend")
                 for output, is_legacy in ((legacy, True), (current, False))]
    codes = [p.wait() for p in processes]
    if any(codes):
        raise RuntimeError(f"audit worker failures: {codes}")
    export_report(snapshot, legacy, current)


if __name__ == "__main__":
    main()
