import type {DiagnosticLoadValue,WeeklyLoadReconciliation} from "../../types/planning";

const number=(value:DiagnosticLoadValue)=>value===null?"No disponible":Number(value).toLocaleString("es-ES",{minimumFractionDigits:2,maximumFractionDigits:2});

export function LoadReconciliationSummary({week}:{week?:WeeklyLoadReconciliation}){
 if(!week)return null;
 const state=week.reconciliation_state;
 return <section aria-label="Carga semanal estimada" className="planning-summary">
  <h3>Carga semanal estimada</h3>
  <dl><dt>Presupuesto</dt><dd>{number(week.weekly_load_budget)}</dd>
   <dt>Estimación prescrita</dt><dd>{number(week.prescribed_estimated_total)}</dd>
   <dt>Desviación</dt><dd>{week.variance_percent===null?"No disponible":`${Number(week.variance_percent)>=0?"+":""}${number(week.variance_percent)} %`}</dd>
   <dt>Calidad de estimación</dt><dd>{week.quality==="MEDIUM"?"Media":week.quality==="LOW"?"Baja":"No disponible"}</dd></dl>
  <p>{state==="NOT_RECONCILED"?"No reconciliado con el presupuesto semanal":state==="REVIEW_REQUIRED"?"Fuera de la tolerancia estimada: requiere revisión":state==="RECONCILED"?"Dentro de la tolerancia del presupuesto semanal":"Información insuficiente para reconciliar con el presupuesto semanal"}</p>
  {week.quality_warning&&<p>La estimación tiene cobertura limitada.</p>}
  {state==="NOT_RECONCILED"&&<p>La desviación supera la tolerancia del {number(Number(week.tolerance)*100)} %. No se puede aceptar este preview.</p>}
  {state==="REVIEW_REQUIRED"&&<p>La desviación supera la tolerancia del {number(Number(week.tolerance)*100)} %. Esta proyección no tiene confianza validada para bloquear la aceptación. Revisa el volumen prescrito.</p>}
 </section>;
}
