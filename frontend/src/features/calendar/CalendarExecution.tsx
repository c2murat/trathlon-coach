import { useState } from "react";
import { AppLink } from "../../app/usePathname";
import { activitySyncCompletedEvent } from "../../components/ActivitySyncButton";
import type { ApiClient } from "../../services/apiClient";
import type { ActivityLinkCandidate } from "../../types/planning";
import { formatDate, formatDistance } from "../../utils/format";
import type { CompletionStatus, ExecutionSessionView } from "../dashboard/executionOverviewTypes";
import {
  executionLongLabels,
  executionShortLabels,
  targetAdherenceText,
  unmatchedExplanation,
} from "../execution/executionPresentation";
import { durationLabel, sessionLabel, sportLabel } from "./planningFormat";
import "./calendarExecution.css";

const icons: Record<CompletionStatus, string> = {
  COMPLETED: "✓",
  PARTIAL: "●",
  OVER_DURATION: "↑",
  UNMATCHED: "—",
  UNKNOWN: "?",
};
const tones: Record<CompletionStatus, string> = {
  COMPLETED: "complete",
  PARTIAL: "partial",
  OVER_DURATION: "duration",
  UNMATCHED: "neutral",
  UNKNOWN: "neutral",
};
const shortDate = (value: string) => {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
};
const candidateDurationLabel = (seconds: number) => `${Math.round(seconds / 60)} min`;

export function ExecutionBadge({ value, compact = false }: { value?: ExecutionSessionView; compact?: boolean }) {
  const status = value?.evidence?.completion_status;
  if (!status) return null;
  const text = executionShortLabels[status];
  return (
    <span className={`calendar-execution-badge calendar-execution-badge--${tones[status]}`} title={text}>
      {compact ? (
        <span role="img" aria-label={text}>
          {icons[status]}
        </span>
      ) : (
        text
      )}
    </span>
  );
}

function ActivityLinker({
  value,
  client,
  athleteId,
  onLinked,
}: {
  value: ExecutionSessionView;
  client: ApiClient;
  athleteId?: string | null;
  onLinked?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [candidates, setCandidates] = useState<ActivityLinkCandidate[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const search = async () => {
    if (!client.plannedSessionActivityCandidates || busy) return;
    setBusy("search");
    setError("");
    setMessage("");
    try {
      const rows = await client.plannedSessionActivityCandidates(value.id);
      setCandidates(rows);
      setOpen(true);
    } catch {
      setError("No se han podido consultar las actividades candidatas.");
    } finally {
      setBusy("");
    }
  };

  const link = async (item: ActivityLinkCandidate) => {
    const manualStrength = item.source_type === "manual_strength";
    if (busy || (manualStrength && !client.linkPlannedSessionManualStrength) || (!manualStrength && !client.linkPlannedSessionActivity)) return;
    if (
      item.local_date !== value.date &&
      !window.confirm(`Vincular la actividad del ${shortDate(item.local_date)} con la sesión planificada del ${shortDate(value.date)}?`)
    )
      return;
    setBusy(item.id);
    setError("");
    setMessage("");
    try {
      if (manualStrength) await client.linkPlannedSessionManualStrength!(value.id, item.id);
      else await client.linkPlannedSessionActivity!(value.id, item.id);
      setMessage("Actividad vinculada. Actualizando ejecución.");
      window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent, { detail: { athleteId } }));
      onLinked?.();
    } catch {
      setError("No se ha podido vincular la actividad.");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="calendar-execution-linker">
      <button type="button" className="button button--small" disabled={Boolean(busy)} onClick={() => void search()}>
        {busy === "search" ? "Buscando…" : "Vincular actividad realizada"}
      </button>
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {open && (
        <div className="activity-candidates">
          {candidates.length === 0 ? (
            <p>No hay actividades compatibles esta semana.</p>
          ) : (
            candidates.map((item) => (
              <article key={item.id}>
                <h4>{item.name}</h4>
                <p>
                  {shortDate(item.local_date)} · {candidateDurationLabel(item.duration_seconds)}
                  {item.distance_meters !== null && <> · {formatDistance(item.distance_meters, item.sport)}</>}
                </p>
                <button type="button" className="button button--small" disabled={Boolean(busy)} onClick={() => void link(item)}>
                  {busy === item.id ? "Vinculando…" : "Vincular"}
                </button>
              </article>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export function CalendarExecutionDetail({
  value,
  timezone,
  client,
  athleteId,
  canManage = false,
  onLinked,
}: {
  value?: ExecutionSessionView;
  timezone: string;
  client?: ApiClient;
  athleteId?: string | null;
  canManage?: boolean;
  onLinked?: () => void;
}) {
  if (!value?.evidence) return null;
  const evidence = value.evidence;
  const targets = evidence.target_comparison;
  const canLinkActivity = Boolean(
    canManage &&
      client &&
      client.plannedSessionActivityCandidates &&
      evidence.completion_status === "UNMATCHED" &&
      value.activities.length === 0,
  );
  return (
    <details className="calendar-execution-detail">
      <summary>Ver ejecución de {sessionLabel(value.title)}</summary>
      <section aria-label={`Ejecución de ${sessionLabel(value.title)}`}>
        <h3>Ejecución</h3>
        <p>Estado: {executionShortLabels[evidence.completion_status]}</p>
        <p>
          <strong>Planificado: </strong>
          {sportLabel(value.sport)} · {sessionLabel(value.title)} ·{" "}
          {value.planned_duration_seconds === null ? "Duración no disponible" : durationLabel(value.planned_duration_seconds)}
          {value.planned_distance_meters !== null && <> · {formatDistance(value.planned_distance_meters, value.sport)}</>}
        </p>
        {evidence.completion_status === "UNMATCHED" && (
          <p>
            {executionLongLabels.UNMATCHED}. {unmatchedExplanation}
          </p>
        )}
        {canLinkActivity && <ActivityLinker value={value} client={client!} athleteId={athleteId} onLinked={onLinked} />}
        {value.activities.length > 0 && (
          <p>
            <strong>Realizado: </strong>
            {evidence.actual_duration_seconds === null ? "Duración no disponible" : durationLabel(evidence.actual_duration_seconds)}
            {evidence.actual_distance_m !== null && <> · {formatDistance(Number(evidence.actual_distance_m), value.sport)}</>}
          </p>
        )}
        {evidence.sport_match === false && <p>Hay actividades vinculadas de un deporte distinto; la comparación es limitada.</p>}
        {value.activities.map((activity) => {
          const provenance = evidence.link_provenance.find((item) => item.activity_id === activity.id);
          return (
            <article key={activity.id}>
              <h4>{activity.name}</h4>
              <p>
                {formatDate(activity.started_at, timezone)} · {durationLabel(activity.duration_seconds)}
                {activity.distance_meters !== null && <> · {formatDistance(activity.distance_meters, activity.sport)}</>}
              </p>
              {provenance && (
                <p>{provenance.match_source === "manual" ? "Actividad vinculada manualmente" : "Actividad vinculada automáticamente"}</p>
              )}
              <AppLink to={`/activities/${activity.id}`}>Ver actividad</AppLink>
            </article>
          );
        })}
        {value.workout && (
          <div>
            <h4>Cumplimiento de objetivos</h4>
            <p>{targetAdherenceText(targets)}</p>
            {targets && !["LOW", "INSUFFICIENT"].includes(targets.confidence) && (
              <p>
                Repeticiones comparadas: {targets.matched_repetitions} de {targets.planned_repetitions}.
              </p>
            )}
          </div>
        )}
      </section>
    </details>
  );
}
