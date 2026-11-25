"""Block 4A isolated replay. Live capture is read-only; workers are offline."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "informe"
SCENARIOS = ("reference-null", "reference-target6", "reference-race-cap", "current-null", "current-target6")


def worker(name, baseline):
    from scripts import audit_structural_intent as replay
    replay.BASE = OUT / "block4a-baseline"
    latest = {}
    if baseline:
        sys.meta_path.insert(0, replay.FrozenPlanning())
    else:
        from app.domains.planning import weekly_intent
        from app.domains.planning.volume_intent import VolumeShadowBuild
        original = weekly_intent.build_session_plan_with_intent

        def observed(context, season, budgets, config, *, workout_observer=None):
            volume = VolumeShadowBuild(context, config)
            def prepare(intent, prescriptions):
                volume.prepare(intent, prescriptions)
                if workout_observer:
                    workout_observer(intent, prescriptions)
            plan, shadow, structure = original(context, season, budgets, config,
                workout_observer=prepare, coherent_volume=True)
            latest.update(volume=volume, plan=plan, shadow=shadow, structure=structure)
            return plan, shadow, structure
        weekly_intent.build_session_plan_with_intent = observed
    path = OUT / f"block4a-{name}-{'before' if baseline else 'after'}.json"
    replay.worker(OUT / f"block4a-{name}-input.json", path, False)
    if not baseline and latest["structure"] is not None:
        from app.domains.planning.preview import TrainingPlanPreviewArtifact
        artifact = TrainingPlanPreviewArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        report = latest["volume"].finish(latest["plan"], latest["shadow"],
            tuple(s.workout for s in artifact.sessions), artifact.load_reconciliation)
        (OUT / f"block4a-{name}-volume.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def export():
    from app.domains.planning.preview import TrainingPlanPreviewArtifact, preview_artifact_payload
    from app.domains.planning.volume_intent import VolumeShadowReport
    manifest = json.loads((OUT / "block4a-baseline/manifest.json").read_text(encoding="utf-8"))
    protected = ("weekly_distribution", "workout_builder", "weekly_budget", "prescribed_load", "session_compatibility",
                 "adaptive_targets", "numeric_adaptation", "prescription_intensity")
    hashes = {}
    for name in protected:
        key = f"backend/app/domains/planning/{name}.py"
        hashes[name] = hashlib.sha256((ROOT / key).read_bytes()).hexdigest() == manifest["hashes"][key]
    assert all(hashes.values())
    checks = {"protected_sources_unchanged": hashes, "real_writes": 0, "acceptances": 0, "scenarios": {}}
    for name in SCENARIOS:
        before_path = OUT / f"block4a-{name}-before.json"
        after_path = OUT / f"block4a-{name}-after.json"
        before = TrainingPlanPreviewArtifact.model_validate_json(before_path.read_text(encoding="utf-8"))
        after = TrainingPlanPreviewArtifact.model_validate_json(after_path.read_text(encoding="utf-8"))
        same = preview_artifact_payload(before) == preview_artifact_payload(after)
        assert same, "existing policy should retain effective prescription"
        assert before.fingerprint == after.fingerprint
        item = {"same_prescription_payload": same, "same_fingerprint": True, "fingerprint": after.fingerprint,
                "before_sha256": hashlib.sha256(before_path.read_bytes()).hexdigest(),
                "after_sha256": hashlib.sha256(after_path.read_bytes()).hexdigest()}
        checks["scenarios"][name] = item
        if name.endswith("null"):
            assert before_path.read_bytes() == after_path.read_bytes()
            item["byte_identical"] = True
            continue
        report = VolumeShadowReport.model_validate_json((OUT / f"block4a-{name}-volume.json").read_text(encoding="utf-8"))
        item.update(weeks=len(report.weeks), minutes_variances=sorted({str(w.minutes_variance) for w in report.weeks}),
                    constrained_weeks=[str(w.intent.week_start) for w in report.weeks if w.constrained_minutes],
                    cap_weeks=[str(w.intent.week_start) for w in report.weeks if "VOLUME_CONSTRAINED_BY_CAP" in w.diagnostics])
        assert not any(w.daily_violations for w in report.weeks)
        if name.endswith("race-cap"):
            assert report.weeks[-1].constrained_minutes > 0
            continue
        rows = ["# Block 4A: " + name + " before / after", "",
            "Duration authority uses existing role policies once. Same targets and workouts imply zero improvement from an already zero minutes variance. Strength is the historical legacy component, not part of endurance authority.", "",
            "All weeks are shown, including at least the first 12 consecutive BASE weeks. Totals exclude competition (no estimated competition duration). Free days are weekday numbers 0=Monday. Secondary column shows unchanged role names and durations.", "",
            "| Week | Phase / adjustment | Sessions before/after | Target min | Actual before/after | Run | Bike | Swim | Strength | Run long before/after | Bike long before/after | Secondary before/after | Free days before/after | Doubles before/after | Delta min / % | Load budget | Allocated | Estimated before/after | Load delta / quality | Caps / reasons |",
            "|---|---|---|---:|---|---:|---:|---:|---:|---|---|---|---|---|---|---:|---:|---|---|---|"]
        base = []
        for w, old, new, budget, load in zip(report.weeks, before.session_plan.weeks, after.session_plan.weeks,
            after.weekly_budget_plan.budgets, after.load_reconciliation.weeks, strict=True):
            old_sessions = [s for s in old.sessions if s.discipline != "competition"]
            sessions = [s for s in new.sessions if s.discipline != "competition"]
            intent = w.intent
            if intent.phase == "BASE" and (old.week_end-old.week_start).days == 6:
                base.append(w)
                assert len(sessions) == 6
            def duration(group, role):
                return next((s.target_duration_minutes for s in group if s.session_type.value == role), "-")
            def free(group):
                return ",".join(str(d) for d in range(7) if not any(s.date.weekday() == d for s in group))
            def doubles(group):
                return sum(n > 1 for n in Counter(s.date for s in group).values())
            def secondary(group):
                return ",".join(f"{s.session_type.value}:{s.target_duration_minutes}" for s in group
                    if s.discipline != "strength" and not s.session_type.value.endswith("LONG"))
            caps = ",".join(r.role for sport in intent.sports for r in sport.roles
                            if any(x.code == "VOLUME_CONSTRAINED_BY_CAP" for x in r.reasons))
            adj = ",".join(a.code for a in budget.adjustments if a.code not in {"BASELINE", "LOW_CONFIDENCE"})
            old_load = next(x for x in before.load_reconciliation.weeks if x.week_start == old.week_start)
            values = [intent.week_start, f"{intent.phase}/{adj}", f"{len(old_sessions)}/{len(sessions)}", intent.weekly_minutes_target,
                f"{sum(s.target_duration_minutes for s in old_sessions)}/{w.actual_minutes}", intent.run_minutes_target,
                intent.bike_minutes_target, intent.swim_minutes_target, intent.strength_minutes_target,
                f"{duration(old_sessions, 'RUN_LONG')}/{duration(sessions, 'RUN_LONG')}",
                f"{duration(old_sessions, 'BIKE_LONG')}/{duration(sessions, 'BIKE_LONG')}",
                secondary(old_sessions) + " / " + secondary(sessions), free(old_sessions) + " / " + free(sessions),
                f"{doubles(old_sessions)}/{doubles(sessions)}", f"{w.minutes_variance}/{w.minutes_variance_percent}",
                load.weekly_load_budget, load.allocated_total, f"{old_load.prescribed_estimated_total}/{load.prescribed_estimated_total}",
                f"{load.variance}/{load.quality}", caps + ";" + ",".join(w.diagnostics)]
            rows.append("| " + " | ".join(map(str, values)) + " |")
            assert all(s.date.weekday() != 0 for s in sessions), "Monday preferred free should remain feasible"
            assert all(s.date.weekday() == 4 for s in sessions if s.session_type.value == "RUN_LONG")
            assert all(s.date.weekday() == 6 for s in sessions if s.session_type.value == "BIKE_LONG")
        assert len(base) >= 12
        assert all((base[i+1].intent.week_start-base[i].intent.week_start).days == 7 for i in range(11))
        item.update(base_weeks=len(base), base_exact_6=True, first12_targets=[w.intent.weekly_minutes_target for w in base[:12]],
                    strength_durations=sorted({s.target_duration_minutes for w in after.session_plan.weeks for s in w.sessions if s.discipline == "strength"}))
        (ROOT / f"docs/block4a-{name}-horizon.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (OUT / "block4a-validation.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=SCENARIOS)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.baseline); return
    if args.export:
        export(); return
    from scripts.audit_structural_intent import freeze_input
    reference = json.loads((OUT / "block2-live-input.json").read_text(encoding="utf-8"))
    current = json.loads((OUT / "block4a-live-input.json").read_text(encoding="utf-8"))
    for name in SCENARIOS:
        snapshot = current if name.startswith("current") else reference
        target = None if name.endswith("null") else 6
        maximum = 12 if name.endswith("target6") else 6
        freeze_input(snapshot, target, maximum, OUT / f"block4a-{name}-input.json")
        processes = [subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", name] +
            (["--baseline"] if baseline else []), cwd=ROOT / "backend") for baseline in (True, False)]
        codes = [p.wait() for p in processes]
        if any(codes):
            raise RuntimeError(f"worker failed: {codes}")
    export()


if __name__ == "__main__":
    main()
