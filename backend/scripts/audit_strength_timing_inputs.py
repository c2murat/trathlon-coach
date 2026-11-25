"""Offline Block 4B.2 identity audit; never generates or accepts DB previews."""
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
    replay.BASE=OUT/"block4b2-baseline"
    if baseline:sys.meta_path.insert(0,replay.FrozenPlanning())
    from app.domains.planning import weekly_intent
    original=weekly_intent.build_session_plan_with_intent
    latest={}
    def active(ctx,season,budgets,config,*,workout_observer=None):
        latest["context"]=ctx
        return original(ctx,season,budgets,config,workout_observer=workout_observer,coherent_volume=True)
    weekly_intent.build_session_plan_with_intent=active
    path=OUT/f"block4b2-{name}-{'before' if baseline else 'after'}.json"
    replay.worker(input_path(name),path,False)
    if not baseline:
        from app.domains.planning.preview import TrainingPlanPreviewArtifact
        from app.domains.planning.strength_timing_inputs import build_strength_timing_inputs_shadow
        artifact=TrainingPlanPreviewArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        report=build_strength_timing_inputs_shadow(latest["context"],artifact)
        assert report.estimates and all(e.coverage=="unavailable" and e.duration_seconds is None for e in report.estimates)
        (OUT/f"block4b2-{name}-timing.json").write_text(report.model_dump_json(indent=2),encoding="utf-8")


def export():
    from app.domains.planning.strength_timing import StrengthTimingShadowReport
    manifest=json.loads((OUT/"block4b2-baseline/manifest.json").read_text(encoding="utf-8"))
    protected={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in manifest["hashes"].items()
        if name!="backend/app/domains/planning/strength_timing.py"}
    assert all(protected.values()),"existing domain or public contract changed"
    checks={"protected_sources_unchanged":protected,"real_data_writes":0,"database_reads":0,"acceptances":0,"scenarios":{}}
    for name in SCENARIOS:
        before=(OUT/f"block4b2-{name}-before.json").read_bytes()
        after=(OUT/f"block4b2-{name}-after.json").read_bytes()
        assert before==after,f"artifact changed: {name}"
        artifact=json.loads(after)
        report=StrengthTimingShadowReport.model_validate_json((OUT/f"block4b2-{name}-timing.json").read_text(encoding="utf-8"))
        data=json.loads(input_path(name).read_text(encoding="utf-8"))
        prefs=data["context"]["preferences"]
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
        assert all(e.coverage=="unavailable" and e.duration_seconds is None and e.validation_state=="not_evaluated" for e in report.estimates)
        checks["scenarios"][name]={"artifact_bytes_equal":True,"fingerprint_equal":True,"sha256":hashlib.sha256(after).hexdigest(),
            "fingerprint":artifact["fingerprint"],"strength_sessions":len(report.estimates),"coverage":dict(Counter(e.coverage for e in report.estimates)),
            "double_days":paired,"phases":sorted({p["phase"] for w in artifact["session_plan"]["weeks"] for p in w["sessions"] if p["discipline"]=="strength"})}
        if name=="double-target6":assert paired>0
    (OUT/"block4b2-validation.json").write_text(json.dumps(checks,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in checks.items() if k!="protected_sources_unchanged"},indent=2))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--worker",choices=SCENARIOS)
    parser.add_argument("--baseline",action="store_true")
    parser.add_argument("--export",action="store_true")
    args=parser.parse_args()
    if args.worker:worker(args.worker,args.baseline);return
    if args.export:export();return
    from app.domains.planning.contracts import PlanningContext,context_fingerprint
    data=json.loads((OUT/"block4a-current-target6-input.json").read_text(encoding="utf-8"))
    ctx=PlanningContext.model_validate(data["context"])
    prefs=ctx.preferences.model_copy(update={"availability_slots":tuple(s for s in ctx.preferences.availability_slots if s.weekday!=3)})
    ctx=ctx.model_copy(update={"preferences":prefs,"request":ctx.request.model_copy(update={"preferences":prefs})})
    ctx=ctx.model_copy(update={"fingerprint":context_fingerprint(ctx.model_dump(exclude={"fingerprint"}))})
    (OUT/"block4b2-double-input.json").write_text(json.dumps({**data,"context":ctx.model_dump(mode="json"),
        "scenario":"IN_MEMORY_AVAILABILITY_FIXTURE_NO_DATABASE_CHANGES"},indent=2),encoding="utf-8")
    for name in SCENARIOS:
        processes=[subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--worker",name]+(["--baseline"] if baseline else []),cwd=ROOT/"backend")
            for baseline in (True,False)]
        codes=[p.wait() for p in processes]
        if any(codes):raise RuntimeError(f"workers failed: {codes}")
    export()


if __name__=="__main__":main()
