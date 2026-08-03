import { useCallback, useEffect, useMemo, useState } from "react";
import type { ApiClient } from "../../services/apiClient";
import type {
  DailyTrainingLoadAggregate,
  WeeklyTrainingLoadAggregate,
} from "../../types/trainingLoad";
import {normalizeTrainingLoad} from "../../types/trainingLoad";
import {
  formatIsoWeekLabel,
  formatTrainingDuration,
  formatTrainingLoad,
  formatTrainingLoadDate,
  getTrainingLoadCoverageLabel,
} from "../../utils/trainingLoadFormat";
import { DailyLoadChart } from "./components/DailyLoadChart";
import { CalculationReliabilityHelp } from "./components/CalculationReliabilityHelp";
import { SummaryCard } from "./components/SummaryCard";
import { QualityBadge } from "./components/QualityBadge";
import { WeeklyLoadChart } from "./components/WeeklyLoadChart";

const PERIOD_OPTIONS = [4, 8, 12] as const;

function formatDateParameter(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function getDateRange(weeks: number) {
  const endDate = new Date();
  const startDate = new Date(endDate);

  startDate.setDate(endDate.getDate() - weeks * 7 + 1);

  return {
    startDate: formatDateParameter(startDate),
    endDate: formatDateParameter(endDate),
    timezoneName: "Europe/Madrid",
  };
}

export function TrainingLoadPage({ client }: { client: ApiClient }) {
  const [weeks, setWeeks] = useState(4);
  const [daily, setDaily] = useState<DailyTrainingLoadAggregate[]>([]);
  const [weekly, setWeekly] = useState<WeeklyTrainingLoadAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const range = useMemo(() => getDateRange(weeks), [weeks]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);

    try {
      const [dailyResponse, weeklyResponse] = await Promise.all([
        client.getDailyTrainingLoad?.(range),
        client.getWeeklyTrainingLoad?.(range),
      ]);

      if (!dailyResponse || !weeklyResponse) {
        throw new Error("La API de carga no está disponible.");
      }

      setDaily(dailyResponse.map(normalizeTrainingLoad));
      setWeekly(weeklyResponse.map(normalizeTrainingLoad));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [client, range]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalLoad = daily.reduce(
    (total, row) => total + row.total_load,
    0,
  );
  const enduranceLoad=daily.reduce((total,row)=>total+(row.endurance_load??row.total_load),0);
  const strengthLoad=daily.reduce((total,row)=>total+(row.strength_load??0),0);
  const strengthSessions=daily.reduce((total,row)=>total+(row.strength_session_count??0),0);

  const activityCount = daily.reduce(
    (total, row) => total + row.loaded_activity_count,
    0,
  );

  const totalDuration = daily.reduce(
    (total, row) => total + row.total_duration_seconds,
    0,
  );

  const weeklyAverage = weekly.length
    ? weekly.reduce((total, row) => total + row.total_load, 0) /
      weekly.length
    : 0;

  const hasData = daily.length > 0 || weekly.length > 0;

  return (
    <article className="training-load-page">
      <header className="training-load-header">
        <div>
          <p className="training-load-eyebrow">Estadísticas</p>
          <h1>Carga de entrenamiento</h1>
          <p className="training-load-introduction">
            Consulta la evolución diaria y semanal de la carga generada por tus
            actividades.
          </p>
        </div>

        <div className="training-load-period">
          <label htmlFor="training-load-period">Periodo</label>

          <select
            id="training-load-period"
            value={weeks}
            onChange={(event) => setWeeks(Number(event.target.value))}
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option} value={option}>
                Últimas {option} semanas
              </option>
            ))}
          </select>

          <span>
            {formatTrainingLoadDate(range.startDate)}
            {" – "}
            {formatTrainingLoadDate(range.endDate)}
          </span>
        </div>
      </header>

      {loading && (
        <section className="training-load-state" role="status">
          <strong>Cargando carga de entrenamiento…</strong>
        </section>
      )}

      {error && !loading && (
        <section
          className="training-load-state training-load-state--error"
          role="alert"
        >
          <strong>No se ha podido cargar la carga de entrenamiento.</strong>

          <button
            className="button button--primary"
            type="button"
            onClick={() => void load()}
          >
            Reintentar
          </button>
        </section>
      )}

      {!loading && !error && !hasData && (
        <section className="training-load-state">
          <strong>No hay datos de carga para este periodo.</strong>
          <span>
            Primero deben existir cargas individuales calculadas y agregadas.
          </span>
        </section>
      )}

      {!loading && !error && hasData && (
        <>
          <section
            className="training-load-summary"
            aria-label="Resumen de carga de entrenamiento"
          >
            <SummaryCard
              icon="load"
              label="Carga total"
              value={formatTrainingLoad(totalLoad)}
              detail={`Acumulada en ${weeks} semanas`}
              variant="primary"
            />

            <SummaryCard
              icon="activity"
              label="Resistencia"
              value={formatTrainingLoad(enduranceLoad)}
              detail={`${activityCount} actividades con carga`}
              variant="activity"
            />
            <SummaryCard icon="load" label="Fuerza" value={formatTrainingLoad(strengthLoad)} detail="Carga de fuerza acumulada" variant="average" />
            <SummaryCard icon="activity" label="Sesiones de fuerza" value={String(strengthSessions)} detail="En el periodo seleccionado" variant="duration" />

            <SummaryCard
              icon="duration"
              label="Tiempo total"
              value={formatTrainingDuration(totalDuration)}
              detail="Duración acumulada"
              variant="duration"
            />

            <SummaryCard
              icon="average"
              label="Promedio semanal"
              value={formatTrainingLoad(weeklyAverage)}
              detail="Carga media por semana"
              variant="average"
            />
          </section>

          <section className="training-load-charts">
            <DailyLoadChart rows={daily} />
            <WeeklyLoadChart rows={weekly} />
          </section>

          <section className="training-load-tables">
            <LoadTable rows={daily} weekly={false} />
            <LoadTable rows={weekly} weekly />
          </section>
        </>
      )}
    </article>
  );
}

