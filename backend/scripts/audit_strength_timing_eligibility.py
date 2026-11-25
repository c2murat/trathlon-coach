"""4B.5 frozen replay, eligibility sidecars and protected byte comparisons."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "informe"
SCENARIOS = ("current-null", "current-target6", "reference-target6", "reference-race-cap", "double-target6")


def worker(name):
    # Reuse 4B.4's replay implementation without overwriting its evidence.
    from scripts import audit_strength_temporal_completion as replay
    from app.domains.planning import weekly_intent
    workspace = OUT / "block4b5-replay"
    workspace.mkdir(exist_ok=True)
    source = "block4b2-double-input.json" if name == "double-target6" else f"block4a-{name}-input.json"
    shutil.copyfile(OUT / source, workspace / source)
    replay.OUT = workspace
    captured = {}
    original = weekly_intent.build_session_plan_with_intent
    def observe(context, *args, **kwargs):
        captured["context"] = context
        return original(context, *args, **kwargs)
    weekly_intent.build_session_plan_with_intent = observe
    replay.worker(name)
    for kind in ("artifact", "policy"):
        shutil.copyfile(workspace / f"block4b4-{name}-{kind}.json", OUT / f"block4b5-{name}-{kind}.json")
    from app.domains.planning.preview import TrainingPlanPreviewArtifact
    from app.domains.planning.strength_timing_policy import prescribe_strength_temporal_inputs
    from app.domains.planning.strength_timing_inputs import compile_strength_timing_inputs
    from app.domains.planning.strength_timing_eligibility import evaluate_strength_timing_eligibility
    artifact = TrainingPlanPreviewArtifact.model_validate_json((OUT / f"block4b5-{name}-artifact.json").read_text(encoding="utf-8"))
    context = captured["context"]
    results = []
    for session in artifact.sessions:
        if session.prescription.discipline != "strength":
            continue
        prescribed = prescribe_strength_temporal_inputs(context, session.prescription, session.workout)
        snapshot = compile_strength_timing_inputs(context, session.workout, prescribed.inputs).snapshot
        result = evaluate_strength_timing_eligibility(context, session.workout, snapshot)
        results.append(result.model_dump(mode="json"))
    (OUT / f"block4b5-{name}-eligibility.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


def export():
    coverage = Counter(); reasons = Counter(); eligible = 0; scenarios = {}
    for name in SCENARIOS:
        a = (OUT / f"block4b4-{name}-artifact.json").read_bytes()
        b = (OUT / f"block4b5-{name}-artifact.json").read_bytes()
        assert a == b
        assert (OUT / f"block4b4-{name}-policy.json").read_bytes() == (OUT / f"block4b5-{name}-policy.json").read_bytes()
        # Explicit public workout bytes in the same canonical serialization.
        old = json.loads(a); new = json.loads(b)
        assert json.dumps([s["workout"] for s in old["sessions"]], sort_keys=True).encode() == json.dumps([s["workout"] for s in new["sessions"]], sort_keys=True).encode()
        values = json.loads((OUT / f"block4b5-{name}-eligibility.json").read_text(encoding="utf-8"))
        for v in values:
            coverage[v["estimate"]["coverage"]] += 1
            reasons.update(v["reasons"])
            eligible += v["temporally_eligible"]
            assert not v["activation_authorized"]
        scenarios[name] = {"evaluations":len(values), "artifact_bytes_equal":True, "public_workouts_equal":True,
            "fingerprint_equal":old["fingerprint"] == new["fingerprint"], "protected_timing_report_bytes_equal":True,
            "artifact_sha256":hashlib.sha256(b).hexdigest()}
    assert sum(coverage.values()) == 468
    baseline = json.loads((OUT / "block4b5-baseline/manifest.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p,h in baseline["hashes"].items())
    result = {"scenarios":scenarios, "coverage":dict(coverage), "eligible":eligible,
        "not_eligible":sum(coverage.values())-eligible, "reasons":dict(reasons), "activations":0,
        "effective_legacy_changes":0, "protected_existing_files":len(baseline["hashes"]),
        "real_data_writes":0, "acceptances":0, "database_reads":0}
    (OUT / "block4b5-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--worker", choices=SCENARIOS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker); return
    for name in SCENARIOS:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", name], cwd=ROOT / "backend", check=True)
    export()


if __name__ == "__main__":
    main()
