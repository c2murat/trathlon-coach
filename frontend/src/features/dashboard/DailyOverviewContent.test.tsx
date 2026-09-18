import {act,cleanup,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {DailyOverviewContent} from "./DailyOverviewContent";
import {DashboardPage} from "./DashboardPage";
import {AthleteOverview} from "./AthleteOverview";
import {RecentActivityList} from "./RecentActivityList";
import {interpretationCopy} from "../trainingStatus/interpretationPresentation";
import type {DailyOverview,DailySession} from "./dailyOverviewTypes";
import type {TrainingStatusInterpretation} from "../trainingStatus/interpretationTypes";
import type {ApiClient} from "../../services/apiClient";
import {FetchApiClient} from "../../services/apiClient";
import type {ActivitySummary} from "../../types/api";
import {activitySyncCompletedEvent} from "../../components/ActivitySyncButton";
import {formatDate} from "../../utils/format";

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
function data():DailyOverview {
  const trend={days:7,start_date:null,fitness_delta:null,fatigue_delta:null,fitness_trend:'INSUFFICIENT_DATA',fatigue_trend:'INSUFFICIENT_DATA'} as const;
  const movement={delta:null,direction:'INSUFFICIENT_DATA',changed_direction:false} as const;
  const interpretation:TrainingStatusInterpretation={athlete_id:'a',as_of_date:'2026-09-18',interpretation_version:'0.8G.2D.1',
    data_date:null,window_start_date:null,trend_days:7,fitness:null,fatigue:null,form:null,fitness_delta:null,fatigue_delta:null,
    fitness_trend:'INSUFFICIENT_DATA',fatigue_trend:'INSUFFICIENT_DATA',form_state:'INSUFFICIENT_DATA',overall_state:'INSUFFICIENT_DATA',
    headline_key:'INSUFFICIENT_DATA',summary_key:'INSUFFICIENT_DATA',fitness_explanation_key:'INSUFFICIENT_DATA',fatigue_explanation_key:'INSUFFICIENT_DATA',
    form_explanation_key:'INSUFFICIENT_DATA',notable_trend_key:'INSUFFICIENT_HISTORY',reason_codes:[],short_term:trend,broader_context:{...trend,days:21},
    recent:{days:3,start_date:null,fitness:movement,fatigue:movement,form_delta:null,recovery_turn:false}};
  return {athlete_id:'a',as_of_date:'2026-09-18',timezone:'Europe/Madrid',interpretation,today_sessions:[],next_session:null,next_goal:null,
    execution:{athlete_id:'a',as_of_date:'2026-09-18',window_start_date:'2026-06-27',evidence_version:'0.8G.2C.1',latest_activity:null,latest_activity_sessions:[],recent_sessions:[]},
    summary:{period:'week',period_start:'2026-09-14T00:00:00Z',period_end:'2026-09-21T00:00:00Z',activity_count:0,total_moving_time_seconds:0,total_distance_metres:0,total_elevation_metres:0,active_days:0,longest_activity_seconds:0,longest_activity_distance_metres:0,sport_breakdown:[]},
    trends:[],consistency:{weeks:12,active_weeks:0,current_training_streak_weeks:0,longest_training_streak_weeks:0,average_active_days_per_week:0,average_moving_time_seconds_per_week:0,last_activity_at:null}};
}
const session=(id='s'):DailySession=>({id,scheduled_date:'2026-09-18',scheduled_start_time:null,sport:'running',title:'RUN_EASY',planned_duration_seconds:2700,planned_distance_meters:8000,status:'planned'});
function client(value=data()) {return {dailyOverview:vi.fn().mockResolvedValue(value),health:vi.fn().mockResolvedValue({status:'ok'}),
  activities:vi.fn().mockResolvedValue({items:[],total:0,limit:10,offset:0}),stravaStatus:vi.fn().mockResolvedValue({connected:false}),latestImport:vi.fn().mockResolvedValue({status:'not_started'}),
  executionOverview:vi.fn(),dashboardSummary:vi.fn(),dashboardTrends:vi.fn(),dashboardConsistency:vi.fn()} as unknown as ApiClient;}

it('renders partial data and all empty states without claiming rest or failure',()=>{
  render(<DailyOverviewContent data={data()}/>);
  expect(screen.getByText('Datos insuficientes')).toBeInTheDocument();
  for(const text of ['No tienes sesiones planificadas para hoy.','No hay más sesiones planificadas actualmente.','No tienes una competición futura configurada.'])expect(screen.getByText(text)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/Hoy toca descansar|No cumplido|NaN/);
});
it('reuses D.1 copy and displays values without computing trends',()=>{
  const value=data();Object.assign(value.interpretation,{fitness:30,fatigue:35,form:-5,overall_state:'BALANCED',headline_key:'BALANCED'});
  render(<DailyOverviewContent data={value}/>);
  expect(screen.getByText(interpretationCopy(value.interpretation).headline)).toBeInTheDocument();
  expect(screen.getByText('30')).toBeInTheDocument();expect(screen.getByRole('link',{name:'Ver estado de forma'})).toHaveAttribute('href','/statistics/training-status');
});
it.each([1,3])('shows all %i sessions today in server order with status and distances',count=>{
  const value=data();value.today_sessions=Array.from({length:count},(_,i)=>({...session(String(i)),title:`Entrenamiento ${i}`}));
  render(<DailyOverviewContent data={value}/>);
  const today=screen.getByRole('region',{name:'Hoy'});
  expect(within(today).getAllByRole('heading',{level:3}).map(x=>x.textContent)).toEqual(value.today_sessions.map(x=>x.title));
  expect(within(today).getAllByText('Estado de planificación: Planificada')).toHaveLength(count);
});
it('shows upcoming session and goal, priority, city, days and links',()=>{
  const value=data();value.next_session={...session(),scheduled_date:'2026-09-19'};
  value.next_goal={id:'g',name:'Carrera del otoño',event_date:'2026-10-01',event_category:'running',event_format:'10k',priority:'A',city:'Madrid',days_remaining:13};
  render(<DailyOverviewContent data={value}/>);
  expect(screen.getByText('19 de septiembre de 2026')).toBeInTheDocument();
  expect(screen.getByText(/13 días restantes/)).toBeInTheDocument();expect(screen.getByText('Madrid')).toBeInTheDocument();
  const headings=screen.getAllByRole('heading').map(x=>x.textContent);
  expect(headings.indexOf('Hoy')).toBeLessThan(headings.indexOf('Último entrenamiento'));
  expect(headings.indexOf('Sesiones recientes')).toBeLessThan(headings.indexOf('Próximamente'));
});
it.each([['2026-07-10T15:00:00Z','17:00'],['2026-01-10T15:00:00Z','16:00']])('shows %s consistently in all three surfaces', (timestamp,hour)=>{
  const value=data();value.consistency.last_activity_at=timestamp;
  value.execution.latest_activity={id:'activity',name:'Ride',sport:'cycling',started_at:timestamp,timezone:'UTC',duration_seconds:3600,distance_meters:20000,average_heart_rate_bpm:null,average_power_w:null};
  render(<><DailyOverviewContent data={value}/><AthleteOverview summary={value.summary} trends={[]} consistency={value.consistency} loading={false} error={null} onRetry={()=>{}} timezone={value.timezone}/>
    <RecentActivityList activities={[{id:'activity',name:'Ride',sport_type:'cycling',start_time:timestamp,athlete_timezone:value.timezone,moving_time_seconds:3600,distance_metres:20000,elevation_metres:0} as ActivitySummary]}/></>);
  const formatted=formatDate(timestamp,value.timezone);expect(formatted).toContain(hour);
  expect(screen.getAllByText(formatted)).toHaveLength(2);
  expect(within(screen.getByRole('region',{name:'Ejecución de tus entrenamientos'})).getByText(new RegExp(hour))).toBeInTheDocument();
});
it('loads one coherent overview and refreshes Q automatically for the same athlete only',async()=>{
  const api=client();render(<DashboardPage client={api} athleteId='a' showSync={false}/>);
  await screen.findByRole('heading',{name:'Tu estado'});expect(api.executionOverview).not.toHaveBeenCalled();expect(api.dashboardSummary).not.toHaveBeenCalled();
  act(()=>window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent,{detail:{athleteId:'foreign'}})));expect(api.dailyOverview).toHaveBeenCalledTimes(1);
  const next=data();next.today_sessions=[session()];vi.mocked(api.dailyOverview!).mockResolvedValue(next);
  act(()=>window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent,{detail:{athleteId:'a'}})));
  await screen.findByText('Estado de planificación: Planificada');expect(api.dailyOverview).toHaveBeenCalledTimes(2);
});
it('rejects a foreign response and keeps load failures distinct from empty data',async()=>{
  const value=data();value.athlete_id='foreign';render(<DashboardPage client={client(value)} athleteId='a' showSync={false}/>);
  await screen.findByText('No se ha podido cargar el resumen de entrenamiento.');
  expect(screen.queryByRole('heading',{name:'Tu estado'})).not.toBeInTheDocument();expect(screen.queryByText('No tienes sesiones planificadas para hoy.')).not.toBeInTheDocument();
});
it('ignores a late overview after switching athlete',async()=>{
  let resolveOld!:(value:DailyOverview)=>void;
  const old=client();vi.mocked(old.dailyOverview!).mockReturnValue(new Promise(resolve=>{resolveOld=resolve}));
  const view=render(<DashboardPage client={old} athleteId='a' showSync={false}/>);
  await waitFor(()=>expect(old.dailyOverview).toHaveBeenCalledOnce());
  const next=data();next.athlete_id='b';next.today_sessions=[{...session(),title:'Sesión del atleta B'}];
  view.rerender(<DashboardPage client={client(next)} athleteId='b' showSync={false}/>);
  await screen.findByText('Sesión del atleta B');
  await act(async()=>resolveOld(data()));
  expect(screen.getByText('Sesión del atleta B')).toBeInTheDocument();
});
it('scopes the daily endpoint through the central client',async()=>{
  const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>data()});
  vi.stubGlobal('fetch',fetcher);
  const api=new FetchApiClient('http://localhost');api.setActiveAthlete('a');await api.dailyOverview();
  expect(fetcher.mock.calls[0][0]).toBe('http://localhost/dashboard/daily-overview');
  expect(new Headers(fetcher.mock.calls[0][1].headers).get('X-TriCoach-Athlete-Id')).toBe('a');
});