function LoadTable({
  rows,
  weekly,
}: {
  rows: (DailyTrainingLoadAggregate | WeeklyTrainingLoadAggregate)[];
  weekly: boolean;
}) {
  const sortedRows = [...rows].sort((first, second) => {
    const firstDate = weekly
      ? (first as WeeklyTrainingLoadAggregate).week_start_date
      : (first as DailyTrainingLoadAggregate).local_date;

    const secondDate = weekly
      ? (second as WeeklyTrainingLoadAggregate).week_start_date
      : (second as DailyTrainingLoadAggregate).local_date;

    return secondDate.localeCompare(firstDate);
  });

  return (
    <section className="training-load-table-card">
      <header className="training-load-table-card__header">
        <div>
          <h2>{weekly ? "Detalle semanal" : "Detalle diario"}</h2>
          <p>
            {weekly
              ? "Resumen de los agregados por semana ISO."
              : "Detalle de los días con carga calculada."}
          </p>
        </div>

        <span>
          {sortedRows.length}{" "}
          {sortedRows.length === 1 ? "registro" : "registros"}
        </span>
      </header>

      {!sortedRows.length ? (
        <p className="training-load-table-empty">
          {weekly
            ? "No hay carga semanal disponible para este periodo."
            : "No hay carga diaria disponible para este periodo."}
        </p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>{weekly ? "Semana" : "Fecha"}</th>
                <th>Carga</th>
                <th>Actividades</th>
                <th>Duración</th>
                <th>Cobertura de datos</th>
                <th><span className="label-with-help">Fiabilidad del cálculo <CalculationReliabilityHelp /></span></th>
              </tr>
            </thead>

            <tbody>
              {sortedRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    {weekly
                      ? formatIsoWeekLabel(
                          (row as WeeklyTrainingLoadAggregate).iso_year,
                          (row as WeeklyTrainingLoadAggregate).iso_week,
                        )
                      : formatTrainingLoadDate(
                          (row as DailyTrainingLoadAggregate).local_date,
                        )}
                  </td>

                  <td>
                    <strong>{formatTrainingLoad(row.total_load)}</strong>
                  </td>

                  <td>{row.loaded_activity_count}</td>

                  <td>
                    {formatTrainingDuration(row.total_duration_seconds)}
                  </td>

                  <td>
                    <span className="training-load-badge">
                      {getTrainingLoadCoverageLabel(row.coverage)}
                    </span>
                  </td>

                  <td><QualityBadge quality={row.quality} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}





