import {act,cleanup,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach,expect,it,vi} from "vitest";
import {CalendarExecutionDetail,ExecutionBadge} from "./CalendarExecution";
import {CalendarPage} from "./CalendarPage";
import {MonthlyCalendar} from "./MonthlyCalendar";
import {AnnualCalendar} from "./AnnualCalendar";
import {calendarItems} from "./calendarItems";
import type {CalendarExecution} from "./calendarExecutionTypes";
import type {CompletionStatus,ExecutionSessionView} from "../dashboard/executionOverviewTypes";
import type {TrainingPlanSession} from "../../types/planning";
import type {ApiClient} from "../../services/apiClient";
import {FetchApiClient} from "../../services/apiClient";
import {activitySyncCompletedEvent} from "../../components/ActivitySyncButton";

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
const year=new Date().getFullYear(),month=new Date().getMonth();
const day=(number:number)=>`${year}-${String(month+1).padStart(2,'0')}-${String(number).padStart(2,'0')}`;
const dateCaption=(number:number)=>`${String(number).padStart(2,'0')}/${String(month+1).padStart(2,'0')}/${year}`;
function view(status:CompletionStatus='COMPLETED'):ExecutionSessionView {
  const activities=[{id:'a1',name:'Actividad primera',sport:'running',started_at:day(10)+'T15:00:00Z',timezone:'UTC',duration_seconds:1200,distance_meters:3000,average_heart_rate_bpm:null,average_power_w:null},
    {id:'a2',name:'Actividad segunda',sport:'running',started_at:day(10)+'T16:00:00Z',timezone:'UTC',duration_seconds:1500,distance_meters:4000,average_heart_rate_bpm:null,average_power_w:null}];
  return {id:'session',date:day(10),sport:'running',title:'RUN_EASY',planned_duration_seconds:2700,planned_distance_meters:8000,workout:null,
    activities:status==='UNMATCHED'?[]:activities,evidence:{planned_session_id:'session',completion_status:status,actual_duration_seconds:status==='UNMATCHED'?null:2700,actual_distance_m:status==='UNMATCHED'?null:7000,
      comparison_confidence:'HIGH',sport_match:true,target_comparison:null,source_activity_ids:activities.map(a=>a.id),
      link_provenance:activities.map((a,i)=>({activity_id:a.id,match_source:i?'automatic':'manual',match_confidence:'high',matching_algorithm_version:i?'0.8g.1':null}))}};
}
function batch(status:CompletionStatus='COMPLETED'):CalendarExecution{return {athlete_id:'owner',as_of_date:day(11),timezone:'Europe/Madrid',start_date:`${year}-01-01`,end_date:`${year}-12-31`,evidence_version:'0.8G.2C.1',sessions:[view(status)]};}
const plan=(id='session',date=day(10)):TrainingPlanSession=>({id,scheduled_date:date,sport:'running',title:'RUN_EASY',description:null,planned_duration_seconds:2700,workout:null});
const api=(data=batch())=>({competitionGoals:vi.fn().mockResolvedValue([]),plannedTrainingSessions:vi.fn().mockResolvedValue([plan(),plan('today',day(11)),plan('future',day(12))]),calendarExecution:vi.fn().mockImplementation(async(start,end)=>({...data,start_date:start,end_date:end}))} as unknown as ApiClient);
function strength(status:CompletionStatus='UNMATCHED'):ExecutionSessionView{return {id:'strength-session',date:day(21),sport:'strength',title:'GENERAL_STRENGTH',planned_duration_seconds:2400,planned_distance_meters:null,workout:null,activities:status==='UNMATCHED'?[]:[{id:'manual-strength',name:'Fuerza manual',sport:'strength',started_at:day(22)+'T15:42:00Z',timezone:'Europe/Madrid',duration_seconds:3600,distance_meters:null,average_heart_rate_bpm:null,average_power_w:null}],evidence:{planned_session_id:'strength-session',completion_status:status,actual_duration_seconds:status==='UNMATCHED'?null:3600,actual_distance_m:null,comparison_confidence:status==='UNMATCHED'?'INSUFFICIENT':'HIGH',sport_match:status==='UNMATCHED'?null:true,target_comparison:null,source_activity_ids:status==='UNMATCHED'?[]:['manual-strength'],link_provenance:status==='UNMATCHED'?[]:[{activity_id:'manual-strength',match_source:'manual',match_confidence:'high',matching_algorithm_version:null}]}}}
const strengthPlan:TrainingPlanSession={id:'strength-session',scheduled_date:day(21),sport:'strength',title:'GENERAL_STRENGTH',description:null,planned_duration_seconds:2400,workout:null};
function unmatchedSport(sport:string,id=`${sport}-session`,date=day(22)):ExecutionSessionView{return {id,date,sport,title:sport==='cycling'?'BIKE_ENDURANCE':sport==='swimming'?'SWIM_TECHNIQUE':'RUN_EASY',planned_duration_seconds:3600,planned_distance_meters:sport==='strength'?null:10000,workout:{schema_version:1,sport,title:'Workout',purpose:'AEROBIC_BASE',steps:[]},activities:[],evidence:{planned_session_id:id,completion_status:'UNMATCHED',actual_duration_seconds:null,actual_distance_m:null,comparison_confidence:'INSUFFICIENT',sport_match:null,target_comparison:null,source_activity_ids:[],link_provenance:[]}}}
function linkedSport(sport:string,id=`${sport}-session`,date=day(22),activityDate=day(21)):ExecutionSessionView{const activity={id:`${sport}-activity`,name:sport==='cycling'?'Bicicleta por la tarde':sport==='swimming'?'Natación por la mañana':'Carrera por la tarde',sport,started_at:activityDate+'T15:00:00Z',timezone:'Europe/Madrid',duration_seconds:4320,distance_meters:sport==='swimming'?1800:34800,average_heart_rate_bpm:null,average_power_w:null};return {...unmatchedSport(sport,id,date),activities:[activity],evidence:{planned_session_id:id,completion_status:'OVER_DURATION',actual_duration_seconds:4320,actual_distance_m:activity.distance_meters,comparison_confidence:'HIGH',sport_match:true,target_comparison:null,source_activity_ids:[activity.id],link_provenance:[{activity_id:activity.id,match_source:'manual',match_confidence:'high',matching_algorithm_version:null}]}}}
const genericPlan=(sport:string,id=`${sport}-session`,date=day(22)):TrainingPlanSession=>({id,scheduled_date:date,sport,title:sport==='cycling'?'BIKE_ENDURANCE':sport==='swimming'?'SWIM_TECHNIQUE':'RUN_EASY',description:null,planned_duration_seconds:3600,workout:null});

