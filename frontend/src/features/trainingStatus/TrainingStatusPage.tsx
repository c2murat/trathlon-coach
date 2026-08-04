import { useEffect, useMemo, useRef, useState } from "react";
import type { ApiClient } from "../../services/apiClient";
import type { DailyTrainingStatus, TrainingStatusPeriodWeeks } from "../../types/trainingStatus";
import { TRAINING_STATUS_PERIODS } from "../../types/trainingStatus";
import { StatusSummaryCard } from "./components/StatusSummaryCard";
import { TrainingStatusChart } from "./components/TrainingStatusChart";
import { WarmupNotice } from "./components/WarmupNotice";
import { formatCalculatedAt, formatDailyLoad, formatForm, formatStatusDate, formatStatusValue, getBrowserTimezone, getTrainingStatusRange } from "./trainingStatusFormat";

const VERSIONS = { trainingLoadAlgorithmVersion:"0.7b.1", manualStrengthAlgorithmVersion:"0.7e.1", trainingStatusAlgorithmVersion:"0.7f.1" };

export function TrainingStatusPage({ client, canRecalculate=true }: { client: ApiClient; canRecalculate?:boolean }) {
  const [weeks,setWeeks]=useState<TrainingStatusPeriodWeeks>(4);
  const [rows,setRows]=useState<DailyTrainingStatus[]>([]);
  const [latest,setLatest]=useState<DailyTrainingStatus|null>(null);
  const [loading,setLoading]=useState(true);
  const [queryError,setQueryError]=useState(false);
  const [recalculating,setRecalculating]=useState(false);
  const [recalculationError,setRecalculationError]=useState("");
  const [announcement,setAnnouncement]=useState("");
  const [noSources,setNoSources]=useState(false);
  const requestId=useRef(0);
  const timezoneName=useMemo(getBrowserTimezone,[]);
  const range=useMemo(()=>getTrainingStatusRange(weeks),[weeks]);
  const query={...range,timezoneName,...VERSIONS};

  useEffect(()=>{
    const id=++requestId.current;
    setLoading(true);setQueryError(false);setNoSources(false);
    if(!client.listTrainingStatus||!client.getLatestTrainingStatus){setQueryError(true);setLoading(false);return}
    Promise.all([client.listTrainingStatus(query),client.getLatestTrainingStatus(query)])
      .then(([series,current])=>{if(id===requestId.current){setRows(series);setLatest(current)}})
      .catch(()=>{if(id===requestId.current)setQueryError(true)})
      .finally(()=>{if(id===requestId.current)setLoading(false)});
  },[client,weeks]);

  async function recalculate(){
    if(recalculating||!client.recalculateTrainingStatus)return;
    setRecalculating(true);setRecalculationError("");setAnnouncement("");setNoSources(false);
    try{
      const series=await client.recalculateTrainingStatus(query);
      const current=client.getLatestTrainingStatus?await client.getLatestTrainingStatus(query):(series.at(-1)??null);
      setRows(series);setLatest(current);
      if(!series.length){setNoSources(true);setAnnouncement("No hay carga de entrenamiento disponible.");}
      else setAnnouncement("Estado de entrenamiento recalculado correctamente.");
    }catch{setRecalculationError("No se ha podido recalcular el estado de entrenamiento.");}
    finally{setRecalculating(false)}
  }

  const globallyEmpty=!latest&&!rows.length;
  return <article className="training-status-page">
    <header className="status-page-header">
      <div><p className="training-load-eyebrow">Estadísticas</p><h1>Estado de entrenamiento</h1><p>Consulta la evolución matemática del fitness, la fatiga y la forma.</p></div>
      <div className="status-page-actions">
        <label htmlFor="training-status-period">Periodo</label>
        <select id="training-status-period" value={weeks} onChange={(event)=>setWeeks(Number(event.target.value) as TrainingStatusPeriodWeeks)}>
          {TRAINING_STATUS_PERIODS.map(value=><option key={value} value={value}>Últimas {value} semanas</option>)}
        </select>
        <span>{formatStatusDate(range.startDate)} – {formatStatusDate(range.endDate)}</span>
        {canRecalculate&&!globallyEmpty&&<button className="button button--primary" disabled={recalculating} onClick={()=>void recalculate()}>{recalculating?"Recalculando…":"Recalcular el estado"}</button>}
      </div>
    </header>
    <div className="status-announcement" aria-live="polite">{announcement}</div>
    {loading&&<section className="training-load-state" role="status"><strong>Cargando estado de entrenamiento…</strong></section>}
    {!loading&&queryError&&<section className="training-load-state training-load-state--error" role="alert"><strong>No se ha podido consultar el estado de entrenamiento.</strong></section>}
    {!loading&&!queryError&&globallyEmpty&&!noSources&&<section className="training-load-state status-empty"><h2>Todavía no hay un estado de entrenamiento calculado</h2><p>Calcula el estado para obtener la evolución del fitness, la fatiga y la forma a partir de tu carga diaria.</p>{canRecalculate&&<button className="button button--primary" disabled={recalculating} onClick={()=>void recalculate()}>Calcular estado de entrenamiento</button>}</section>}
    {!loading&&!queryError&&noSources&&<section className="training-load-state status-empty"><h2>No hay carga de entrenamiento disponible</h2><p>Registra o importa entrenamientos antes de calcular el estado.</p></section>}
    {recalculationError&&<p className="status-recalculation-error" role="alert" aria-live="assertive">{recalculationError}</p>}
    {!loading&&!queryError&&latest&&<>
      <section className="status-summary-grid" aria-label="Estado más reciente">
        <StatusSummaryCard label="Fitness" value={formatStatusValue(latest.fitness)} detail="Carga crónica suavizada a medio plazo" variant="fitness"/>
        <StatusSummaryCard label="Fatiga" value={formatStatusValue(latest.fatigue)} detail="Carga aguda suavizada de los últimos días" variant="fatigue"/>
        <StatusSummaryCard label="Forma" value={formatForm(latest.form)} detail="Diferencia entre el fitness y la fatiga" variant="form"/>
        <StatusSummaryCard label="Carga del día" value={formatDailyLoad(latest.total_load)} detail={formatStatusDate(latest.date)} variant="load"/>
      </section>
      <WarmupNotice status={latest}/>
      <TrainingStatusChart rows={rows}/>
      <details className="status-interpretation"><summary>Cómo interpretar estos datos</summary><p>El fitness representa la carga crónica suavizada. La fatiga representa la carga aguda suavizada. La forma es la diferencia entre el fitness y la fatiga.</p><p>Una forma negativa indica que la fatiga calculada supera al fitness; una forma positiva indica lo contrario.</p><p>Estos indicadores describen una estimación matemática de la carga y no sustituyen las sensaciones personales, el descanso, la salud ni el criterio profesional.</p></details>
      <footer className="status-technical"><span>Última actualización: {formatCalculatedAt(latest.calculated_at)}</span><span>Modelo {latest.training_status_algorithm_version}</span><span>Carga {latest.training_load_algorithm_version}</span><span>Fuerza {latest.manual_strength_algorithm_version}</span></footer>
    </>}
    {!loading&&!queryError&&!globallyEmpty&&latest&&rows.length===0&&<p className="status-interval-empty">No hay estados en el intervalo seleccionado; se muestra el estado más reciente.</p>}
  </article>;
}
