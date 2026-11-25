"""Offline strength shadow replay from the frozen, read-only Block 4A inputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "backend"))
OUT = ROOT / "informe"
SCENARIOS = ("current-null","current-target6","reference-target6","reference-race-cap")


def worker(name,baseline):
    from scripts import audit_structural_intent as replay
    replay.BASE = OUT / "block4b-baseline"
    if baseline:
        sys.meta_path.insert(0,replay.FrozenPlanning())
    from app.domains.planning import weekly_intent
    latest = {}
    original = weekly_intent.build_session_plan_with_intent
    def active(ctx,season,budgets,config,*,workout_observer=None):
        latest.update(context=ctx,config=config)
        return original(ctx,season,budgets,config,workout_observer=workout_observer,coherent_volume=True)
    weekly_intent.build_session_plan_with_intent = active
    path = OUT / f"block4b-{name}-{'before' if baseline else 'after'}.json"
    replay.worker(OUT / f"block4a-{name}-input.json",path,False)
    if not baseline:
        from app.domains.planning.preview import TrainingPlanPreviewArtifact
        from app.domains.planning.strength_intent import build_strength_shadow
        artifact = TrainingPlanPreviewArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        report = build_strength_shadow(latest["context"],artifact,latest["config"])
        (OUT / f"block4b-{name}-strength.json").write_text(report.model_dump_json(indent=2),encoding="utf-8")


def export():
    from app.domains.planning.strength_intent import StructuredStrengthShadowReport
    manifest = json.loads((OUT / "block4b-baseline/manifest.json").read_text(encoding="utf-8"))
    protected = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
        for name,digest in manifest["hashes"].items() if "/domains/" in name}
    assert all(protected.values()),"existing policy changed"
    checks = {"existing_domain_sources_unchanged":protected,"real_writes":0,"acceptances":0,"scenarios":{}}
    for name in SCENARIOS:
        before = (OUT / f"block4b-{name}-before.json").read_bytes()
        after = (OUT / f"block4b-{name}-after.json").read_bytes()
        assert before == after,f"artifact changed: {name}"
        report = StructuredStrengthShadowReport.model_validate_json((OUT / f"block4b-{name}-strength.json").read_text(encoding="utf-8"))
        artifact = json.loads(after)
        sessions = [s for w in report.weeks for s in w.sessions]
        assert all(s.structured_estimated_duration_minutes is None and s.variance_minutes is None for s in sessions)
        assert all(s.selected_duration_minutes==s.legacy_duration_minutes for s in sessions)
        pair_weeks = [w for w in report.weeks if len(w.sessions)==2]
        item = {"byte_identical":True,"sha256":hashlib.sha256(after).hexdigest(),"fingerprint":artifact["fingerprint"],
            "weeks":len(report.weeks),"strength_sessions_observed":len(sessions),
            "pair_weeks":len(pair_weeks),"identical_pair_weeks":sum(w.same_structure_within_week for w in pair_weeks),
            "legacy_minutes":sorted({s.legacy_duration_minutes for s in sessions}),
            "structured_duration_available":False,"confidence":"UNAVAILABLE",
            "phase_counts":dict(Counter(s.phase for s in sessions)),
            "unplaced_strength_sessions":sum(w.unplaced_strength_sessions for w in report.weeks)}
        checks["scenarios"][name] = item
        for week in artifact["session_plan"]["weeks"]:
            daily = Counter(s["date"] for s in week["sessions"] if s["discipline"]!="competition")
            assert max(daily.values(),default=0) <= 2
        if not name.endswith("target6"):
            continue
        assert len(report.weeks)>=12 and all(len(w.sessions)==2 for w in report.weeks[:12])
        rows = ["# Block 4B: strength shadow - " + name,"",
            "Offline comparison against frozen Block 4A. All legacy artifact bytes and workouts remain identical. S1/S2 are observed calendar occurrences, not new A/B content roles. Unknown estimates/variance are not zero.","",
            "| Week | Phase | S1 structure | S1 legacy min | S1 estimate | S2 structure | S2 legacy min | S2 estimate | RPE | Sets/reps | Rest s | Progression / variant | Confidence | Fallback |",
            "|---|---|---|---:|---|---|---:|---|---|---|---|---|---|---|"]
        for w in report.weeks:
            def summary(s):
                return "; ".join(f"{x.order}. {x.title}" for x in s.structure.exercises) if s else "-"
            a = w.sessions[0] if w.sessions else None
            b = w.sessions[1] if len(w.sessions)>1 else None
            first = a.structure.exercises[0] if a and a.structure.exercises else None
            values = [w.week_start,w.phase,summary(a),a.legacy_duration_minutes if a else "-","UNKNOWN",summary(b),b.legacy_duration_minutes if b else "-",
                "UNKNOWN" if b else "-",f"{first.target_rpe[0]}-{first.target_rpe[1]}" if first and first.target_rpe else "-",
                f"{first.sets}x{first.reps}" if first else "-",first.rest_seconds if first else "-",
                f"_progression_level={a.progression_level}; variant={a.structure.variant_index}; {a.progression_reason}" if a else "-",
                "UNAVAILABLE",a.fallback_reason if a else "NO_PLACED_STRENGTH"]
            rows.append("| " + " | ".join(map(str,values)) + " |")
        rows += ["","Profiles in the horizon include BASE/BUILD/SPECIFIC/TAPER; no post-race RECOVERY is invented. RECOVERY and COMPETITION profiles are separately tested against the existing builder. Full provenance, allocated times, previous/proposed/final structures and missing-data list: [JSON](../informe/block4b-"+name+"-strength.json).",""]
        (ROOT / f"docs/block4b-{name}-horizon.md").write_text("\n".join(rows),encoding="utf-8")
    (OUT / "block4b-validation.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in checks.items() if k!="existing_domain_sources_unchanged"},indent=2))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--worker",choices=SCENARIOS)
    parser.add_argument("--baseline",action="store_true")
    parser.add_argument("--export",action="store_true")
    args=parser.parse_args()
    if args.worker:
        worker(args.worker,args.baseline);return
    if args.export:
        export();return
    for name in SCENARIOS:
        processes=[subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--worker",name]+(["--baseline"] if baseline else []),cwd=ROOT/"backend")
                   for baseline in (True,False)]
        codes=[p.wait() for p in processes]
        if any(codes):raise RuntimeError(f"failed workers: {codes}")
    export()


if __name__=="__main__":
    main()
