import type { DailyTrainingStatus } from "../../../types/trainingStatus";
import { formatDailyLoad, formatForm, formatHistoryDay, formatStatusDate, formatStatusValue } from "../trainingStatusFormat";

const SERIES = [{ key: "fitness", label: "Fitness" }, { key: "fatigue", label: "Fatiga" }, { key: "form", label: "Forma" }] as const;

export function TrainingStatusChart({ rows }: { rows: DailyTrainingStatus[] }) {
  const data = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  if (!data.length) return <section className="status-chart-card"><h2>Evolución del fitness, la fatiga y la forma</h2><p>No hay estados en el intervalo seleccionado.</p></section>;
  const width = 900, height = 390;
  const padding = { top: 35, right: 24, bottom: 62, left: 62 };
  const plotWidth = width - padding.left - padding.right, plotHeight = height - padding.top - padding.bottom;
  const values = data.flatMap((row) => [row.fitness, row.fatigue, row.form, 0]);
  const rawMin = Math.min(...values), rawMax = Math.max(...values), span = Math.max(rawMax - rawMin, 1);
  const minimum = rawMin - span * .1, maximum = rawMax + span * .1, scale = maximum - minimum;
  const x = (index: number) => padding.left + index / Math.max(data.length - 1, 1) * plotWidth;
  const y = (value: number) => padding.top + (maximum - value) / scale * plotHeight;
  const ticks = [0, .25, .5, .75, 1], labelEvery = Math.max(1, Math.ceil(data.length / 7));
  return <section className="status-chart-card">
    <header><div><h2>Evolución del fitness, la fatiga y la forma</h2><p>Valores diarios de carga matemática suavizada.</p></div>
      <ul className="status-chart-legend" aria-label="Series del gráfico">{SERIES.map((series) => <li key={series.key} data-series={series.key}>{series.label}</li>)}</ul>
    </header>
    <svg className="status-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Gráfico diario del fitness, la fatiga y la forma">
      <text className="status-chart__axis-title" x="16" y="20">Valor</text>
      <g className="training-chart__grid">{ticks.map((tick) => { const position = padding.top + plotHeight * tick; return <line key={tick} x1={padding.left} x2={width-padding.right} y1={position} y2={position}/>; })}</g>
      <g className="training-chart__labels">{ticks.map((tick) => { const value=maximum-scale*tick, position=padding.top+plotHeight*tick; return <text key={tick} x={padding.left-10} y={position+4} textAnchor="end">{formatStatusValue(value)}</text>; })}</g>
      <line className="training-chart__axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={padding.top+plotHeight}/>
      <line className="training-chart__axis" x1={padding.left} x2={width-padding.right} y1={padding.top+plotHeight} y2={padding.top+plotHeight}/>
      <line className="status-chart__zero" x1={padding.left} x2={width-padding.right} y1={y(0)} y2={y(0)}/>
      {SERIES.map((series) => <polyline key={series.key} className={`status-chart__line status-chart__line--${series.key}`} points={data.map((row,index)=>`${x(index)},${y(row[series.key])}`).join(" ")} aria-hidden="true"/>)}
      {data.map((row,index) => {
        const label=[formatStatusDate(row.date),`Carga: ${formatDailyLoad(row.total_load)}`,`Fitness: ${formatStatusValue(row.fitness)}`,`Fatiga: ${formatStatusValue(row.fatigue)}`,`Forma: ${formatForm(row.form)}`,formatHistoryDay(row.history_day_number),row.is_warmup?"En adaptación":"Historial consolidado"].join("; ");
        return <g key={row.date} className="status-chart__datum" tabIndex={0} role="img" aria-label={label}><title>{label}</title><rect x={x(index)-12} y={padding.top} width="24" height={plotHeight} fill="transparent"/>
          {SERIES.map((series)=><circle key={series.key} className={`status-chart__point status-chart__point--${series.key}`} cx={x(index)} cy={y(row[series.key])} r="4"/>)}
          {(index%labelEvery===0||index===data.length-1)&&<text className="training-chart__x-label" x={x(index)} y={height-22} textAnchor="middle">{new Intl.DateTimeFormat("es-ES",{day:"2-digit",month:"short",timeZone:"UTC"}).format(new Date(`${row.date}T00:00:00Z`))}</text>}
        </g>;
      })}
      <text className="status-chart__axis-title" x={width/2} y={height-3} textAnchor="middle">Fecha</text>
    </svg>
  </section>;
}
