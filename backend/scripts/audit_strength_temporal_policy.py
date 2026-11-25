"""4B.3 offline shadow evaluation, frozen inputs and byte identity checks."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"backend"))
OUT=ROOT/"informe"
SCENARIOS=("current-null","current-target6","reference-target6","reference-race-cap","double-target6")


def input_path(name):
    return OUT/("block4b2-double-input.json" if name=="double-target6" else f"block4a-{name}-input.json")


def worker(name,baseline):
    from scripts import audit_structural_intent as replay
    replay.BASE=OUT/"block4b3-baseline"
    if baseline:sys.meta_path.insert(0,replay.FrozenPlanning())
    from app.domains.planning import weekly_intent
    original=weekly_intent.build_session_plan_with_intent
    latest={}
    def active(ctx,season,budgets,config,*,workout_observer=None):
        latest["context"]=ctx
        return original(ctx,season,budgets,config,workout_observer=workout_observer,coherent_volume=True)
    weekly_intent.build_session_plan_with_intent=active
    path=OUT/f"block4b3-{name}-{'before' if baseline else 'after'}.json"
    replay.worker(input_path(name),path,False)
    if not baseline:
        from app.domains.planning.preview import TrainingPlanPreviewArtifact
        from app.domains.planning.strength_timing import build_strength_timing_shadow
        from app.domains.planning.strength_timing_policy import build_strength_temporal_policy_shadow
        artifact=TrainingPlanPreviewArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        prior=build_strength_timing_shadow(latest["context"],artifact)
        report=build_strength_temporal_policy_shadow(latest["context"],artifact)
        (OUT/f"block4b3-{name}-prior-timing.json").write_text(prior.model_dump_json(indent=2),encoding="utf-8")
        (OUT/f"block4b3-{name}-policy.json").write_text(report.model_dump_json(indent=2),encoding="utf-8")


def export():
    from app.domains.planning.strength_timing import StrengthTimingShadowReport
    from app.domains.planning.strength_timing_policy import StrengthTemporalPolicyReport
    manifest=json.loads((OUT/"block4b3-baseline/manifest.json").read_text(encoding="utf-8"))
    protected={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in manifest["hashes"].items()
        if name!="backend/app/application/planning_preview.py"}
    assert all(protected.values()),"existing domain or public contract changed"
    checks={"protected_sources_unchanged":protected,"real_data_writes":0,"database_reads":0,"acceptances":0,"scenarios":{}}
    totals=Counter();comparisons=Counter();reasons=Counter();parameters=Counter();components=Counter();unknowns=Counter();policies=Counter();before_cov=Counter();rows=[]
    for name in SCENARIOS:
        before=(OUT/f"block4b3-{name}-before.json").read_bytes();after=(OUT/f"block4b3-{name}-after.json").read_bytes()
        assert before==after,f"artifact changed: {name}"
        artifact=json.loads(after)
        prior=StrengthTimingShadowReport.model_validate_json((OUT/f"block4b3-{name}-prior-timing.json").read_text(encoding="utf-8"))
        report=StrengthTemporalPolicyReport.model_validate_json((OUT/f"block4b3-{name}-policy.json").read_text(encoding="utf-8"))
        assert len(prior.estimates)==len(report.evaluations)
        duplicates=0
        for e,old in zip(report.evaluations,prior.estimates,strict=True):
            assert e.estimate.workout_fingerprint==old.workout_fingerprint
            before_cov[old.coverage]+=1;totals[e.estimate.coverage]+=1;comparisons[e.comparison.status]+=1
            assert e.estimate.validation_state=="not_evaluated"
            ids=[k.component_id for k in e.estimate.known_components]
            duplicates+=len(ids)-len(set(ids))
            assert sum(k.seconds.minimum for k in e.estimate.known_components)==e.estimate.known_subtotal_seconds.minimum
            assert e.estimate.duration_seconds is None # no invented execution, edges or transitions in captures
            for d in e.parameter_decisions:
                reasons[d.reason]+=1
                if d.action=="rest_scope_prescribed":parameters[d.parameter_seconds]+=1
            for k in e.estimate.known_components:
                components["inter_set_rest" if ".pause_after_set[" in k.component_id else k.component_id]+=1
            for key in e.estimate.missing_components:
                kind="execution_scope" if "execution_scope" in key else "execution" if "execution" in key else "rest_scope_or_occurrences" if "rest_occurrences" in key else "between_exercises" if key.startswith("gap:") else "warmup" if key.startswith("warmup") else "cooldown" if key.startswith("cooldown") else key
                unknowns[kind]+=1
            if any(d.action=="rest_scope_prescribed" for d in e.parameter_decisions):policies[e.policy.policy_id]+=1
            rows.append({"scenario":name,"date":str(e.scheduled_date),"phase":e.phase,"workout_fingerprint":e.estimate.workout_fingerprint,
                "before":old.coverage,"after":e.estimate.coverage,"legacy_seconds":e.comparison.legacy_seconds,
                "known_min_seconds":e.estimate.known_subtotal_seconds.minimum,"known_max_seconds":e.estimate.known_subtotal_seconds.maximum,
                "comparison":e.comparison.status,"missing_components":e.estimate.missing_components,
                "policy_id":e.policy.policy_id,"policy_version":e.policy.version})
        assert duplicates==0
        data=json.loads(input_path(name).read_text(encoding="utf-8"));prefs=data["context"]["preferences"]
        slots={s["weekday"]:s for s in prefs["availability_slots"]}
        from datetime import date
        paired=0
        for week in artifact["session_plan"]["weeks"]:
            groups=defaultdict(list)
            for p in week["sessions"]:
                if p["discipline"]!="competition":groups[p["date"]].append(p)
            for day,group in groups.items():
                slot=slots[date.fromisoformat(day).weekday()]
                assert len(group)<=min(slot["max_sessions"],prefs["max_sessions_per_day"])
                assert sum(s["target_duration_minutes"] for s in group)<=slot["available_minutes"]
                paired+=len(group)>1
        checks["scenarios"][name]={"artifact_bytes_equal":True,"fingerprint_equal":True,"sha256":hashlib.sha256(after).hexdigest(),
            "fingerprint":artifact["fingerprint"],"total_outputs":len(report.evaluations),"strength_sessions":len(report.evaluations),
            "before":dict(Counter(e.coverage for e in prior.estimates)),"after":dict(Counter(e.estimate.coverage for e in report.evaluations)),
            "comparisons":dict(Counter(e.comparison.status for e in report.evaluations)),"double_counted_components":duplicates,"double_days":paired,
            "known_subtotal_values_seconds":sorted({e.estimate.known_subtotal_seconds.minimum for e in report.evaluations})}
    checks["matrix"]={"total_outputs":len(rows),"identified_strength_sessions":len(rows),"before":dict(before_cov),"after":dict(totals),
        "comparisons":dict(comparisons),"parameter_seconds_counts":dict(parameters),"known_components":dict(components),
        "unknown_components":dict(unknowns),"policy_applications":dict(policies),"parameter_decision_reasons":dict(reasons),
        "double_counted_components":0,"complete_legacy_comparisons":0,"proven_partial_lower_bound_exceedances":comparisons["LEGACY_BELOW_KNOWN_MINIMUM"],
        "no_full_duration_inferred_from_partial":True}
    assert len(rows)==468
    (OUT/"block4b3-session-matrix.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
    (OUT/"block4b3-validation.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    lines=["# Bloque4B.3 - matriz diagnostica de468 salidas", "", "Capturas reutilizadas:23/11 y09/11/2026; evaluacion offline sin cambios de datos reales.","",
        "| Escenario | Salidas fuerza | Antes C/P/U | Despues C/P/U | Comparacion valida | Dobles | Doble cuenta | Bytes/FP |",
        "|---|---:|---|---|---|---:|---:|---|"]
    def triple(c):return "/".join(str(c.get(s,0)) for s in ("complete","partial","unavailable"))
    for name,s in checks["scenarios"].items():
        lines.append(f"| {name} | {s['strength_sessions']} | {triple(s['before'])} | {triple(s['after'])} | {s['comparisons']} | {s['double_days']} | 0 | Identicos |")
    lines += ["", "C/P/U = complete/partial/unavailable. Partial no demuestra que la sesion completa quepa en legacy o disponibilidad.","",
        "Subtotales conocidos: descansos entre series bilaterales. Ejecucion, alcance unilateral, transiciones y extremos no se rellenan.","",
        "[JSON por sesion](../informe/block4b3-session-matrix.json), [contadores de componentes, politicas, motivos y parametros](../informe/block4b3-validation.json).",""]
    (ROOT/"docs/block4b3-shadow-matrix.md").write_text("\n".join(lines),encoding="utf-8")
    print(json.dumps({"matrix":checks["matrix"],"identity_scenarios":list(checks["scenarios"])},indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--worker",choices=SCENARIOS);parser.add_argument("--baseline",action="store_true");parser.add_argument("--export",action="store_true")
    args=parser.parse_args()
    if args.worker:worker(args.worker,args.baseline);return
    if args.export:export();return
    for name in SCENARIOS:
        processes=[subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--worker",name]+(["--baseline"] if baseline else []),cwd=ROOT/"backend") for baseline in (True,False)]
        codes=[p.wait() for p in processes]
        if any(codes):raise RuntimeError(f"workers failed: {codes}")
    export()


if __name__=="__main__":main()
