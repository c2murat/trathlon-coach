import {useCallback,useEffect,useRef,useState} from "react";
import {useAthleteContext} from "../../app/AthleteContext";
import {ActivitySyncButton} from "../../components/ActivitySyncButton";
import {apiClient,type ApiClient} from "../../services/apiClient";
import type {StravaStatus} from "../../types/api";
import {ATHLETE_CAPABILITIES} from "../../types/sessionContext";
import {formatDate} from "../../utils/format";
import "./connections.css";

type Props={client?:ApiClient;athleteId?:string;athleteName?:string;canManage?:boolean;canConnect?:boolean;canDisconnect?:boolean;canSync?:boolean;onExternalNavigate?:(url:string)=>void};
function errorCode(error:unknown){return error instanceof Error?error.message:""}

export function ConnectionsPage(props:Props){
 const context=useAthleteContext(),athleteId=props.athleteId??context.activeAthleteId??"",athleteName=props.athleteName??context.activeAthlete?.label??"Atleta";
 const canConnect=props.canConnect??props.canManage??context.hasAthleteCapability(ATHLETE_CAPABILITIES.CONNECT_STRAVA),canDisconnect=props.canDisconnect??props.canManage??context.hasAthleteCapability(ATHLETE_CAPABILITIES.DISCONNECT_STRAVA),canSync=props.canSync??context.hasAthleteCapability(ATHLETE_CAPABILITIES.IMPORT_STRAVA);
 return <StravaConnectionPanel {...props} athleteId={athleteId} athleteName={athleteName} canConnect={canConnect} canDisconnect={canDisconnect} canSync={canSync}/>;
}

export function StravaConnectionPanel({client=apiClient,athleteId,athleteName,canManage,canConnect=canManage??false,canDisconnect=canManage??false,canSync=false,onExternalNavigate=(url)=>window.location.assign(url)}:Required<Pick<Props,"athleteId"|"athleteName">>&Props){
 const [status,setStatus]=useState<StravaStatus|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false),[confirming,setConfirming]=useState(false);
 const generation=useRef(0),mounted=useRef(false),locked=useRef(false);
 const load=useCallback(async()=>{const current=++generation.current;setStatus(null);setLoading(true);setError(null);try{const next=await client.stravaStatus();if(mounted.current&&current===generation.current)setStatus(next)}catch{if(mounted.current&&current===generation.current)setError("No se ha podido cargar el estado de Strava.")}finally{if(mounted.current&&current===generation.current)setLoading(false)}},[client,athleteId]);
 useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;generation.current++;locked.current=false}},[load]);
 const connect=async()=>{if(locked.current)return;locked.current=true;setBusy(true);setError(null);try{const result=await client.startStravaConnection();if(!/^https:\/\//i.test(result.authorization_url))throw new Error("invalid_authorization_url");if(mounted.current)onExternalNavigate(result.authorization_url)}catch(cause){if(mounted.current)setError(errorCode(cause).includes("strava_external_account_already_linked")?"Esta cuenta de Strava ya está vinculada a otro atleta.":errorCode(cause).includes("403")?`No tienes permisos para gestionar la conexión de Strava de ${athleteName}.`:"No se ha podido iniciar la conexión con Strava.")}finally{locked.current=false;if(mounted.current)setBusy(false)}};
 const disconnect=async()=>{if(locked.current)return;locked.current=true;setBusy(true);setError(null);try{await client.disconnectStrava();if(mounted.current){setConfirming(false);await load()}}catch(cause){if(mounted.current)setError(errorCode(cause).includes("403")?`No tienes permisos para gestionar la conexión de Strava de ${athleteName}.`:"No se ha podido desconectar Strava.")}finally{locked.current=false;if(mounted.current)setBusy(false)}};
 return <article className="connections-page"><header className="athlete-profile-header"><p>CONFIGURACIÓN DEL ATLETA</p><h1>Conexiones</h1><span>Gestiona las integraciones del atleta seleccionado.</span></header><section className="connection-card" aria-labelledby="strava-connection-title"><div className="connection-card__heading"><div><p className="eyebrow">Strava</p><h2 id="strava-connection-title">{athleteName}</h2></div>{status&&<strong className={`connection-state connection-state--${status.connected?"connected":"disconnected"}`}>{status.connected?"Conectado":status.requires_reconnect?"Requiere reconexión":"Sin conectar"}</strong>}</div>
 {loading&&<div className="connection-state-panel" role="status">Cargando el estado de Strava para {athleteName}…</div>}
 {error&&<div className="connection-state-panel connection-state-panel--error" role="alert"><p>{error}</p><button className="button button--ghost" type="button" onClick={()=>void load()}>Reintentar</button></div>}
 {!loading&&status&&<><p>{status.connected?`La cuenta autorizada está vinculada exclusivamente a ${athleteName}.`:`La cuenta que autorices se vinculará exclusivamente a ${athleteName}.`}</p>{status.connected&&<dl className="connection-details"><div><dt>Última sincronización</dt><dd>{formatDate(status.last_sync_at,"Europe/Madrid")}</dd></div><div><dt>Conectada desde</dt><dd>{formatDate(status.connected_at,"Europe/Madrid")}</dd></div></dl>}
 <div className="connection-actions">{canConnect&&(!status.connected||status.requires_reconnect)&&<button className="button button--primary" type="button" disabled={busy} onClick={()=>void connect()} aria-label={`${status.requires_reconnect?"Reconectar":"Conectar"} Strava para ${athleteName}`}>{busy?"Abriendo Strava…":status.requires_reconnect?"Reconectar Strava":"Conectar Strava"}</button>}{status.connected&&canSync&&<ActivitySyncButton key={athleteId} athleteId={athleteId} client={client}/>} {canDisconnect&&status.connected&&!confirming&&<button className="button button--ghost" type="button" disabled={busy} onClick={()=>setConfirming(true)}>Desconectar Strava</button>}</div>
 {confirming&&<div className="connection-confirm" role="group" aria-label={`Confirmar desconexión de Strava para ${athleteName}`}><p>Se retirará la autorización de {athleteName}. Las actividades y el histórico importado se conservarán.</p><button className="button button--primary" type="button" disabled={busy} onClick={()=>void disconnect()}>{busy?"Desconectando…":"Confirmar desconexión"}</button><button className="button button--ghost" type="button" disabled={busy} onClick={()=>setConfirming(false)}>Cancelar</button></div>}
 {!canConnect&&!canDisconnect&&!canSync&&<p className="connection-readonly">Puedes consultar esta conexión, pero no gestionarla.</p>}</>}
 </section></article>;
}
