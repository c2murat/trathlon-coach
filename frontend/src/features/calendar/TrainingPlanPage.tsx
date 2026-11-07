import { useEffect, useMemo, useRef, useState } from "react";
import { AppLink } from "../../app/usePathname";
import { activitySyncCompletedEvent } from "../../components/ActivitySyncButton";
import type { ApiClient } from "../../services/apiClient";
import type {
  ActivityLinkCandidate,
  PlannedSessionActivityLink,
  TrainingPlan,
  TrainingPlanSession,
} from "../../types/planning";
import { formatDate } from "../../utils/format";
import { dateLabel } from "./competitionLabels";
import { durationLabel, errorMessage, sportLabel } from "./planningFormat";
import { WorkoutDetail } from "./PlanningFlowPages";

const statusLabels: Record<string, string> = {
  draft: "Borrador",
  active: "Activo",
  completed: "Completado",
  archived: "Archivado",
};

const idFromPath = () => window.location.pathname.split("/").filter(Boolean).at(-1) ?? "";
const activityDuration = (seconds: number) => `${Math.round(seconds / 60)} min`;
const activityDistance = (meters: number | null) =>
  meters == null ? "" : ` · ${(meters / 1000).toLocaleString("es-ES", { maximumFractionDigits: 1 })} km`;
const isoDate = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

function weekDates(date: string) {
  const value = new Date(`${date}T12:00:00`);
  const day = (value.getDay() + 6) % 7;
  const monday = new Date(value);
  monday.setDate(value.getDate() - day);
  return Array.from({ length: 7 }, (_, index) => {
    const item = new Date(monday);
    item.setDate(monday.getDate() + index);
    return isoDate(item);
  });
}

function dispatchPlanningRefresh(athleteId: string) {
  window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent, { detail: { athleteId } }));
}

