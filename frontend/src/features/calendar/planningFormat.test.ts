import {describe,expect,it} from "vitest";
import {durationLabel,errorMessage,goalRoleLabel,paceLabel,sessionLabel,sportLabel,targetLabel,warningLabel,workoutTargetLabel} from "./planningFormat";
describe("planning formatters",()=>{it("uses centralized Spanish labels",()=>{expect(sportLabel("cycling")).toBe("Ciclismo");expect(sessionLabel("RUN_THRESHOLD")).toBe("Carrera a umbral")});it("formats athlete targets",()=>{expect(durationLabel(4500)).toBe("1 h 15 min");expect(paceLabel(275)).toBe("4:35 /km");expect(targetLabel(250,"target_watts")).toBe("250 W");expect(targetLabel(8,"rpe")).toBe("RPE 8")});it("maps fingerprint conflicts",()=>expect(errorMessage(new Error("(409) fingerprint_mismatch"))).toBe("La vista previa ya no coincide con la versión esperada."));it("maps overlap conflicts",()=>expect(errorMessage(new Error('(409) {"code":"training_plan_overlap"}'))).toBe("Ya existe un plan de entrenamiento para parte de este periodo."));it("formats structured warnings without exposing enum codes",()=>{const text=warningLabel("DISCIPLINE_UNDERREPRESENTED",{discipline:"cycling"});expect(text).toContain("ciclismo");expect(text).not.toContain("DISCIPLINE_");expect(warningLabel("PREFERRED_REST_DAY_UNAVAILABLE")).toContain("descanso preferido")});it("formats every goal role explicitly",()=>expect([goalRoleLabel("primary"),goalRoleLabel("supporting"),goalRoleLabel("training")]).toEqual(["Principal","Secundario","Entrenamiento"]))});

describe("resolved workout targets",()=>{
 it("formats snapshotted FTP, threshold pace and CSS ranges",()=>{
  expect(workoutTargetLabel({metric:"power",mode:"percent_reference",reference:"FTP",minimum:.5,maximum:.65,reference_value:250,reference_unit:"watts",resolved_minimum:125,resolved_maximum:163,resolved_unit:"watts"})).toBe("Potencia 125–163 W · 50–65 % FTP · FTP: 250 W");
  expect(workoutTargetLabel({metric:"pace",mode:"percent_reference",reference:"threshold_pace",minimum:1.15,maximum:1.35,reference_value:240,reference_unit:"seconds_per_km",resolved_minimum:276,resolved_maximum:324,resolved_unit:"seconds_per_km"})).toContain("Ritmo 4:36–5:24 min/km");
  expect(workoutTargetLabel({metric:"swim_pace",mode:"percent_reference",reference:"CSS",minimum:1.1,maximum:1.25,reference_value:100,reference_unit:"seconds_per_100m",resolved_minimum:110,resolved_maximum:125,resolved_unit:"seconds_per_100m"})).toContain("Ritmo 1:50–2:05 /100 m");
 });
 it("localizes legacy relative fallback without technical identifiers",()=>{
  const label=workoutTargetLabel({metric:"pace",mode:"percent_reference",reference:"threshold_pace",minimum:1.15,maximum:1.35});
  expect(label).toBe("1,15–1,35 × ritmo umbral");expect(label).not.toContain("threshold_pace");
 });
});
