import {useEffect,useRef,useState} from "react";
import type {ApiClient} from "../../services/apiClient";
import {activitySyncCompletedEvent} from "../../components/ActivitySyncButton";
import {AppLink} from "../../app/usePathname";
import {durationLabel,sessionLabel,sportLabel} from "../calendar/planningFormat";
import {dateLabel} from "../calendar/competitionLabels";
import {WorkoutDetail} from "../calendar/PlanningFlowPages";
import {formatDate} from "../../utils/format";
import type {ActivityFacts,CompletionStatus,ExecutionOverview,ExecutionSessionView,TargetAdherenceEvidence} from "./executionOverviewTypes";
import "./executionOverview.css";

const labels:Record<CompletionStatus,string>={COMPLETED:"Completado",PARTIAL:"Realizado parcialmente",
  OVER_DURATION:"Duración superior a la prevista",UNKNOWN:"No hay datos suficientes para valorar el cumplimiento",
  UNMATCHED:"No se ha encontrado una actividad vinculada"};
const distance=(meters:number|string|null)=>meters===null?"Distancia no disponible":`${(Number(meters)/1000).toLocaleString("es-ES",{maximumFractionDigits:2})} km`;
const duration=(seconds:number|null)=>seconds===null?"Duración no disponible":durationLabel(seconds);

export function targetAdherenceText(target:TargetAdherenceEvidence|null){
  if(!target||["LOW","INSUFFICIENT"].includes(target.confidence))return "No hay datos suficientes para comprobar los intervalos";
  if(Number(target.target_hit_fraction)===1&&target.matched_repetitions===target.planned_repetitions)return "Objetivos comprobados cumplidos";
  if(Number(target.target_hit_fraction)>0)return "Objetivos parcialmente cumplidos";
  return "Los objetivos comprobados están fuera del rango previsto";
}
function Activity({value,timezone}:{value:ActivityFacts;timezone?:string}){return <div className="execution-activity">
  <AppLink to={`/activities/${value.id}`}>{value.name}</AppLink>
  <p>{sportLabel(value.sport)} · {formatDate(value.started_at,timezone??value.timezone)} · {duration(value.duration_seconds)} · {distance(value.distance_meters)}</p>
  {(value.average_heart_rate_bpm!==null||value.average_power_w!==null)&&<p>
    {value.average_heart_rate_bpm!==null&&<>Pulso medio: {Math.round(value.average_heart_rate_bpm)} ppm. </>}
    {value.average_power_w!==null&&<>Potencia media: {Math.round(value.average_power_w)} W.</>}
  </p>}
</div>}
function Comparison({value,timezone}:{value:ExecutionSessionView;timezone?:string}){const evidence=value.evidence;return <div className="execution-comparison">
  <p><strong>Planificado: </strong>{sportLabel(value.sport)} · {sessionLabel(value.title)} · {duration(value.planned_duration_seconds)}{value.planned_distance_meters!==null&&<> · {distance(value.planned_distance_meters)}</>}</p>
  <p><strong>Realizado: </strong>{duration(evidence?.actual_duration_seconds??null)} · {distance(evidence?.actual_distance_m??null)}</p>
  {value.activities.map(activity=><Activity key={activity.id} value={activity} timezone={timezone}/>)}
  {evidence?.completion_status==="UNMATCHED"&&<p>La ausencia de vínculo no permite saber si esta sesión se realizó.</p>}
  {evidence?.sport_match===false&&<p>Hay actividades vinculadas de un deporte distinto; la comparación es limitada.</p>}
  {!evidence&&<p>Esta sesión está fuera del histórico evaluado, limitado a una ventana de 84 días hasta la fecha de consulta.</p>}
  {value.workout&&<><p>{targetAdherenceText(evidence?.target_comparison??null)}</p>
    {evidence?.target_comparison&&!["LOW","INSUFFICIENT"].includes(evidence.target_comparison.confidence)&&<p>Repeticiones comparadas: {evidence.target_comparison.matched_repetitions} de {evidence.target_comparison.planned_repetitions}.</p>}
    <WorkoutDetail workout={value.workout}/></>}
</div>}
export function ExecutionOverviewSection({client,athleteId}:{client:ApiClient;athleteId?:string}){
  const [data,setData]=useState<ExecutionOverview|null>(null),[error,setError]=useState(false),[loading,setLoading]=useState(true);
  const [scope,setScope]=useState<string|undefined>();const generation=useRef(0);
  useEffect(()=>{
    const load=async()=>{const request=++generation.current;setLoading(true);setError(false);setData(null);
      try{const result=await client.executionOverview!();if(athleteId&&result.athlete_id!==athleteId)throw new Error("athlete mismatch");
        if(request===generation.current)setData(result);
      }catch{if(request===generation.current)setError(true)}finally{if(request===generation.current){setLoading(false);setScope(athleteId)}}};
    if(!client.executionOverview)return;
    void load();
    const refresh=(event:Event)=>{const source=(event as CustomEvent<{athleteId?:string}>).detail?.athleteId;if(!source||!athleteId||source===athleteId)void load()};
    window.addEventListener(activitySyncCompletedEvent,refresh);
    return()=>{generation.current++;window.removeEventListener(activitySyncCompletedEvent,refresh)};
  },[client,athleteId]);
  if(!client.executionOverview)return null;
  if(loading||scope!==athleteId)return <section className="dashboard-section" role="status">Consultando tus sesiones recientes…</section>;
  if(error)return <section className="dashboard-section" role="alert">No se ha podido consultar el cumplimiento de tus sesiones.</section>;
  if(!data)return null;
  return <ExecutionOverviewContent data={data}/>;
}
export function ExecutionOverviewContent({data,timezone}:{data:ExecutionOverview;timezone?:string}){
  return <section className="dashboard-section execution-overview" aria-label="Ejecución de tus entrenamientos">
    <h2>Último entrenamiento</h2>
    {data.latest_activity?<><Activity value={data.latest_activity} timezone={timezone}/>
      {data.latest_activity_sessions.length?data.latest_activity_sessions.map(value=><article key={value.id}>
        <h3>Sesión relacionada: {sessionLabel(value.title)}</h3><p className="status-badge">{labels[value.evidence?.completion_status??"UNKNOWN"]}</p><Comparison value={value} timezone={timezone}/>
      </article>):<p>No se ha encontrado una sesión planificada vinculada a esta actividad.</p>}
    </>:<p>Todavía no hay actividades registradas.</p>}
    <h2>Sesiones recientes</h2>
    <p>Últimas sesiones planificadas de días anteriores, dentro de los últimos 84 días.</p>
    {data.recent_sessions.length?<ul className="execution-sessions">{data.recent_sessions.map(value=><li key={value.id}><details>
      <summary><time dateTime={value.date}>{dateLabel(value.date)}</time> · {sessionLabel(value.title)} <span className="status-badge">{labels[value.evidence?.completion_status??"UNKNOWN"]}</span></summary>
      <Comparison value={value} timezone={timezone}/>
    </details></li>)}</ul>:<p>No hay sesiones planificadas recientes.</p>}
  </section>;
}
