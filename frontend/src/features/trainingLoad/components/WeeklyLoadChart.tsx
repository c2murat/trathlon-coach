import type { WeeklyTrainingLoadAggregate } from "../../../types/trainingLoad";
import { formatIsoWeekLabel, formatTrainingLoad } from "../../../utils/trainingLoadFormat";
import { ChartCard } from "./ChartCard";

type Props = { rows: WeeklyTrainingLoadAggregate[] };

export function WeeklyLoadChart({ rows }: Props) {
  const data = [...rows].sort((a, b) => a.week_start_date.localeCompare(b.week_start_date));
  const width = 760, height = 320;
  const padding = { top: 42, right: 28, bottom: 54, left: 58 };
  const plotWidth = width - padding.left - padding.right, plotHeight = height - padding.top - padding.bottom;
  const maximum = Math.max(...data.map((row) => row.total_load), 1);
  const scaleMaximum = Math.ceil(maximum / 50) * 50 || 50;
  const slot = plotWidth / Math.max(data.length, 1), barWidth = Math.min(62, slot * .58);
  const ticks = [0, .25, .5, .75, 1];

  return <ChartCard title="Evolución semanal" description="Comparación de la carga acumulada por semana ISO.">
    {!data.length ? <p className="chart-empty">No hay carga semanal disponible.</p> : <div className="training-chart-scroll">
      <svg viewBox={`0 0 ${width} ${height}`} className="training-chart" role="img" aria-label="Gráfico de barras de carga semanal">
        <g className="training-chart__grid">{ticks.map((tick) => { const y = padding.top + plotHeight * (1 - tick); return <line key={tick} x1={padding.left} x2={width - padding.right} y1={y} y2={y} />; })}</g>
        <g className="training-chart__labels">{ticks.map((tick) => { const y = padding.top + plotHeight * (1 - tick); return <text key={tick} x={padding.left - 10} y={y + 4} textAnchor="end">{formatTrainingLoad(scaleMaximum * tick)}</text>; })}</g>
        <line className="training-chart__axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={padding.top + plotHeight} />
        <line className="training-chart__axis" x1={padding.left} x2={width - padding.right} y1={padding.top + plotHeight} y2={padding.top + plotHeight} />
        {data.map((row, index) => {
          const barHeight = row.total_load / scaleMaximum * plotHeight;
          const x = padding.left + index * slot + (slot - barWidth) / 2;
          const y = padding.top + plotHeight - barHeight;
          const label = `${formatIsoWeekLabel(row.iso_year, row.iso_week)}: ${formatTrainingLoad(row.total_load)} puntos de carga; resistencia ${formatTrainingLoad(row.endurance_load??row.total_load)}, fuerza ${formatTrainingLoad(row.strength_load??0)}, sesiones de fuerza ${row.strength_session_count??0}`;
          const strengthHeight=(row.strength_load??0)/scaleMaximum*plotHeight;
          return <g key={row.id} className="training-chart__datum" tabIndex={0} role="img" aria-label={label}>
            <title>{label}</title>
            <rect x={x} y={y} width={barWidth} height={Math.max(barHeight, 2)} rx="8" className="training-bar-chart__bar" />
            {strengthHeight>0&&<rect x={x} y={padding.top+plotHeight-strengthHeight} width={barWidth} height={strengthHeight} rx="4" className="training-bar-chart__strength" />}
            <g className="training-chart__tooltip" transform={`translate(${x + barWidth / 2} ${Math.max(y - 6, 28)})`} aria-hidden="true">
              <rect x="-50" y="-23" width="100" height="20" rx="5" />
              <text x="0" y="-10" textAnchor="middle">{formatTrainingLoad(row.total_load)} pts</text>
            </g>
            <text x={x + barWidth / 2} y={Math.max(y - 8, 15)} textAnchor="middle" className="training-bar-chart__value">{formatTrainingLoad(row.total_load)}</text>
            <text x={x + barWidth / 2} y={height - 18} textAnchor="middle" className="training-chart__x-label">S{row.iso_week}</text>
          </g>;
        })}
      </svg>
    </div>}
  </ChartCard>;
}
