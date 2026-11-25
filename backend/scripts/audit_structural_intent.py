"""Block 2: read-only athlete preview and isolated Block 1 comparisons."""
import argparse
from collections import Counter, defaultdict
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
BASE = OUT / "block2-baseline"
sys.path.insert(0, str(ROOT / "backend"))


class FrozenPlanning(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    names = {f"app.domains.planning.{n}" for n in ("session_planning", "weekly_intent", "weekly_distribution", "preview")}

    def find_spec(self, fullname, path, target=None):
        return importlib.util.spec_from_loader(fullname, self) if fullname in self.names else None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        relative = "backend/" + module.__name__.replace(".", "/") + ".py"
        source = BASE / (relative.replace("/", "__") + ".txt")
        module.__file__ = str(ROOT / relative)
        exec(compile(source.read_text(encoding="utf-8"), module.__file__, "exec"), module.__dict__)


def worker(input_path, output_path, baseline):
    if baseline:
        sys.meta_path.insert(0, FrozenPlanning())
    from app.domains.planning.contracts import PlanningContext
    from app.domains.planning.execution_proposals import ExecutionAdaptationProposalContext
    from app.domains.planning.season_structure import SeasonStructureBuilder, SeasonStructureConfig
    from app.domains.planning.weekly_budget import WeeklyBudgetConfig, build_weekly_budget_plan
    from app.domains.planning.session_planning import SessionPlanningConfig, build_session_plan
    from app.domains.planning.workout_builder import WorkoutBuilderConfig, build_structured_workout
    from app.domains.planning.preview import build_preview_artifact
    from app.domains.planning.numeric_adaptation import resolve_numeric_adaptations
    from app.domains.planning.planning_adaptation import normalize_numeric_planning_adaptation, with_planning_adaptation
    if not baseline:
        from app.domains.planning.weekly_intent import build_session_plan_with_intent
        from app.domains.planning.intent_workouts import IntentWorkoutBuild
    data = json.loads(input_path.read_text(encoding="utf-8"))
    ctx = PlanningContext.model_validate(data["context"])
    proposals = ExecutionAdaptationProposalContext.model_validate(data["proposals"])
    config = SessionPlanningConfig(version="0.8F.9", algorithm_version="0.8F.9")
    wc = WorkoutBuilderConfig(version="0.8F.9", algorithm_version="0.8F.9")

    def outputs(context):
        season = SeasonStructureBuilder(SeasonStructureConfig(version="0.8F.3", algorithm_version="0.8F.3")).build(context)
        budgets = build_weekly_budget_plan(context, season, WeeklyBudgetConfig(version="0.8F.4", algorithm_version="0.8F.4"))
        structure = None
        if baseline:
            plan = build_session_plan(context, season, budgets, config)
            drafts = tuple(build_structured_workout(context, s, wc) for w in plan.weeks for s in w.sessions)
        else:
            content = IntentWorkoutBuild(context, wc)
            plan, _, structure = build_session_plan_with_intent(context, season, budgets, config, workout_observer=content.prepare)
            if structure:
                drafts = content.finish(plan, structure)
                structure = content.annotate(structure)
            else:
                drafts = tuple(build_structured_workout(context, s, wc) for w in plan.weeks for s in w.sessions)
            # Entire drafts, including targets/steps/duration/identity, must be
            # equivalent to the unchanged builder for each final prescription.
            assert [d.model_dump_json() for d in drafts] == [build_structured_workout(context, s, wc).model_dump_json() for w in plan.weeks for s in w.sessions]
        return season, budgets, plan, drafts, structure

    season, budgets, plan, drafts, structure = outputs(ctx)
    prescriptions = tuple(s for w in plan.weeks for s in w.sessions)
    adaptation = normalize_numeric_planning_adaptation(resolve_numeric_adaptations(
        proposals=proposals, context=ctx, prescriptions=prescriptions, drafts=drafts,
    )).planning_input
    if adaptation is not None:
        ctx = with_planning_adaptation(ctx, adaptation)
        season, budgets, plan, drafts, structure = outputs(ctx)
    roles = {g.goal_id: g.role for g in season.goals}
    kwargs = {"structural_planning": structure} if structure is not None else {}
    artifact = build_preview_artifact(
        athlete_id=ctx.request.athlete_id, timezone_name=ctx.request.timezone_name, context_fingerprint_value=ctx.fingerprint,
        season=season, budgets=budgets, session_plan=plan,
        goals=tuple(g.model_copy(update={"role": roles[g.competition_goal_id]}) for g in ctx.goals),
        workout_drafts=drafts, algorithm_version="0.8F.9", configuration_version="0.8F.9", **kwargs,
    )
    output_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")


def freeze_input(snapshot, target, maximum, output):
    from app.domains.planning.contracts import PlanningContext, context_fingerprint
    ctx = PlanningContext.model_validate(snapshot["context"])
    prefs = ctx.preferences.model_copy(update={"target_sessions_per_week": target, "max_sessions_per_week": maximum})
    ctx = ctx.model_copy(update={"preferences": prefs, "request": ctx.request.model_copy(update={"preferences": prefs})})
    ctx = ctx.model_copy(update={"fingerprint": context_fingerprint(ctx.model_dump(exclude={"fingerprint"}))})
    output.write_text(json.dumps({**snapshot, "context": ctx.model_dump(mode="json", exclude_none=True),
                                 "scenario": {"target": target, "max_weekly": maximum, "preference_writes": 0}}, indent=2), encoding="utf-8")


def export(snapshot):
    old_null = OUT / "block2-null-before.json"; new_null = OUT / "block2-null-after.json"
    assert old_null.read_bytes() == new_null.read_bytes(), "NULL byte compatibility failed"
    a = json.loads((OUT / "block2-target6-after.json").read_text(encoding="utf-8"))
    before = json.loads((OUT / "block2-target6-before.json").read_text(encoding="utf-8"))
    structure = a["structural_planning"]
    rows = []; phases = defaultdict(list)
    for result, week in zip(structure["weeks"], a["session_plan"]["weeks"], strict=True):
        intent = result["intent"]
        counts = {c["sport"]: c["sessions"] for c in intent["desired_composition"]}
        assert sum(counts.values()) == result["intended_sessions"] == len(intent["session_intents"])
        assert result["placed"] + len(result["unplaced"]) == result["generated"]
        row = {"week": intent["week_start"], "end": intent["week_end"], "phase": intent["phase"],
               "requested": intent["requested_sessions"], "phase_adjusted": intent["phase_adjusted_sessions"],
               "horizon_adjusted": intent["horizon_adjusted_sessions"], "intents": result["intended_sessions"],
               "workouts": result["generated_workout_count"], "placed": result["placed"], "unplaced": len(result["unplaced"]),
               "counts": counts, "days": result["occupied_days"], "doubles": result["double_days"],
               "classification": result["classification"], "competition": result["competition_sessions"],
               "calendar_total": result["total_calendar_sessions"],
               "reasons": [r["code"] for r in intent["frequency_reasons"]],
               "unplaced_sessions": result["unplaced"], "warnings": week["warnings"]}
        rows.append(row); phases[row["phase"]].append(row)
    base = [r for r in rows if r["phase"] == "BASE" and (date.fromisoformat(r["end"]) - date.fromisoformat(r["week"])).days == 6]
    assert all(r["placed"] == r["intents"] == r["workouts"] == 6 and not r["unplaced"] for r in base)
    cap = json.loads((OUT / "block2-race-cap-after.json").read_text(encoding="utf-8"))["structural_planning"]["weeks"][-1]
    assert cap["intended_sessions"] == 6 and cap["placed"] == 5 and len(cap["unplaced"]) == 1
    summary = {
        "audit_date": "2026-11-12", "source": snapshot.get("source"), "planning_as_of": snapshot["context"]["request"]["planning_date"],
        "scenario": {"target_sessions_per_week": 6, "max_sessions_per_week": 12, "writes": 0},
        "legacy_null_byte_equivalent": True, "null_sha256": hashlib.sha256(new_null.read_bytes()).hexdigest(),
        "weeks": len(rows), "base_weeks": len(base), "base_exact_percent": 100.0,
        "classifications": dict(Counter(r["classification"] for r in rows)),
        "unplaced_count": sum(r["unplaced"] for r in rows),
        "unchanged_builder_drafts_verified": True,
        "target6_before_fingerprint": before["fingerprint"], "target6_after_fingerprint": a["fingerprint"],
        "phase_compositions": {phase: {"weeks": len(rr), "counts": [list(v) for v in sorted({tuple(r['counts'][s] for s in ('running','cycling','swimming','strength')) for r in rr})]} for phase, rr in phases.items()},
        "race_capacity_case": {k: cap[k] for k in ("requested_training_sessions", "phase_adjusted_sessions", "intended_sessions", "competition_sessions", "placed", "unplaced", "generated_workout_count", "classification")},
        "real_writes": 0, "preview_acceptances": 0, "rows": rows,
    }
    (OUT / "block2-validation.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Bloque 2 — horizonte athlete, target 6 / máximo 12", "",
             "Preview local de solo lectura, 09/11/2026–16/10/2027. Preferencias copiadas en memoria; sin guardar cambios ni aceptar planes.", "",
             f"BASE completas exactas: {len(base)}/{len(base)} (100 %). Sesiones sin colocar en el escenario principal: {summary['unplaced_count']}.", "",
             "Competición es adicional al target de entrenamiento y consume el máximo semanal del calendario. No existe una reducción del total explícito por taper; sí se reduce fuerza conforme a la regla existente. No se confunde capacidad con phase-adjustment.", "",
             "R/B/N/F = carrera/bici/natación/fuerza. Generated workouts cuenta también recetas construidas para intents no colocados; el artefacto publica solo las colocadas y conserva las restantes con razón.", "",
             "| Semana | Fase | Requested | Phase-adjusted | Horizon-adjusted | Intents | Workouts | Placed | Unplaced | R/B/N/F | Días | Dobles | Clase | Razón |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---|"]
    for r in rows:
        reason = "NO_TOTAL_FREQUENCY_PHASE_REDUCTION" + ("; COMPETITION_ADDITIONAL" if r["competition"] else "")
        lines.append("| " + " | ".join(map(str, [r["week"], r["phase"], r["requested"], r["phase_adjusted"], r["horizon_adjusted"], r["intents"], r["workouts"], r["placed"], r["unplaced"], "/".join(str(r["counts"][s]) for s in ("running", "cycling", "swimming", "strength")), r["days"], r["doubles"], r["classification"], reason])) + " |")
    lines += ["", "[Artefacto completo](../informe/block2-target6-after.json), [validación/composición por fase](../informe/block2-validation.json).", "",
              "Caso separado máximo semanal6: requested6, phase-adjusted6, seis intents/workouts, cinco colocadas y una no colocada con razón WEEKLY_LIMIT_INCLUDING_COMPETITION. No se ha cambiado la preferencia real.", ""]
    (ROOT / "docs/block2-horizon.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"rows", "race_capacity_case", "source"}}, indent=2))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--worker", action="store_true")
    parser.add_argument("--baseline", action="store_true"); parser.add_argument("--input", type=Path); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.input, args.output, args.baseline); return
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    for name in FrozenPlanning.names:
        relative = "backend/" + name.replace(".", "/") + ".py"
        assert hashlib.sha256((BASE / (relative.replace("/", "__") + ".txt")).read_bytes()).hexdigest() == manifest["hashes"][relative]
    if args.input:
        snapshot = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        from scripts.audit_weekly_intent_shadow import snapshot_live
        snapshot = snapshot_live(date(2026, 11, 9))
    (OUT / "block2-live-input.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    actual_max = snapshot["context"]["preferences"]["max_sessions_per_week"]
    for name, target, maximum in (("null", None, actual_max), ("target6", 6, 12), ("race-cap", 6, 6)):
        input_path = OUT / f"block2-{name}-input.json"; freeze_input(snapshot, target, maximum, input_path)
        print(f"Replaying {name} before/after from frozen input.", flush=True)
        processes = [subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", "--input", str(input_path),
                                      "--output", str(OUT / f"block2-{name}-{suffix}.json")] + (["--baseline"] if baseline else []), cwd=ROOT / "backend")
                     for suffix, baseline in (("before", True), ("after", False))]
        codes = [p.wait() for p in processes]
        if any(codes): raise RuntimeError(f"workers failed: {codes}")
    export(snapshot)


if __name__ == "__main__":
    main()