function ActivityLinks({
  client,
  athleteId,
  session,
  canManage,
}: {
  client: ApiClient;
  athleteId: string;
  session: TrainingPlanSession;
  canManage: boolean;
}) {
  const [links, setLinks] = useState<PlannedSessionActivityLink[]>([]);
  const [candidates, setCandidates] = useState<ActivityLinkCandidate[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const lock = useRef(false);

  useEffect(() => {
    const run = ++generation.current;
    setLinks([]);
    setCandidates([]);
    setOpen(false);
    setBusy("");
    setError("");
    setMessage("");
    lock.current = false;
    Promise.resolve(client.plannedSessionActivityLinks?.(session.id) ?? [])
      .then((value) => {
        if (run === generation.current) setLinks(value);
      })
      .catch((cause) => {
        if (run === generation.current) setError(errorMessage(cause));
      });
    return () => {
      generation.current++;
    };
  }, [client, athleteId, session.id]);

  const search = async () => {
    if (lock.current || !client.plannedSessionActivityCandidates) return;
    lock.current = true;
    setBusy("search");
    setError("");
    setMessage("");
    try {
      setCandidates(await client.plannedSessionActivityCandidates(session.id));
      setOpen(true);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      lock.current = false;
      setBusy("");
    }
  };

  const link = async (item: ActivityLinkCandidate) => {
    const manualStrength = item.source_type === "manual_strength";
    if (
      lock.current ||
      (manualStrength && !client.linkPlannedSessionManualStrength) ||
      (!manualStrength && !client.linkPlannedSessionActivity)
    )
      return;
    lock.current = true;
    setBusy(`link:${item.id}`);
    setError("");
    try {
      const value = manualStrength
        ? await client.linkPlannedSessionManualStrength!(session.id, item.id)
        : await client.linkPlannedSessionActivity!(session.id, item.id);
      setLinks((current) => (current.some((existing) => existing.id === value.id) ? current : [...current, value]));
      setCandidates((current) => current.filter((candidate) => candidate.id !== item.id));
      dispatchPlanningRefresh(athleteId);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      lock.current = false;
      setBusy("");
    }
  };

  const unlink = async (activityId: string) => {
    if (
      lock.current ||
      !client.unlinkPlannedSessionActivity ||
      !window.confirm("¿Desvincular esta actividad?")
    )
      return;
    lock.current = true;
    setBusy(`unlink:${activityId}`);
    setError("");
    try {
      await client.unlinkPlannedSessionActivity(session.id, activityId);
      setLinks((current) => current.filter((item) => item.completed_activity_id !== activityId));
      dispatchPlanningRefresh(athleteId);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      lock.current = false;
      setBusy("");
    }
  };

  const automatic = async () => {
    if (lock.current || !client.autoMatchPlannedSessionActivity) return;
    lock.current = true;
    setBusy("auto");
    setError("");
    setMessage("");
    try {
      const result = await client.autoMatchPlannedSessionActivity(session.id);
      if (result.link) {
        setLinks((current) =>
          current.some((item) => item.id === result.link!.id) ? current : [...current, result.link!],
        );
        dispatchPlanningRefresh(athleteId);
      } else if (result.classification === "ambiguous") {
        setCandidates(result.candidates);
        setOpen(true);
        setMessage("Hemos encontrado varias actividades posibles. Selecciona la correcta.");
      } else setMessage("No hemos encontrado una coincidencia segura.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      lock.current = false;
      setBusy("");
    }
  };

  return (
    <section className="planned-activity-links">
      <h4>Actividad realizada</h4>
      {links.length === 0 ? (
        <p>No hay una actividad vinculada.</p>
      ) : (
        links.map((item) => (
          <div key={item.id} className="planned-activity-link">
            <p>
              {sportLabel(item.activity.sport)} · {activityDuration(item.activity.duration_seconds)}
              {activityDistance(item.activity.distance_meters)}
            </p>
            <small>Vinculada {item.match_source === "manual" ? "manualmente" : "automáticamente"}</small>
            <div>
              {item.completed_activity_id ? (
                <AppLink className="button button--small" to={`/activities/${item.completed_activity_id}`}>
                  Ver actividad
                </AppLink>
              ) : (
                <span className="read-only-note">Actividad manual registrada</span>
              )}
              {canManage && item.completed_activity_id && (
                <button
                  type="button"
                  className="button button--small"
                  disabled={Boolean(busy)}
                  onClick={() => void unlink(item.completed_activity_id!)}
                >
                  {busy === `unlink:${item.completed_activity_id}` ? "Desvinculando…" : "Desvincular"}
                </button>
              )}
            </div>
          </div>
        ))
      )}
      {canManage && (
        <div>
          <button type="button" className="button button--small" disabled={Boolean(busy)} onClick={() => void search()}>
            {busy === "search" ? "Buscando…" : "Buscar actividad"}
          </button>
          <button type="button" className="button button--small" disabled={Boolean(busy)} onClick={() => void automatic()}>
            {busy === "auto" ? "Buscando…" : "Buscar coincidencia automática"}
          </button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {open && (
        <div className="activity-candidates">
          {candidates.length === 0 ? (
            <p>No hay candidatas razonables.</p>
          ) : (
            candidates.map((item) => (
              <div key={item.id}>
                <p>
                  {sportLabel(item.sport)} · {formatDate(item.started_at, item.timezone)} ·{" "}
                  {activityDuration(item.duration_seconds)}
                  {activityDistance(item.distance_meters)}
                </p>
                <small>{item.confidence === "high" ? "Coincidencia alta" : "Coincidencia posible"}</small>
                {canManage && (
                  <button
                    type="button"
                    className="button button--small"
                    disabled={Boolean(busy)}
                    onClick={() => void link(item)}
                  >
                    {busy === `link:${item.id}` ? "Vinculando…" : "Vincular"}
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
}

function ScheduleChange({
  client,
  athleteId,
  session,
  canManage,
  mutable,
  allSessions,
  onScheduledDateChange,
}: {
  client: ApiClient;
  athleteId: string;
  session: TrainingPlanSession;
  canManage: boolean;
  mutable: boolean;
  allSessions: TrainingPlanSession[];
  onScheduledDateChange: (sessionId: string, date: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const dates = useMemo(() => weekDates(session.scheduled_date), [session.scheduled_date]);

  if (!canManage || !mutable) return null;

  const reschedule = async (date: string) => {
    if (busy || date === session.scheduled_date || !client.reschedulePlannedSession) return;
    setBusy(date);
    setError("");
    setMessage("");
    try {
      const value = await client.reschedulePlannedSession(session.id, date);
      onScheduledDateChange(session.id, value.scheduled_date);
      setMessage("Día actualizado.");
      dispatchPlanningRefresh(athleteId);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="planned-activity-links">
      <h4>Reprogramación</h4>
      <button type="button" className="button button--small" disabled={Boolean(busy)} onClick={() => setOpen((value) => !value)}>
        Cambiar día
      </button>
      {open && (
        <div className="activity-candidates">
          {dates.map((date) => {
            const conflicts = allSessions.filter((item) => item.id !== session.id && item.scheduled_date === date).length;
            return (
              <div key={date}>
                <p>
                  <time dateTime={date}>{dateLabel(date)}</time>
                  {conflicts > 0
                    ? ` · Ya hay ${conflicts} sesión${conflicts === 1 ? "" : "es"} planificada${conflicts === 1 ? "" : "s"} ese día.`
                    : ""}
                </p>
                <button
                  type="button"
                  className="button button--small"
                  disabled={Boolean(busy) || date === session.scheduled_date}
                  onClick={() => void reschedule(date)}
                >
                  {busy === date ? "Guardando…" : date === session.scheduled_date ? "Día actual" : "Mover aquí"}
                </button>
              </div>
            );
          })}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
    </section>
  );
}

export function TrainingPlanPage({
  client,
  athleteId,
  canManage = false,
}: {
  client: ApiClient;
  athleteId: string;
  canManage?: boolean;
}) {
  const id = idFromPath();
  const [plan, setPlan] = useState<TrainingPlan | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"activate" | "complete" | "archive" | null>(null);
  const generation = useRef(0);
  const submitLock = useRef(false);

  useEffect(() => {
    const run = ++generation.current;
    setPlan(null);
    setError("");
    setBusy(null);
    submitLock.current = false;
    (client.trainingPlan?.(id) ?? Promise.reject(new Error("404")))
      .then((value) => {
        if (run === generation.current) setPlan(value);
      })
      .catch((cause) => {
        if (run === generation.current) setError(errorMessage(cause));
      });
    return () => {
      generation.current++;
    };
  }, [client, id, athleteId]);

  const weeks = useMemo(() => {
    const map = new Map<string, TrainingPlan["sessions"]>();
    for (const session of plan?.sessions ?? []) {
      const key = weekDates(session.scheduled_date)[0];
      map.set(key, [...(map.get(key) ?? []), session]);
    }
    return [...map].map(
      ([week, sessions]) =>
        [week, [...sessions].sort((left, right) => left.scheduled_date.localeCompare(right.scheduled_date))] as const,
    );
  }, [plan]);

  const transition = async (action: "activate" | "complete" | "archive") => {
    if (!plan || busy || submitLock.current) return;
    if (
      action !== "activate" &&
      !window.confirm(action === "complete" ? "¿Marcar este plan como completado?" : "¿Archivar este plan?")
    )
      return;
    const request =
      action === "activate"
        ? client.activateTrainingPlan
        : action === "complete"
          ? client.completeTrainingPlan
          : client.archiveTrainingPlan;
    if (!request) return;
    submitLock.current = true;
    setBusy(action);
    setError("");
    try {
      setPlan(await request.call(client, id));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      submitLock.current = false;
      setBusy(null);
    }
  };

  const changeSessionDate = (sessionId: string, scheduledDate: string) => {
    setPlan((current) =>
      current
        ? {
            ...current,
            sessions: current.sessions.map((session) =>
              session.id === sessionId ? { ...session, scheduled_date: scheduledDate } : session,
            ),
          }
        : current,
    );
  };

  if (error && !plan)
    return (
      <p role="alert" className="error-banner">
        {error}
      </p>
    );
  if (!plan) return <p role="status">Cargando plan…</p>;

  const mutable = plan.status === "draft" || plan.status === "active";

  return (
    <section className="planning-page">
      <header>
        <p className="eyebrow">PLAN CREADO</p>
        <h1>{plan.title}</h1>
        <p>
          {dateLabel(plan.start_date)} — {dateLabel(plan.end_date)} · Estado: {statusLabels[plan.status] ?? plan.status}
        </p>
      </header>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {plan.status === "completed" && (
        <p role="status" className="success-banner">
          Plan completado
        </p>
      )}
      {plan.status === "archived" && (
        <p role="status" className="info-banner">
          Plan archivado
        </p>
      )}
      {canManage && mutable && (
        <div className="planning-actions">
          {plan.status === "draft" && (
            <button type="button" className="button button--primary" disabled={Boolean(busy)} onClick={() => void transition("activate")}>
              {busy === "activate" ? "Activando…" : "Activar plan"}
            </button>
          )}
          {plan.status === "active" && (
            <button type="button" className="button button--primary" disabled={Boolean(busy)} onClick={() => void transition("complete")}>
              {busy === "complete" ? "Completando…" : "Marcar como completado"}
            </button>
          )}
          <button type="button" className="button" disabled={Boolean(busy)} onClick={() => void transition("archive")}>
            {busy === "archive" ? "Archivando…" : "Archivar"}
          </button>
        </div>
      )}
      {!canManage && mutable && <p className="read-only-note">Vista de solo lectura. No tienes permiso para cambiar el estado del plan.</p>}
      {weeks.map(([week, sessions]) => (
        <section className="preview-week" key={week}>
          <h2>Semana del {dateLabel(week)}</h2>
          {sessions.map((session) => (
            <article className={`preview-session preview-session--${session.sport}`} key={session.id}>
              <time dateTime={session.scheduled_date}>{dateLabel(session.scheduled_date)}</time>
              <div>
                <h3>{session.title}</h3>
                <p>
                  {sportLabel(session.sport)} · {durationLabel(session.planned_duration_seconds)}
                </p>
                {session.description && <p>{session.description}</p>}
                <WorkoutDetail workout={session.workout} />
                <ScheduleChange
                  client={client}
                  athleteId={athleteId}
                  session={session}
                  canManage={canManage}
                  mutable={mutable}
                  allSessions={plan.sessions}
                  onScheduledDateChange={changeSessionDate}
                />
                <ActivityLinks client={client} athleteId={athleteId} session={session} canManage={canManage} />
              </div>
            </article>
          ))}
        </section>
      ))}
      <AppLink className="button" to="/calendar">
        Volver al calendario
      </AppLink>
    </section>
  );
}
