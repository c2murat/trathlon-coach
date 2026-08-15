import {useEffect,useRef,useState} from "react";
import {ActivitiesPage} from "../features/activities/ActivitiesPage";
import {ActivitySummaryPage} from "../features/activities/ActivitySummaryPage";
import {DashboardPage} from "../features/dashboard/DashboardPage";
import {ManualStrengthPage} from "../features/manualStrength/ManualStrengthPage";
import {PerformanceProfilePage} from "../features/profile/PerformanceProfilePage";
import {AccountPage} from "../features/account/AccountPage";
import {AthleteProfilePage} from "../features/athleteProfile/AthleteProfilePage";
import {ConnectionsPage} from "../features/connections/ConnectionsPage";
import {CoachAssignmentsPage} from "../features/coachAssignments/CoachAssignmentsPage";
import {TrainingLoadPage} from "../features/trainingLoad/TrainingLoadPage";
import {TrainingStatusPage} from "../features/trainingStatus/TrainingStatusPage";
import {apiClient,type ApiClient} from "../services/apiClient";
import {ComingSoonPage} from "./ComingSoonPage";
import {NavIcon,type NavIconName} from "./NavIcon";
import {useTheme} from "./ThemeProvider";
import {AppLink,navigate,usePathname} from "./usePathname";
import {useAthleteContext} from "./AthleteContext";
import {AthleteSelector} from "./AthleteSelector";
import {NewAthleteDialog} from "./NewAthleteDialog";
import {ATHLETE_CAPABILITIES,type AthleteCapability,type AthleteRole} from "../types/sessionContext";
import {useAuth} from "./AuthContext";

