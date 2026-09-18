import { useCallback, useEffect, useState } from "react";
import { StatusCard } from "../../components/StatusCard";
import { useRef } from "react";
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
import {ExecutionOverviewSection} from "./ExecutionOverviewSection";
import {DailyOverviewContent} from "./DailyOverviewContent";
import type {DailyOverview} from "./dailyOverviewTypes";
import { RecentActivityList } from "./RecentActivityList";
import {ActivitySyncButton,activitySyncCompletedEvent} from "../../components/ActivitySyncButton";
import {AppLink} from "../../app/usePathname";
import type {AthleteProfileCompleteness} from "../athleteProfile/athleteProfileTypes";
import {roleLabel,type AthleteRole} from "../../types/sessionContext";

interface DashboardPageProps {
  athleteId?: string;
  client?: ApiClient;
  pollDelayMs?: number;
  showSync?: boolean;
  canManageStrava?: boolean;
  onExternalNavigate?: (url: string) => void;
  currentAthleteName?: string;
  currentAthleteRole?: AthleteRole;
  canEditAthleteProfile?: boolean;
}

const emptyActivities: ActivityPage = {
  total: 0,
  limit: 10,
  offset: 0,
  items: [],
};

export function DashboardPage({
  athleteId,
  client = apiClient,
  pollDelayMs = 2000,
  showSync = true,
  canManageStrava = true,
  onExternalNavigate,
  currentAthleteName,
  currentAthleteRole,
  canEditAthleteProfile = true,
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
  const [daily,setDaily]=useState<DailyOverview|null>(null);
  const analyticsGeneration=useRef(0);
  const [connecting,setConnecting]=useState(false);
  const [profileCompleteness,setProfileCompleteness]=useState<AthleteProfileCompleteness|null>(null);
  const mounted = useRef(true);
  const profileGeneration=useRef(0);

  const connectStrava=async()=>{if(connecting||!onExternalNavigate)return;setConnecting(true);setError(null);try{const {authorization_url}=await client.startStravaConnection();if(!/^https:\/\//i.test(authorization_url))throw new Error("invalid_authorization_url");if(mounted.current)onExternalNavigate(authorization_url)}catch{if(mounted.current)setError("No se ha podido iniciar la conexión con Strava.")}finally{if(mounted.current)setConnecting(false)}};

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(()=>{const generation=++profileGeneration.current;setProfileCompleteness(null);if(!client.getAthleteProfile)return;void Promise.resolve(client.getAthleteProfile()).then(value=>{if(value&&mounted.current&&generation===profileGeneration.current)setProfileCompleteness(value.completeness)}).catch(()=>undefined);return()=>{profileGeneration.current++}},[client]);


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
    const generation=++analyticsGeneration.current;
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    try {
      if(client.dailyOverview){
        const value=await client.dailyOverview();
        if(athleteId&&value.athlete_id!==athleteId)throw new Error("athlete mismatch");
        if(generation!==analyticsGeneration.current)return;
        setDaily(value);setSummary(value.summary);setTrends(value.trends);setConsistency(value.consistency);
        return;
      }
      const [nextSummary, nextTrends, nextConsistency] = await Promise.all([client.dashboardSummary(), client.dashboardTrends(), client.dashboardConsistency()]);
      if(generation!==analyticsGeneration.current)return;
      setSummary(nextSummary); setTrends(nextTrends); setConsistency(nextConsistency);
    } catch { if(generation===analyticsGeneration.current){setDaily(null);setAnalyticsError("No se ha podido cargar el resumen de entrenamiento.");} }
    finally { if(generation===analyticsGeneration.current)setAnalyticsLoading(false); }
  }, [client,athleteId]);

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
    setDaily(null);
    void loadDashboard();
    void loadAnalytics();
    return()=>{analyticsGeneration.current++};
  }, [loadAnalytics, loadDashboard]);
  useEffect(() => { const refresh=(event:Event)=>{const source=(event as CustomEvent<{athleteId?:string}>).detail?.athleteId;if(source&&athleteId&&source!==athleteId)return;void loadContent();void loadAnalytics()}; window.addEventListener(activitySyncCompletedEvent,refresh); return()=>window.removeEventListener(activitySyncCompletedEvent,refresh) }, [loadContent,loadAnalytics,athleteId]);

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
    <div className="dashboard-page">{showSync&&strava?.connected&&<ActivitySyncButton client={client} pollDelayMs={pollDelayMs} athleteId={athleteId}/>}
      <header className="page-header"><div><p className="eyebrow">PANEL PERSONAL</p><h1>Inicio</h1><p>Tu espacio personal de entrenamiento de resistencia</p>{currentAthleteName&&currentAthleteRole&&<div className="dashboard-athlete-context"><strong>{currentAthleteName}</strong><span className="athlete-role-badge">{roleLabel(currentAthleteRole)}</span></div>}</div><span className="version-badge">Versión 0.5A.1</span></header>

      {profileCompleteness?.status==="minimal"&&<aside className="athlete-profile-banner" aria-labelledby="athlete-profile-banner-title">{canEditAthleteProfile?<><div><h2 id="athlete-profile-banner-title">Completa tu perfil deportivo</h2><p>Puedes añadir información opcional para mejorar el contexto de entrenamiento.</p></div><AppLink className="button button--primary" to="/settings/athlete-profile">Completar perfil</AppLink></>:<><div><h2 id="athlete-profile-banner-title">Perfil deportivo del atleta</h2><p>Consulta la información básica de {currentAthleteName??"el atleta"}.</p></div><AppLink className="button button--primary" to="/settings/athlete-profile">Ver perfil</AppLink></>}</aside>}

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

          {client.dailyOverview&&(analyticsLoading?<section className="dashboard-section" role="status">Consultando tu resumen de hoy…</section>:
            daily&&(!athleteId||daily.athlete_id===athleteId)?<DailyOverviewContent data={daily}/>:null)}
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
              detail={<>{strava?.message}{canManageStrava&&strava&&<AppLink className="status-card__link" to="/settings/connections">Gestionar Strava</AppLink>}{canManageStrava&&strava&&!strava.connected&&onExternalNavigate&&<button className="status-card__link" type="button" disabled={connecting} onClick={()=>void connectStrava()}>{connecting?"Conectando…":"Conectar Strava"}</button>}</>}
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

          <AthleteOverview summary={summary} trends={trends} consistency={consistency} loading={analyticsLoading} error={analyticsError} onRetry={() => void loadAnalytics()} timezone={daily?.timezone??athleteTimezone}/>
          {!client.dailyOverview&&<ExecutionOverviewSection client={client} athleteId={athleteId}/>}

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