it.each([['COMPLETED','Completada'],['PARTIAL','Parcial'],['OVER_DURATION','Duración superior'],['UNMATCHED','Sin actividad vinculada'],['UNKNOWN','Evidencia insuficiente']] as const)('translates %s without technical enums or blame',async(status,text)=>{
  render(<><ExecutionBadge value={view(status)}/><CalendarExecutionDetail value={view(status)} timezone='Europe/Madrid'/></>);
  expect(screen.getByText(text)).toBeInTheDocument();await userEvent.click(screen.getByText('Ver ejecución de carrera suave',{exact:false}).closest('summary')!);
  expect(document.body.textContent).not.toMatch(/COMPLETED|PARTIAL|OVER_DURATION|UNKNOWN|UNMATCHED|No cumplid[ao]/);
  if(status==='UNMATCHED')expect(screen.getByText(/La ausencia de vínculo no permite saber/)).toBeInTheDocument();
});
it('shows aggregated planned/performed facts and every linked activity with provenance',async()=>{
  render(<CalendarExecutionDetail value={view()} timezone='Europe/Madrid'/>);
  await userEvent.click(screen.getByText(/Ver ejecución/));
  expect(screen.getAllByText(/45 min/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Actividad vinculada manualmente/)).toBeInTheDocument();expect(screen.getByText(/Actividad vinculada automáticamente/)).toBeInTheDocument();
  expect(screen.getAllByRole('link',{name:'Ver actividad'}).map(x=>x.getAttribute('href'))).toEqual(['/activities/a1','/activities/a2']);
  expect(screen.getByText('Actividad primera')).toBeInTheDocument();expect(screen.getByText('Actividad segunda')).toBeInTheDocument();
});
it.each([null,{planned_repetitions:5,matched_repetitions:4,target_hit_fraction:'0.75',execution_relation:'WITHIN_TARGET',confidence:'HIGH'}] as const)('uses structured evidence without inventing hit counts',async targets=>{
  const value=view();value.workout={schema_version:1,sport:'running',title:'RUN_EASY',purpose:'AEROBIC_BASE',steps:[]};value.evidence!.target_comparison=targets;
  render(<CalendarExecutionDetail value={value} timezone='Europe/Madrid'/>);await userEvent.click(screen.getByText(/Ver ejecución/));
  expect(screen.getByText('Cumplimiento de objetivos')).toBeInTheDocument();
  expect(screen.getByText(targets?'Objetivos parcialmente cumplidos':'No hay datos suficientes para comprobar los intervalos')).toBeInTheDocument();
  if(targets)expect(screen.getByText('Repeticiones comparadas: 4 de 5.')).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/bloques dentro del rango/);
});
it('omits today/future badges even if a response contains them',()=>{
  const data=batch();data.sessions.push({...view(),id:'today',date:day(11)},{...view(),id:'future',date:day(12)});
  const items=calendarItems([],[plan(),plan('today',day(11)),plan('future',day(12))],data);
  expect(items.map(x=>Boolean(x.execution))).toEqual([true,false,false]);
});
it('list shows badge and detail only for elapsed sessions and refreshes on sync',async()=>{
  window.history.replaceState({},"","/calendar?view=list");
  const client=api();render(<CalendarPage client={client} athleteId='owner' canManage={false}/>);
  await screen.findByText('Completada');expect(screen.getAllByText(/Ver ejecución/)).toHaveLength(1);
  act(()=>window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent,{detail:{athleteId:'foreign'}})));expect(client.calendarExecution).toHaveBeenCalledOnce();
  act(()=>window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent,{detail:{athleteId:'owner'}})));
  await waitFor(()=>expect(client.calendarExecution).toHaveBeenCalledTimes(2));
});
it('month shows textual badges, accessible day labels and all linked details',async()=>{
  const items=calendarItems([],[plan()],batch('UNMATCHED'));
  render(<MonthlyCalendar items={items} year={year} month={month} selectedDate={day(10)} today={day(11)} timezone='Europe/Madrid' onSelectDate={vi.fn()} onMonthChange={vi.fn()}/>);
  expect(screen.getByRole('gridcell',{name:/Sin actividad vinculada/})).toBeInTheDocument();
  expect(screen.getAllByText('Sin actividad vinculada').length).toBeGreaterThan(0);
  await userEvent.click(screen.getByText(/Ver ejecución/));expect(screen.getByRole('heading',{name:'Ejecución'})).toBeInTheDocument();
});
it('links manual strength from the month execution panel after explicit cross-day confirmation',async()=>{
  window.history.replaceState({},"","/calendar?view=month");
  const initial={...batch('UNMATCHED'),as_of_date:day(28),sessions:[strength()]},linked={...initial,sessions:[strength('OVER_DURATION')]};
  let calls=0;const client={competitionGoals:vi.fn().mockResolvedValue([]),plannedTrainingSessions:vi.fn().mockResolvedValue([strengthPlan]),calendarExecution:vi.fn().mockImplementation(async(start,end)=>({...(++calls===1?initial:linked),start_date:start,end_date:end})),plannedSessionActivityCandidates:vi.fn().mockResolvedValue([{id:'manual-strength',name:'Fuerza manual',sport:'strength',started_at:day(22)+'T15:42:00Z',timezone:'Europe/Madrid',duration_seconds:3600,distance_meters:null,source_type:'manual_strength',local_date:day(22),confidence:'high',evidence:['same_week_manual_strength']}]),linkPlannedSessionManualStrength:vi.fn().mockResolvedValue({id:'link',planned_training_session_id:'strength-session',completed_activity_id:null,manual_strength_session_id:'manual-strength',match_source:'manual',match_confidence:'high',created_at:new Date().toISOString(),activity:{id:'manual-strength',name:'Fuerza manual',sport:'strength',started_at:day(22)+'T15:42:00Z',timezone:'Europe/Madrid',duration_seconds:3600,distance_meters:null,source_type:'manual_strength'}})} as unknown as ApiClient;
  vi.spyOn(window,'confirm').mockReturnValueOnce(true);
  render(<CalendarPage client={client} athleteId='owner' canManage/>);
  await userEvent.click(await screen.findByRole('gridcell',{name:/21.*Sin actividad vinculada/}));
  await userEvent.click(screen.getByText(/Ver ejecución/));
  await userEvent.click(screen.getByRole('button',{name:'Vincular actividad realizada'}));
  await waitFor(()=>expect(client.plannedSessionActivityCandidates).toHaveBeenCalledWith('strength-session'));
  expect(await screen.findByText(new RegExp(`${dateCaption(22)}.*60 min`))).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Vincular'}));
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('sesión planificada'));
  await waitFor(()=>expect(client.linkPlannedSessionManualStrength).toHaveBeenCalledWith('strength-session','manual-strength'));
  await waitFor(()=>expect(screen.getAllByText('Duración superior').length).toBeGreaterThan(0));
  expect(screen.getByText(/Planificado:/).parentElement).toHaveTextContent('40 min');
  expect(screen.getByText(/Realizado:/).parentElement).toHaveTextContent('1 h 0 min');
});
it('links a completed cycling activity from the month execution panel without moving dates',async()=>{
  window.history.replaceState({},"","/calendar?view=month");
  const initial={...batch('UNMATCHED'),as_of_date:day(28),sessions:[unmatchedSport('cycling')]},linked={...initial,sessions:[linkedSport('cycling')]};
  let calls=0;const client={competitionGoals:vi.fn().mockResolvedValue([]),plannedTrainingSessions:vi.fn().mockResolvedValue([genericPlan('cycling')]),calendarExecution:vi.fn().mockImplementation(async(start,end)=>({...(++calls===1?initial:linked),start_date:start,end_date:end})),plannedSessionActivityCandidates:vi.fn().mockResolvedValue([{id:'other-bike',name:'Otra bici',sport:'cycling',started_at:day(20)+'T15:00:00Z',timezone:'Europe/Madrid',duration_seconds:1800,distance_meters:12000,source_type:'completed_activity',local_date:day(20),confidence:'low',evidence:['sport_compatible','same_week']},{id:'cycling-activity',name:'Bicicleta por la tarde',sport:'cycling',started_at:day(21)+'T15:00:00Z',timezone:'Europe/Madrid',duration_seconds:4320,distance_meters:34800,source_type:'completed_activity',local_date:day(21),confidence:'medium',evidence:['sport_compatible','same_week']}]),linkPlannedSessionActivity:vi.fn().mockResolvedValue({id:'link',planned_training_session_id:'cycling-session',completed_activity_id:'cycling-activity',match_source:'manual',match_confidence:'high',created_at:new Date().toISOString(),activity:{id:'cycling-activity',name:'Bicicleta por la tarde',sport:'cycling',started_at:day(21)+'T15:00:00Z',timezone:'Europe/Madrid',duration_seconds:4320,distance_meters:34800,source_type:'completed_activity'}})} as unknown as ApiClient;
  vi.spyOn(window,'confirm').mockReturnValueOnce(true);
  render(<CalendarPage client={client} athleteId='owner' canManage/>);
  await userEvent.click(await screen.findByRole('gridcell',{name:/22.*Sin actividad vinculada/}));
  await userEvent.click(screen.getByText(/Ver ejecuci/));
  await userEvent.click(screen.getByRole('button',{name:'Vincular actividad realizada'}));
  expect(await screen.findByText('Bicicleta por la tarde')).toBeVisible();
  expect(screen.getByText(new RegExp(`${dateCaption(21)}.*72 min`))).toBeVisible();
  expect(screen.getByText(/34,8 km/)).toBeVisible();
  await userEvent.click(within(screen.getByText('Bicicleta por la tarde').closest('article')!).getByRole('button',{name:'Vincular'}));
  expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining(dateCaption(22)));
  await waitFor(()=>expect(client.linkPlannedSessionActivity).toHaveBeenCalledWith('cycling-session','cycling-activity'));
  await waitFor(()=>expect(screen.getAllByText('Duración superior').length).toBeGreaterThan(0));
  expect(screen.getByText(/Planificado:/).parentElement).toHaveTextContent('1 h 0 min');
  expect(screen.getByText(/Realizado:/).parentElement).toHaveTextContent('1 h 12 min');
  expect(screen.getByRole('link',{name:'Ver actividad'}).getAttribute('href')).toBe('/activities/cycling-activity');
});
it.each([['running',23],['swimming',20]] as const)('links a completed %s activity from execution detail with explicit cross-day confirmation',async(sport,actualDay)=>{
  const value=unmatchedSport(sport,`${sport}-session`,day(22));
  const client={plannedSessionActivityCandidates:vi.fn().mockResolvedValue([{id:`${sport}-activity`,name:`${sport} realizada`,sport,started_at:day(actualDay)+'T08:00:00Z',timezone:'Europe/Madrid',duration_seconds:1800,distance_meters:sport==='swimming'?1200:5000,source_type:'completed_activity',local_date:day(actualDay),confidence:'medium',evidence:['sport_compatible','same_week']}]),linkPlannedSessionActivity:vi.fn().mockResolvedValue({})} as unknown as ApiClient;
  vi.spyOn(window,'confirm').mockReturnValueOnce(true);
  render(<CalendarExecutionDetail value={value} timezone='Europe/Madrid' client={client} athleteId='owner' canManage/>);
  await userEvent.click(screen.getByText(/Ver ejecuci/));
  await userEvent.click(screen.getByRole('button',{name:'Vincular actividad realizada'}));
  expect(await screen.findByText(`${sport} realizada`)).toBeVisible();
  await userEvent.click(screen.getByRole('button',{name:'Vincular'}));
  expect(window.confirm).toHaveBeenCalled();
  await waitFor(()=>expect(client.linkPlannedSessionActivity).toHaveBeenCalledWith(`${sport}-session`,`${sport}-activity`));
});
it('hides manual linking without permission and reports candidate lookup errors',async()=>{
  window.history.replaceState({},"","/calendar?view=month");
  const data={...batch('UNMATCHED'),as_of_date:day(28),sessions:[strength()]};
  const readonly={...api(data),plannedTrainingSessions:vi.fn().mockResolvedValue([strengthPlan])} as unknown as ApiClient;
  render(<CalendarPage client={readonly} athleteId='owner' canManage={false}/>);
  await userEvent.click(await screen.findByRole('gridcell',{name:/21.*Sin actividad vinculada/}));
  await userEvent.click(screen.getByText(/Ver ejecución/));
  expect(screen.queryByRole('button',{name:'Vincular actividad realizada'})).not.toBeInTheDocument();
  cleanup();
  window.history.replaceState({},"","/calendar?view=month");
  const failing={...api(data),plannedTrainingSessions:vi.fn().mockResolvedValue([strengthPlan]),plannedSessionActivityCandidates:vi.fn().mockRejectedValue(new Error('boom'))} as unknown as ApiClient;
  render(<CalendarPage client={failing} athleteId='owner' canManage/>);
  await userEvent.click(await screen.findByRole('gridcell',{name:/21.*Sin actividad vinculada/}));
  await userEvent.click(screen.getByText(/Ver ejecución/));
  await userEvent.click(screen.getByRole('button',{name:'Vincular actividad realizada'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('No se han podido consultar las actividades candidatas.');
});
it('year keeps compact indicators accessible and selection opens the same day in list',async()=>{
  const client=api(batch('PARTIAL'));render(<CalendarPage client={client} athleteId='owner' canManage={false}/>);
  await screen.findByText('Parcial');await userEvent.click(screen.getByRole('button',{name:/^Año$/}));
  const cell=await screen.findByRole('button',{name:/1 evento.*Parcial/});
  expect(within(cell).getByRole('img',{name:'Parcial'})).toBeInTheDocument();
  await userEvent.click(cell);await screen.findByRole('heading',{name:'RUN_EASY'});
  expect(screen.getAllByRole('heading',{name:'RUN_EASY'})).toHaveLength(1);
  expect(screen.getByText('Parcial')).toBeInTheDocument();
});
it('keeps planning available when execution fails and rejects foreign evidence',async()=>{
  window.history.replaceState({},"","/calendar?view=list");
  const client=api({...batch(),athlete_id:'foreign'});render(<CalendarPage client={client} athleteId='owner' canManage={false}/>);
  await screen.findByRole('alert');expect(screen.getAllByRole('heading',{name:'RUN_EASY'})).toHaveLength(3);
  expect(screen.queryByText('Completada')).not.toBeInTheDocument();
});
it('uses the athlete scoped batch endpoint',async()=>{
  const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>batch()});vi.stubGlobal('fetch',fetcher);
  const client=new FetchApiClient('http://local');client.setActiveAthlete('owner');await client.calendarExecution(day(1),day(28));
  expect(fetcher.mock.calls[0][0]).toContain('/dashboard/calendar-execution?start_date=');
  expect(new Headers(fetcher.mock.calls[0][1].headers).get('X-TriCoach-Athlete-Id')).toBe('owner');
});
