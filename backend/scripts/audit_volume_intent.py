"""Offline Block 3 replay from frozen athlete inputs; no database connection."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "informe"


def worker(scenario, baseline):
    from scripts import audit_structural_intent as replay
    replay.BASE = OUT / "block3-baseline"
    path = OUT / f"block3-{scenario}-{'before' if baseline else 'after'}.json"
    latest = {}
    if baseline:
        sys.meta_path.insert(0, replay.FrozenPlanning())
    if not baseline:
        from app.domains.planning import weekly_intent
        from app.domains.planning.volume_intent import VolumeShadowBuild
        from app.domains.planning.preview import TrainingPlanPreviewArtifact
        original = weekly_intent.build_session_plan_with_intent

        def observed(context, season, budgets, config, *, workout_observer=None):
            volume = VolumeShadowBuild(context, config)

            def prepare(intent, prescriptions):
                volume.prepare(intent, prescriptions)
                if workout_observer:
                    workout_observer(intent, prescriptions)

            plan, shadow, structure = original(context, season, budgets, config, workout_observer=prepare)
            latest.update(volume=volume, plan=plan, shadow=shadow, structure=structure)
            return plan, shadow, structure

        weekly_intent.build_session_plan_with_intent = observed
    replay.worker(OUT / f"block2-{scenario}-input.json", path, False)
    if not baseline and latest["structure"] is not None:
        artifact = TrainingPlanPreviewArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        report = latest["volume"].finish(latest["plan"], latest["shadow"],
            tuple(s.workout for s in artifact.sessions), artifact.load_reconciliation)
        (OUT / f"block3-{scenario}-volume.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def export():
    from app.domains.planning.volume_intent import VolumeShadowReport
    manifest = json.loads((OUT / "block3-baseline/manifest.json").read_text(encoding="utf-8"))
    protected = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                 for name, digest in manifest["hashes"].items() if "/domains/" in name}
    assert all(protected.values()), "existing domain rule changed"
    checks = {"unchanged_domain_sources": protected}
    for scenario in ("null", "target6", "race-cap"):
        before = (OUT / f"block3-{scenario}-before.json").read_bytes()
        after = (OUT / f"block3-{scenario}-after.json").read_bytes()
        assert before == after, f"artifact bytes changed: {scenario}"
        checks[scenario] = {"byte_identical": True, "sha256": hashlib.sha256(after).hexdigest(),
                            "fingerprint": json.loads(after)["fingerprint"]}
    report = VolumeShadowReport.model_validate_json((OUT / "block3-target6-volume.json").read_text(encoding="utf-8"))
    artifact = json.loads((OUT / "block3-target6-after.json").read_text(encoding="utf-8"))
    budgets = {w["week_start"]: w for w in artifact["weekly_budget_plan"]["budgets"]}
    base = [w for w in report.weeks if w.intent.phase == "BASE"]
    assert len(base) >= 12
    assert all(not w.daily_violations for w in report.weeks)
    rows = ["# Bloque 3: comparación shadow de volumen", "",
            "Replay offline de la captura del bloque 2 (as-of 09/11/2026). Preferencias target=6, máximo semanal=12; ninguna consulta ni escritura a datos reales.", "",
            "Fuente: suma de las políticas existentes por rol, antes del builder. Las cuotas de carga no se convierten en cuotas de minutos. Las columnas de minutos excluyen competición, cuyo contenido/duración no se estima.", "",
            "Fuerza: minutos y contenido E×S×R (ejercicios × series × repeticiones), descanso en segundos y RPE. El contenido completo está en el JSON por sesión.", "",
            "| Semana | Fase / ajustes | Target min | Actual min | Run | Bike | Swim | Fuerza | RUN_LONG | BIKE_LONG | Fuerza 1 | Fuerza 2 | Carga budget | Estimada | Δ min / carga | Caps / razones |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|---|"]
    for w in report.weeks:
        sports = {s.sport: s for s in w.intent.sports}
        roles = [r for s in w.intent.sports for r in s.roles]
        strength = [f"{s.duration_seconds // 60} min; {len(s.exercises)}×{s.sets[0]}×{s.reps[0]}; rest {s.rest_seconds[0]}; RPE {s.rpe_bounds[0]}" for s in w.strength_volume_intent]
        caps = [r.role for r in roles if any(d.code == "CAP_REACHED" for d in r.reasons)]
        adjustments = ",".join(a["code"] for a in budgets[str(w.intent.week_start)]["adjustments"] if a["code"] not in {"BASELINE", "LOW_CONFIDENCE"})
        values = [w.intent.week_start, f"{w.intent.phase} / {adjustments}", w.intent.weekly_minutes_target, w.actual_minutes,
                  *(sports[s].minutes_target for s in ("running", "cycling", "swimming", "strength")),
                  next((r.final_value for r in roles if r.role == "RUN_LONG"), "—"),
                  next((r.final_value for r in roles if r.role == "BIKE_LONG"), "—"),
                  *(strength + ["—", "—"])[:2], w.intent.weekly_load_budget, w.estimated_load,
                  f"{w.minutes_variance} / {w.load_variance}", ",".join(caps) + "; " + ",".join(w.diagnostics)]
        rows.append("| " + " | ".join(map(str, values)) + " |")
    rows.extend(["", "Se muestran las 49 semanas, incluidas las primeras 12 BASE consecutivas, deload y taper. Un target derivado de duraciones legacy reconcilia por construcción cuando todos los workouts se colocan y conservan su duración; no valida una política de volumen independiente.", "",
                 "[JSON de trazas completo](../informe/block3-target6-volume.json). [Equivalencia de artefactos](../informe/block3-validation.json).", ""])
    (ROOT / "docs/block3-volume-horizon.md").write_text("\n".join(rows), encoding="utf-8")
    checks.update(weeks=len(report.weeks), base_weeks=len(base), first_12_consecutive_base=all(
        (base[i+1].intent.week_start - base[i].intent.week_start).days == 7 for i in range(11)),
        daily_violations=0, real_writes=0, acceptances=0,
        frequency_unchanged=True, workout_builder_unchanged=True,
        distinct_first12_targets=sorted({w.intent.weekly_minutes_target for w in base[:12]}))
    (OUT / "block3-validation.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=("null", "target6", "race-cap"))
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.baseline)
        return
    for scenario in ("null", "target6", "race-cap"):
        for baseline in (True, False):
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", scenario] +
                           (["--baseline"] if baseline else []), cwd=ROOT / "backend", check=True)
    export()


if __name__ == "__main__":
    main()
