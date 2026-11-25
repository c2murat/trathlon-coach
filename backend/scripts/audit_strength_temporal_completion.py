"""4B.4: offline reconciliation and differentiated missing-data audit.

No prescription values or planning behavior are introduced. Reuses the single
4B.1/4B.2 estimator and the unchanged 4B.3 policy on frozen inputs.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "informe"
SCENARIOS = ("current-null", "current-target6", "reference-target6", "reference-race-cap", "double-target6")
AUDIT_VERSION = "strength-temporal-completion-audit-4b4-v1"


def classify_missing(component):
    """Multiple causes may apply; counts are requirements, not time events."""
    if "execution_scope" in component or "rest_occurrences" in component:
        return {"component": component, "kind": "unilateral_scope", "causes": ["catalog_information", "structural_ambiguity"],
                "required": "Explicit total/per-side sets, side order and pause occurrences"}
    if "execution" in component:
        return {"component": component, "kind": "execution", "causes": ["sporting_prescription", "independent_evidence"],
                "required": "Session-specific tempo or per-set duration with independent provenance"}
    if component.startswith("gap:"):
        return {"component": component, "kind": "transition", "causes": ["sporting_prescription", "independent_evidence"],
                "required": "Whole boundary gap or explicit disjoint/included scopes"}
    if component.startswith(("warmup", "cooldown")):
        return {"component": component, "kind": "session_edge", "causes": ["sporting_prescription", "independent_evidence"],
                "required": "Explicit prefix/tail timing, edge nodes, or sourced absence; never implicit zero"}
    return {"component": component, "kind": "structure_or_other", "causes": ["structural_ambiguity", "technical_model_review"],
            "required": "Review diagnostic; do not assume an additive duration"}


def describe_structure(nodes):
    if any(n["kind"] == "repeat" for n in nodes):
        return "repeat_requires_declared_order"
    return "flat_strength" if all(n.get("phase") == "strength" for n in nodes) else "flat_with_edge_nodes"


def worker(name):
    from scripts import audit_structural_intent as replay
    from app.domains.planning import weekly_intent
    original = weekly_intent.build_session_plan_with_intent
    captured = {}
    def active(ctx, season, budgets, config, *, workout_observer=None):
        captured["context"] = ctx
        return original(ctx, season, budgets, config, workout_observer=workout_observer, coherent_volume=True)
    weekly_intent.build_session_plan_with_intent = active
    source = OUT / ("block4b2-double-input.json" if name == "double-target6" else f"block4a-{name}-input.json")
    dest = OUT / f"block4b4-{name}-artifact.json"
    replay.worker(source, dest, False)
    from app.domains.planning.preview import TrainingPlanPreviewArtifact
    from app.domains.planning.strength_timing_policy import build_strength_temporal_policy_shadow
    artifact = TrainingPlanPreviewArtifact.model_validate_json(dest.read_text(encoding="utf-8"))
    report = build_strength_temporal_policy_shadow(captured["context"], artifact)
    (OUT / f"block4b4-{name}-policy.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")


def export():
    rows = []; exercises = Counter(); unilateral = Counter(); kinds = Counter(); causes = Counter(); groups = Counter(); scenarios = {}
    for name in SCENARIOS:
        old_bytes = (OUT / f"block4b3-{name}-after.json").read_bytes()
        new_bytes = (OUT / f"block4b4-{name}-artifact.json").read_bytes()
        assert old_bytes == new_bytes, name
        artifact = json.loads(new_bytes)
        old = json.loads((OUT / f"block4b3-{name}-policy.json").read_text(encoding="utf-8"))
        new = json.loads((OUT / f"block4b4-{name}-policy.json").read_text(encoding="utf-8"))
        assert old == new, "Re-evaluation must preserve existing temporal policy results"
        sessions = [s for s in artifact["sessions"] if s["prescription"]["discipline"] == "strength"]
        assert len(sessions) == len(new["evaluations"])
        for session, before, e in zip(sessions, old["evaluations"], new["evaluations"], strict=True):
            estimate = e["estimate"]; nodes = session["workout"]["definition"]["steps"]
            structure = describe_structure(nodes); role = session["prescription"]["session_type"]
            known = estimate["known_components"]
            assert len({k["component_id"] for k in known}) == len(known)
            assert sum(k["seconds"]["minimum"] for k in known) == estimate["known_subtotal_seconds"]["minimum"]
            assert sum(k["seconds"]["maximum"] for k in known) == estimate["known_subtotal_seconds"]["maximum"]
            issues = [classify_missing(c) for c in estimate["missing_components"]]
            for issue in issues:
                kinds[issue["kind"]] += 1
                causes.update(issue["causes"])
            for node in nodes:
                if node.get("phase") == "strength":
                    exercises[node["title"]] += 1
                    if node.get("unilateral") is True: unilateral[node["title"]] += 1
            groups[(role, structure, e["phase"], estimate["coverage"])] += 1
            rows.append({"scenario": name, "date": e["scheduled_date"], "role": role, "structure": structure,
                "phase": e["phase"], "workout_fingerprint": estimate["workout_fingerprint"],
                "before_coverage": before["estimate"]["coverage"], "coverage": estimate["coverage"],
                "known_components": known, "unknown_components": issues, "policy": e["policy"],
                "parameter_decisions": e["parameter_decisions"], "complete_interval": estimate["duration_seconds"],
                "known_subtotal": estimate["known_subtotal_seconds"], "reconciliation": e["comparison"],
                "incompatibility_reason": e["comparison"]["reason"] if e["comparison"]["status"] in ("LEGACY_BELOW_KNOWN_MINIMUM", "LEGACY_BELOW_INTERVAL", "LEGACY_ABOVE_INTERVAL") else None,
                "validation_state": estimate["validation_state"], "diagnostics": e["diagnostics"]})
        scenarios[name] = {"evaluations": len(sessions), "artifact_bytes_equal": True, "fingerprint_equal": old["artifact_fingerprint"] == new["artifact_fingerprint"],
            "policy_report_equal": True, "artifact_sha256": hashlib.sha256(new_bytes).hexdigest()}
    assert len(rows) == 468
    baseline = json.loads((OUT / "block4b4-baseline/manifest.json").read_text(encoding="utf-8"))
    protected = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in baseline["hashes"].items()}
    assert all(protected.values()), "Application/domain/public contract changed"
    summary = {"audit_version": AUDIT_VERSION, "scenarios": scenarios, "coverage": dict(Counter(r["coverage"] for r in rows)),
        "comparisons": dict(Counter(r["reconciliation"]["status"] for r in rows)), "unknown_kinds": dict(kinds),
        "nonexclusive_cause_counts": dict(causes), "exercise_occurrences_missing_execution": dict(exercises.most_common()),
        "unilateral_occurrences": dict(unilateral.most_common()),
        "groups": [{"role": k[0], "structure": k[1], "phase": k[2], "coverage": k[3], "count": v} for k,v in sorted(groups.items())],
        "protected_sources_unchanged": protected, "database_reads": 0, "real_data_writes": 0, "acceptances": 0}
    (OUT / "block4b4-session-matrix.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "block4b4-validation.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k != "protected_sources_unchanged"}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--worker", choices=SCENARIOS)
    args = parser.parse_args()
    if args.worker: worker(args.worker); return
    for name in SCENARIOS:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", name], cwd=ROOT / "backend", check=True)
    export()


if __name__ == "__main__": main()
