import {AppLink} from "../../app/usePathname";
import {dateLabel,categoryLabels} from "../calendar/competitionLabels";
import {durationLabel,sessionLabel,sportLabel} from "../calendar/planningFormat";
import {interpretationCopy} from "../trainingStatus/interpretationPresentation";
import {ExecutionOverviewContent} from "./ExecutionOverviewSection";
import type {DailyOverview,DailySession} from "./dailyOverviewTypes";
import "./dailyOverview.css";

const statuses={planned:"Planificada",completed:"Completada",skipped:"Omitida",cancelled:"Cancelada"};
function Session({value}:{value:DailySession}){
  return <article className="daily-session">
    <h3>{/^[A-Z_]+$/.test(value.title)?sessionLabel(value.title):value.title}</h3>
    <p>{sportLabel(value.sport)} · {value.planned_duration_seconds===null?"Duración no disponible":durationLabel(value.planned_duration_seconds)}
      {value.planned_distance_meters!==null&&<> · {(value.planned_distance_meters/1000).toLocaleString("es-ES")} km</>}</p>
    <p>Estado de planificación: {statuses[value.status]}</p>
    <AppLink to="/calendar">Ver en el calendario</AppLink>
  </article>;
}
export function DailyOverviewContent({data}:{data:DailyOverview}){
  const copy=interpretationCopy(data.interpretation),goal=data.next_goal;
  const number=(value:string|number|null)=>value===null?"—":Number(value).toLocaleString("es-ES",{maximumFractionDigits:1});
  return <div className="daily-overview">
    <section className="dashboard-section daily-heading"><p className="eyebrow">Resumen de hoy</p>
      <h2><time dateTime={data.as_of_date}>{dateLabel(data.as_of_date)}</time></h2>
      <p>{data.today_sessions.length} {data.today_sessions.length===1?"sesión planificada":"sesiones planificadas"}</p>
    </section>
    <div className="daily-grid">
      <section className="dashboard-section" aria-labelledby="daily-state"><h2 id="daily-state">Tu estado</h2>
        <span className="status-badge">{copy.badge}</span><p>{copy.headline}</p>
        <dl className="daily-metrics">{([['Fitness',data.interpretation.fitness],['Fatiga',data.interpretation.fatigue],['Forma',data.interpretation.form]] as const).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{number(value)}</dd></div>)}</dl>
        {data.interpretation.data_date&&<p className="daily-caption">Datos del {dateLabel(data.interpretation.data_date)}</p>}
        <AppLink to="/statistics/training-status">Ver estado de forma</AppLink>
      </section>
      <section className="dashboard-section" aria-labelledby="daily-today"><h2 id="daily-today">Hoy</h2>
        {data.today_sessions.length?data.today_sessions.map(value=><Session key={value.id} value={value}/>):<p>No tienes sesiones planificadas para hoy.</p>}
      </section>
    </div>
    <ExecutionOverviewContent data={data.execution} timezone={data.timezone}/>
    <section aria-labelledby="daily-upcoming"><h2 id="daily-upcoming">Próximamente</h2><div className="daily-grid">
      <section className="dashboard-section" aria-labelledby="daily-next"><h3 id="daily-next">Próxima sesión</h3>
        {data.next_session?<><p><time dateTime={data.next_session.scheduled_date}>{dateLabel(data.next_session.scheduled_date)}</time></p><Session value={data.next_session}/></>:<p>No hay más sesiones planificadas actualmente.</p>}
      </section>
      <section className="dashboard-section" aria-labelledby="daily-goal"><h3 id="daily-goal">Próximo objetivo</h3>
        {goal?<><h4>{goal.name}</h4><p><time dateTime={goal.event_date}>{dateLabel(goal.event_date)}</time> · {goal.days_remaining} días restantes</p>
          <p>{categoryLabels[goal.event_category as keyof typeof categoryLabels]??goal.event_category} · Prioridad {goal.priority}</p>
          {goal.city&&<p>{goal.city}</p>}</>:<p>No tienes una competición futura configurada.</p>}
        <AppLink to="/calendar">Ver calendario y objetivos</AppLink>
      </section>
    </div></section>
  </div>;
}