const nav:{path:string;label:string;icon:NavIconName}[]=[
 {path:"/dashboard",label:"Inicio",icon:"home"},{path:"/activities",label:"Actividades",icon:"activities"},
 {path:"/calendar",label:"Calendario",icon:"calendar"},{path:"/statistics",label:"Estadísticas",icon:"statistics"},
 {path:"/settings/connections",label:"Conexiones",icon:"settings"},
 {path:"/health",label:"Salud",icon:"health"},{path:"/settings",label:"Configuración",icon:"settings"},
];
function ActivitySyncButton(_: {client:ApiClient}){return null}
function greeting(){const hour=new Date().getHours();return hour<12?"Buenos días":hour<20?"Buenas tardes":"Buenas noches"}
function routeContent(path:string,client:ApiClient,has:(capability:AthleteCapability)=>boolean,athlete?:{label:string;role:string}|null){
 if(path==="/dashboard")return <DashboardPage client={client} showSync canManageStrava={has(ATHLETE_CAPABILITIES.CONNECT_STRAVA)} currentAthleteName={athlete?.label} currentAthleteRole={athlete?.role as AthleteRole|undefined}/>;
 if(path==="/activities")return <ActivitiesPage client={client}/>;
 if(path==="/activities/strength")return <ManualStrengthPage client={client} canCreate={has(ATHLETE_CAPABILITIES.CREATE_STRENGTH)} canUpdate={has(ATHLETE_CAPABILITIES.UPDATE_STRENGTH)} canDelete={has(ATHLETE_CAPABILITIES.DELETE_STRENGTH)} canRecalculate={has(ATHLETE_CAPABILITIES.RECALCULATE)}/>;
 if(path==="/settings/account")return <AccountPage client={client}/>;
 if(path==="/settings/coaches")return <CoachAssignmentsPage client={client}/>;
 if(path==="/settings/athlete-profile")return <AthleteProfilePage client={client}/>;
 if(path==="/settings/connections")return <ConnectionsPage client={client}/>;
 if(path==="/settings/performance-profile"){const profile=has(ATHLETE_CAPABILITIES.CREATE_PROFILE),reference=has(ATHLETE_CAPABILITIES.CREATE_REFERENCE);return <div key={`${profile}-${reference}`} className={`${profile?"":"deny-profile "}${reference?"":"deny-reference"}`}><PerformanceProfilePage client={client}/></div>}
 if(path==="/statistics/training-load")return <TrainingLoadPage client={client}/>;
 if(path==="/statistics/training-status")return <TrainingStatusPage client={client} canRecalculate={has(ATHLETE_CAPABILITIES.RECALCULATE)}/>;
 if(path.startsWith("/activities/"))return <div className={`${has(ATHLETE_CAPABILITIES.RECALCULATE)?"":"deny-recalculate "}${has(ATHLETE_CAPABILITIES.ENRICH_STRAVA)?"":"deny-enrichment "}${has(ATHLETE_CAPABILITIES.EVIDENCE_STRAVA)?"":"deny-evidence"}`}><ActivitySummaryPage activityId={path.slice(12)} client={client}/></div>;
 return <ComingSoonPage title={nav.find(item=>item.path===path)?.label??"Página"}/>;
}
export function AppShell({client=apiClient,showLogout=false,onLogout}:{client?:ApiClient;showLogout?:boolean;onLogout?():Promise<void>}){
 const [path]=usePathname(),{theme,toggle}=useTheme();
 const {user,refreshUser}=useAuth();
 const {athletes,activeAthlete,activeAthleteId,loading,selectionRequired,error,announcement,hasAthleteCapability,refreshContext}=useAthleteContext();
 const [drawer,setDrawer]=useState(false),[userOpen,setUserOpen]=useState(false),[creating,setCreating]=useState(false);const menuRef=useRef<HTMLDivElement>(null),createTrigger=useRef<HTMLButtonElement|null>(null);
 const openCreate=(trigger:HTMLButtonElement)=>{createTrigger.current=trigger;setCreating(true)},closeCreate=()=>{setCreating(false);queueMicrotask(()=>createTrigger.current?.focus())};
 useEffect(()=>{if(path==="/")navigate("/dashboard")},[path]);useEffect(()=>setDrawer(false),[path]);
 useEffect(()=>{const close=(event:MouseEvent)=>{if(!menuRef.current?.contains(event.target as Node))setUserOpen(false)};document.addEventListener("mousedown",close);return()=>document.removeEventListener("mousedown",close)},[]);
 const displayName=user?.display_name?.trim()||"Usuario",initial=displayName.charAt(0).toLocaleUpperCase("es-ES")||"U";
 const isEmptyCoach=user?.account_plan==="coach"&&!activeAthleteId;
 const canCreateAthletes=user?.account_plan==="owner";
 const date=new Intl.DateTimeFormat("es-ES",{weekday:"long",day:"numeric",month:"long",year:"numeric"}).format(new Date());
 const content=path==="/settings/account"?routeContent(path,client,hasAthleteCapability,activeAthlete):loading?<section role="status">Cargando contexto…</section>:error?<section role="alert"><h1>Error al cargar el contexto</h1><p>{error}</p></section>:!athletes.length&&user?.account_plan==="coach"?<section className="athlete-empty"><h1>Bienvenido, {displayName}</h1><p className="athlete-role-badge">Entrenador</p><h2>Todavía no tienes atletas asignados.</h2><p>Cuando tengas atletas asignados, aparecerán aquí para que puedas trabajar con ellos.</p></section>:!athletes.length?<section className="athlete-empty"><h1>Sin atleta asociado</h1><p>No existe un perfil de atleta asociado a este usuario.</p>{canCreateAthletes&&<button type="button" className="button button--primary" onClick={event=>openCreate(event.currentTarget)}>Crear mi primer atleta</button>}</section>:selectionRequired?<section className="athlete-selection-screen"><h1>Selección de atleta necesaria</h1><p>Selecciona el perfil con el que quieres trabajar.</p><AthleteSelector required onCreate={canCreateAthletes?openCreate:undefined}/></section>:activeAthleteId?<div key={activeAthleteId}>{path==="/health"&&!hasAthleteCapability(ATHLETE_CAPABILITIES.READ_HEALTH)?<section role="alert"><h1>Acceso no permitido</h1><p>No tienes permiso para consultar la salud de este atleta.</p></section>:routeContent(path,client,hasAthleteCapability,activeAthlete)}</div>:null;
 return <div className="application-shell">
  <a className="skip-link" href="#main-content">Saltar al contenido principal</a>
  <aside className={`sidebar ${drawer?"sidebar--open":""}`} aria-label="Navegación principal"><div className="brand"><span className="brand__mark" aria-hidden="true">T</span><span>TriCoach AI</span></div><nav>{nav.filter(item=>(!isEmptyCoach||["/dashboard","/settings"].includes(item.path))&&(item.path!=="/health"||hasAthleteCapability(ATHLETE_CAPABILITIES.READ_HEALTH))).map(item=><span key={item.path}><AppLink to={item.path} className={`nav-link ${path===item.path||(item.path==="/activities"&&path.startsWith("/activities/"))?"nav-link--active":""}`}><NavIcon name={item.icon}/><span className="nav-item-label">{item.label}</span></AppLink>{item.path==="/activities"&&<AppLink to="/activities/strength" className={`nav-link nav-link--strength ${path==="/activities/strength"?"nav-link--active":""}`}><NavIcon name="strength"/><span className="nav-item-label">Fuerza</span></AppLink>}{item.path==="/statistics"&&<><AppLink to="/statistics/training-load" className={`nav-link nav-link--nested nav-subitem ${path==="/statistics/training-load"?"nav-link--active":""}`}>Carga de entrenamiento</AppLink><AppLink to="/statistics/training-status" className={`nav-link nav-link--nested nav-subitem ${path==="/statistics/training-status"?"nav-link--active":""}`}>Estado de forma</AppLink></>}{item.path==="/settings"&&<><AppLink to="/settings/account" className={`nav-link nav-link--nested nav-subitem ${path==="/settings/account"?"nav-link--active":""}`}>Cuenta</AppLink>{user?.account_plan==="owner"&&<AppLink to="/settings/coaches" className={`nav-link nav-link--nested nav-subitem ${path==="/settings/coaches"?"nav-link--active":""}`}>Entrenadores</AppLink>}{!isEmptyCoach&&<> <AppLink to="/settings/athlete-profile" className={`nav-link nav-link--nested nav-subitem ${path==="/settings/athlete-profile"?"nav-link--active":""}`}>Perfil deportivo</AppLink><AppLink to="/settings/performance-profile" className={`nav-link nav-link--nested nav-subitem ${path==="/settings/performance-profile"?"nav-link--active":""}`}>Perfil de rendimiento</AppLink></>}</>}</span>)}</nav><p className="sidebar__version">Versión 0.7G.5</p></aside>
  {drawer&&<button className="drawer-backdrop" aria-label="Cerrar navegación" onClick={()=>setDrawer(false)}/>}
  <div className="application-main"><header className="topbar"><button className="icon-button mobile-menu" type="button" aria-label={drawer?"Cerrar menú":"Abrir menú"} aria-expanded={drawer} onClick={()=>setDrawer(value=>!value)}>☰</button>{activeAthleteId&&<ActivitySyncButton client={client}/>}{athletes.length>0&&<div className="athlete-context-control">{user?.account_plan==="coach"&&<span>Mis atletas</span>}<AthleteSelector onCreate={canCreateAthletes?openCreate:undefined}/></div>}<div className="topbar__greeting"><strong>{greeting()}, {displayName}</strong><span>{date}</span></div><div className="topbar__actions"><button className="icon-button" type="button" aria-label={`Activar tema ${theme==="light"?"oscuro":"claro"}`} onClick={toggle}>{theme==="light"?"☾":"☀"}</button><div className="user-menu" ref={menuRef}><button className="user-button" type="button" aria-haspopup="menu" aria-expanded={userOpen} onClick={()=>setUserOpen(value=>!value)}><span className="avatar" aria-label={`Usuario: ${displayName}`}>{initial}</span><span>{displayName}</span><span aria-hidden="true">⌄</span></button>{userOpen&&<div className="user-menu__panel" role="menu"><button role="menuitem" disabled>Perfil <small>Próximamente</small></button><AppLink to="/settings/account" className="user-menu__link">Cuenta</AppLink>{!isEmptyCoach&&<> <AppLink to="/settings/athlete-profile" className="user-menu__link">Perfil deportivo</AppLink><AppLink to="/settings/performance-profile" className="user-menu__link">Perfil de rendimiento</AppLink></>}{showLogout?<button role="menuitem" onClick={()=>void onLogout?.()}>Cerrar sesión</button>:<button role="menuitem" disabled>Cerrar sesión <small>Desarrollo</small></button>}</div>}</div></div></header><div className="sr-only" aria-live="polite">{announcement}</div><main id="main-content" className="page-content" tabIndex={-1}>{path==="/"?null:content}</main></div>{creating&&canCreateAthletes&&<NewAthleteDialog client={client} refreshContext={refreshContext} refreshUser={refreshUser} onClose={closeCreate} onActivated={()=>navigate("/dashboard")}/>}
 </div>
}
