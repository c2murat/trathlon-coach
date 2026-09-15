import type {ReassessmentStatus} from "./reassessmentTypes";

export const statusPresentation: Record<ReassessmentStatus, {label: string; description: string}> = {
  REASSESSMENT_CANDIDATE: {label: "Revisión recomendada", description: "La evidencia reciente sugiere que conviene volver a revisar esta referencia."},
  NO_REASSESSMENT_NEEDED: {label: "Sin revisión necesaria", description: "La evidencia disponible no indica que esta referencia necesite revisarse ahora."},
  INSUFFICIENT_EVIDENCE: {label: "Aún no hay evidencia suficiente", description: "Hacen falta más sesiones estructuradas compatibles para valorar esta referencia."},
  INCONSISTENT_EVIDENCE: {label: "Evidencia no concluyente", description: "Los datos disponibles no muestran una tendencia suficientemente consistente para valorar esta referencia."},
  REFERENCE_UNAVAILABLE: {label: "Referencia no disponible", description: "Falta una referencia vigente para realizar esta valoración."},
};
export const confidenceLabels = {HIGH: "Alta", MEDIUM: "Media", LOW: "Baja", INSUFFICIENT: "Insuficiente"};
const reasons: Record<string, string> = {
  REPEATED_ABOVE_ANCHORED_TARGET: "Varias sesiones estructuradas se han completado por encima de la potencia asociada a esta referencia.",
  REPEATED_FASTER_THAN_ANCHORED_TARGET: "Varias sesiones estructuradas se han completado a un ritmo más rápido que el asociado a esta referencia.",
  RECENT_EVIDENCE_SUFFICIENT: "Hay suficiente evidencia reciente para realizar esta valoración.",
  REFERENCE_MISSING: "No hay una referencia vigente disponible.",
  RECENT_PARTIALS_PRESENT: "También hay sesiones recientes parcialmente completadas.",
  EXTREME_OVERSHOOT_PRESENT: "Algunas ejecuciones se alejan mucho de lo prescrito y no permiten una conclusión fiable.",
  EVIDENCE_CONTRADICTORY: "La evidencia no muestra una tendencia suficientemente consistente.",
  STRUCTURED_EVIDENCE_INSUFFICIENT: "No hay suficientes sesiones estructuradas comparables.",
  RECENT_EVIDENCE_INSUFFICIENT: "Faltan sesiones comparables recientes.",
  TARGET_NOT_CAPABILITY_ANCHORED: "Algunas sesiones no pueden vincularse con certeza a esta referencia.",
  UNKNOWN_MAJORITY: "En la mayoría de las sesiones no hay una comparación válida disponible.",
  UNMATCHED_MAJORITY: "La mayoría de las sesiones no están vinculadas a una actividad completada.",
  INDEPENDENT_ACTIVITIES_INSUFFICIENT: "No hay suficientes actividades independientes para confirmar una ejecución repetida.",
  NO_REPEATED_REASSESSMENT_SIGNAL: "No se observa una señal repetida que justifique revisar la referencia ahora.",
};
export const reasonLabel = (code: string) => reasons[code] ?? "Hay información adicional de la valoración que todavía no puede mostrarse.";
export function reassessmentError(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  if (message.includes("(401)")) return "Tu sesión ha caducado. Inicia sesión para consultar la revisión de referencias.";
  if (message.includes("(403)")) return "No tienes permiso para consultar las referencias de este atleta.";
  if (message.includes("(404)")) return "No se ha encontrado la revisión de referencias para este atleta.";
  if (/\(5\d\d\)/.test(message)) return "El servidor no ha podido cargar la revisión de referencias. Inténtalo de nuevo.";
  return "No se ha podido conectar para cargar la revisión de referencias. Inténtalo de nuevo.";
}
