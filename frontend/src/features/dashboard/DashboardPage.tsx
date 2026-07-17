import { useCallback, useEffect, useState } from "react";
import { StatusCard } from "../../components/StatusCard";
import type { ApiClient } from "../../services/apiClient";
import { apiClient } from "../../services/apiClient";
import type {
  ActivityPage,
  DashboardSummary,
  WeeklyTrend,
  Consistency,
  ImportStatus,
  StravaStatus,
  SyncStatus,
} from "../../types/api";
import { displayStatus, formatDate, formatRelativeDate } from "../../utils/format";
import { AthleteOverview } from "./AthleteOverview";
import { RecentActivityList } from "./RecentActivityList";
import {ActivitySyncButton,activitySyncCompletedEvent} from "../../components/ActivitySyncButton";

interface DashboardPageProps {
  client?: ApiClient;
  pollDelayMs?: number;
  showSync?: boolean;
}

const emptyActivities: ActivityPage = {
  total: 0,
  limit: 10,
  offset: 0,
  items: [],
};

export function DashboardPage({
  client = apiClient,
  pollDelayMs = 2000,
  showSync = true,
}: DashboardPageProps) {
  const [loading, setLoading] = useState(true);
  const [backendOnline, setBackendOnline] = useState(false);
  const [strava, setStrava] = useState<StravaStatus | null>(null);
  const [activities, setActivities] = useState(emptyActivities);
  const [sync, setSync] = useState<ImportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [trends, setTrends] = useState<WeeklyTrend[]>([]);
  const [consistency, setConsistency] = useState<Consistency | null>(null);

  const loadContent = useCallback(async () => {
    const [stravaResult, activitiesResult, syncResult] =
      await Promise.allSettled([
        client.stravaStatus(),
        client.activities(),
        client.latestImport(),
      ]);
    if (stravaResult.status === "fulfilled") setStrava(stravaResult.value);
    if (activitiesResult.status === "fulfilled")
      setActivities(activitiesResult.value);
    if (syncResult.status === "fulfilled") setSync(syncResult.value);
    if (
      stravaResult.status === "rejected" ||
      activitiesResult.status === "rejected" ||
      syncResult.status === "rejected"
    ) {
      setError("No se han podido cargar algunos datos. Inténtalo de nuevo.");
    } else {
      setError(null);
    }
  }, [client]);

  const loadAnalytics = useCallback(async () => {
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    try {
      const [nextSummary, nextTrends, nextConsistency] = await Promise.all([client.dashboardSummary(), client.dashboardTrends(), client.dashboardConsistency()]);
      setSummary(nextSummary); setTrends(nextTrends); setConsistency(nextConsistency);
    } catch { setAnalyticsError("No se ha podido cargar el resumen de entrenamiento."); }
    finally { setAnalyticsLoading(false); }
  }, [client]);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      await client.health();
      setBackendOnline(true);
      await loadContent();
    } catch {
      setBackendOnline(false);
      setError("El backend no está disponible. Comprueba que esté iniciado e inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }, [client, loadContent]);

  useEffect(() => {
    void loadDashboard();
    void loadAnalytics();
  }, [loadAnalytics, loadDashboard]);
  useEffect(() => { const refresh=()=>{void loadContent();void loadAnalytics()}; window.addEventListener(activitySyncCompletedEvent,refresh); return()=>window.removeEventListener(activitySyncCompletedEvent,refresh) }, [loadContent,loadAnalytics]);

  const syncStatus: SyncStatus = sync?.status ?? "not_started";
  const athleteTimezone =
    activities.items[0]?.athlete_timezone ?? "Europe/Madrid";
  const stravaLabel = !backendOnline
    ? "No disponible"
    : strava?.connected
      ? "Conectado"
      : strava?.requires_reconnect
        ? "Requiere reconexión"
        : strava?.connection_status === "temporarily_unavailable"
          ? "No disponible temporalmente"
          : "Desconectado";

  return (
    <div className="dashboard-page">{showSync&&<ActivitySyncButton client={client} pollDelayMs={pollDelayMs}/>}
      <header className="page-header"><div><p className="eyebrow">PANEL PERSONAL</p><h1>Inicio</h1><p>Tu espacio personal de entrenamiento de resistencia</p></div><span className="version-badge">Versión 0.5A.1</span></header>

      {loading ? (
        <section className="loading-state" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <p>Cargando tu espacio de entrenamiento…</p>
        </section>
      ) : (
        <>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button type="button" onClick={() => void loadDashboard()}>
                Reintentar
              </button>
            </div>
          )}

          <section className="status-grid" aria-label="Estado del sistema">
            <StatusCard
              label="Backend"
              icon="⌁"
              value={backendOnline ? "En l\u00ednea" : "Sin conexi\u00f3n"}
              tone={backendOnline ? "positive" : "warning"}
            />
            <StatusCard
              label="Strava"
              icon="S"
              value={stravaLabel}
              tone={strava?.connected ? "positive" : "warning"}
              detail={<>{strava?.message}{strava&&!strava.connected&&<a className="status-card__link" href="http://127.0.0.1:8000/integrations/strava/connect">Conectar Strava</a>}</>}
            />
            <StatusCard
              label="Actividades importadas"
              icon="↗"
              value={activities.total.toLocaleString("es-ES")}
            />
            <StatusCard
              label="Última sincronización"
              icon="↻"
              value={displayStatus(syncStatus)}
              tone={
                syncStatus === "failed" ||
                syncStatus === "retry_scheduled"
                  ? "warning"
                  : "neutral"
              }
              detail={
                <span>
                  Última sincronización: {formatRelativeDate(strava?.last_sync_at ?? null) ? `${formatRelativeDate(strava?.last_sync_at ?? null)} · ` : ""}
                  {formatDate(strava?.last_sync_at ?? null, athleteTimezone)}
                </span>
              }
            />
          </section>

          <AthleteOverview summary={summary} trends={trends} consistency={consistency} loading={analyticsLoading} error={analyticsError} onRetry={() => void loadAnalytics()} />

          <section className="dashboard-section">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Resumen de Strava</p>
                <h2>Actividades recientes</h2>
              </div>
            </div>
            <RecentActivityList activities={activities.items} />
          </section>
        </>
      )}
    </div>
  );
}





