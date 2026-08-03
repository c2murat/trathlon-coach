import type { DailyTrainingLoadAggregate } from "../../../types/trainingLoad";
import { formatTrainingLoad, formatTrainingLoadDate } from "../../../utils/trainingLoadFormat";
import { ChartCard } from "./ChartCard";

type Props = { rows: DailyTrainingLoadAggregate[] };

export function DailyLoadChart({ rows }: Props) {
  const data = [...rows].sort((a, b) => a.local_date.localeCompare(b.local_date));
  const width = 760, height = 320;
  const padding = { top: 38, right: 28, bottom: 54, left: 58 };
  const plotWidth = width - padding.left - padding.right, plotHeight = height - padding.top - padding.bottom;
  const maximum = Math.max(...data.map((row) => row.total_load), 1);
  const scaleMaximum = Math.ceil(maximum / 25) * 25 || 25;
  const points = data.map((row, index) => ({ x: padding.left + index / Math.max(data.length - 1, 1) * plotWidth, y: padding.top + plotHeight - row.total_load / scaleMaximum * plotHeight }));
  const path = points.length ? points.slice(1).reduce((value, point, index) => { const previous = points[index]; return `${value} Q ${previous.x} ${previous.y} ${(previous.x + point.x) / 2} ${(previous.y + point.y) / 2}`; }, `M ${points[0].x} ${points[0].y}`) + (points.length > 1 ? ` T ${points.at(-1)!.x} ${points.at(-1)!.y}` : "") : "";
  const ticks = [0, .25, .5, .75, 1];
  const labelEvery = Math.max(1, Math.ceil(data.length / 7));

  return <ChartCard title="Evolución diaria" description="Carga diaria de entrenamiento.">
    {!data.length ? <p className="chart-empty">No hay carga diaria disponible.</p> : <div className="training-chart-scroll">
      <svg viewBox={`0 0 ${width} ${height}`} className="training-chart" role="img" aria-label="Gráfico de línea de carga diaria">
        <g className="training-chart__grid">{ticks.map((tick) => { const y = padding.top + plotHeight * (1 - tick); return <line key={tick} x1={padding.left} x2={width - padding.right} y1={y} y2={y} />; })}</g>
        <g className="training-chart__labels">{ticks.map((tick) => { const y = padding.top + plotHeight * (1 - tick); return <text key={tick} x={padding.left - 10} y={y + 4} textAnchor="end">{formatTrainingLoad(scaleMaximum * tick)}</text>; })}</g>
        <line className="training-chart__axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={padding.top + plotHeight} />
        <line className="training-chart__axis" x1={padding.left} x2={width - padding.right} y1={padding.top + plotHeight} y2={padding.top + plotHeight} />
        <path className="training-line-chart__area" d={`${path} L ${points.at(-1)!.x} ${padding.top + plotHeight} L ${points[0].x} ${padding.top + plotHeight} Z`} />
        <path className="training-line-chart__line" d={path} />
        {data.map((row, index) => {
          const label = `${formatTrainingLoadDate(row.local_date)}: ${formatTrainingLoad(row.total_load)} puntos de carga; resistencia ${formatTrainingLoad(row.endurance_load??row.total_load)}, fuerza ${formatTrainingLoad(row.strength_load??0)}, sesiones de fuerza ${row.strength_session_count??0}`;
          return <g key={row.id} className="training-chart__datum" tabIndex={0} role="img" aria-label={label}>
            <title>{label}</title>
            <circle className="training-line-chart__point-halo" cx={points[index].x} cy={points[index].y} r="10" />
            <circle className="training-line-chart__point" cx={points[index].x} cy={points[index].y} r="5" />
            <g className="training-chart__tooltip" transform={`translate(${points[index].x} ${Math.max(points[index].y - 16, 24)})`} aria-hidden="true">
              <rect x="-50" y="-23" width="100" height="20" rx="5" />
              <text x="0" y="-10" textAnchor="middle">{formatTrainingLoad(row.total_load)} pts total</text>
            </g>
            {(index % labelEvery === 0 || index === data.length - 1) && <text className="training-chart__x-label" x={points[index].x} y={height - 18} textAnchor="middle">{new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(`${row.local_date}T00:00:00Z`))}</text>}
          </g>;
        })}
      </svg>
    </div>}
  </ChartCard>;
}
