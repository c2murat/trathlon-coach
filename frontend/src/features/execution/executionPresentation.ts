import type {CompletionStatus,TargetAdherenceEvidence} from "../dashboard/executionOverviewTypes";

export const executionLongLabels:Record<CompletionStatus,string>={COMPLETED:"Completado",PARTIAL:"Realizado parcialmente",
  OVER_DURATION:"Duración superior a la prevista",UNKNOWN:"No hay datos suficientes para valorar el cumplimiento",
  UNMATCHED:"No se ha encontrado una actividad vinculada"};

export const executionShortLabels:Record<CompletionStatus,string>={COMPLETED:"Completada",PARTIAL:"Parcial",OVER_DURATION:"Duración superior",UNMATCHED:"Sin actividad vinculada",UNKNOWN:"Evidencia insuficiente"};
export const unmatchedExplanation="La ausencia de vínculo no permite saber si esta sesión se realizó.";

export function targetAdherenceText(target:TargetAdherenceEvidence|null){
  if(!target||["LOW","INSUFFICIENT"].includes(target.confidence))return "No hay datos suficientes para comprobar los intervalos";
  if(Number(target.target_hit_fraction)===1&&target.matched_repetitions===target.planned_repetitions)return "Objetivos comprobados cumplidos";
  if(Number(target.target_hit_fraction)>0)return "Objetivos parcialmente cumplidos";
  return "Los objetivos comprobados están fuera del rango previsto";
}
