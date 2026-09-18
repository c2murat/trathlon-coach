import {act,cleanup,render,screen,waitFor,within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach,describe,expect,it,vi} from "vitest";
import {ExecutionOverviewSection,targetAdherenceText} from "./ExecutionOverviewSection";
import {DashboardPage} from "./DashboardPage";
import type {ApiClient} from "../../services/apiClient";
import {FetchApiClient} from "../../services/apiClient";
import type {CompletionStatus,ExecutionOverview,TargetAdherenceEvidence} from "./executionOverviewTypes";
import {activitySyncCompletedEvent} from "../../components/ActivitySyncButton";

afterEach(()=>{cleanup();vi.restoreAllMocks()});
function overview(status:CompletionStatus="COMPLETED",athlete="a"):ExecutionOverview{
  const activity={id:"activity",name:"Carrera del parque",sport:"running",started_at:"2026-09-15T08:00:00Z",
    timezone:"Europe/Madrid",duration_seconds:4260,distance_meters:12000,average_heart_rate_bpm:140,average_power_w:null};
  const session={id:"session",date:"2026-09-15",sport:"running",title:"RUN_EASY",planned_duration_seconds:4500,
    planned_distance_meters:12000,workout:null,evidence:{planned_session_id:"session",completion_status:status,
      actual_duration_seconds:4260,actual_distance_m:12000,comparison_confidence:"HIGH",sport_match:true,
      target_comparison:null,source_activity_ids:[activity.id],link_provenance:[]},activities:status==="UNMATCHED"?[]:[activity]};
  return {athlete_id:athlete,as_of_date:"2026-09-16",window_start_date:"2026-06-24",evidence_version:"0.8G.2C.1",
    latest_activity:activity,latest_activity_sessions:status==="UNMATCHED"?[]:[session],recent_sessions:[session]};
}
const clientFor=(value=overview())=>({executionOverview:vi.fn().mockResolvedValue(value)} as unknown as ApiClient);

describe("Home execution evidence",()=>{
  it.each([["COMPLETED","Completado"],["PARTIAL","Realizado parcialmente"],["OVER_DURATION","Duración superior a la prevista"],
    ["UNKNOWN","No hay datos suficientes para valorar el cumplimiento"],["UNMATCHED","No se ha encontrado una actividad vinculada"]] as const)("translates %s without claiming a missed workout",async(status,label)=>{
      render(<ExecutionOverviewSection client={clientFor(overview(status))} athleteId="a"/>);
      const region=await screen.findByRole("region",{name:"Ejecución de tus entrenamientos"});
      expect(within(region).getAllByText(label).length).toBeGreaterThan(0);
      expect(region.textContent).not.toMatch(/COMPLETED|PARTIAL|OVER_DURATION|UNKNOWN|UNMATCHED|No cumplido|score/i);
      expect(within(region).getByRole("heading",{name:"Último entrenamiento"})).toBeInTheDocument();
      expect(within(region).getByRole("heading",{name:"Sesiones recientes"})).toBeInTheDocument();
  });
  it("shows planned and performed durations, distance, date and activity",async()=>{
    render(<ExecutionOverviewSection client={clientFor()} athleteId="a"/>);
    await screen.findByRole("region",{name:"Ejecución de tus entrenamientos"});
    expect(screen.getAllByText(/1 h 15 min/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1 h 11 min/).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link",{name:"Carrera del parque"})[0]).toHaveAttribute("href","/activities/activity");
    expect(screen.getAllByText(/12 km/).length).toBeGreaterThan(0);
    expect(screen.getByText("15 de septiembre de 2026")).toHaveAttribute("datetime","2026-09-15");
  });
  it("uses existing target evidence without inventing hit counts from a rounded fraction",()=>{
    const target:TargetAdherenceEvidence={matched_repetitions:5,planned_repetitions:5,target_hit_fraction:"1.00",execution_relation:"WITHIN_TARGET",confidence:"HIGH"};
    expect(targetAdherenceText(target)).toBe("Objetivos comprobados cumplidos");
    expect(targetAdherenceText({...target,target_hit_fraction:"0.60"})).toBe("Objetivos parcialmente cumplidos");
    expect(targetAdherenceText({...target,matched_repetitions:3})).toBe("Objetivos parcialmente cumplidos");
    expect(targetAdherenceText(null)).toContain("No hay datos suficientes");
    expect(targetAdherenceText({...target,confidence:"LOW"})).toContain("No hay datos suficientes");
  });
  it.each([true,false])("renders structured targets and the supported adherence message (%s)",async available=>{
    const data=overview();const session=data.recent_sessions[0];
    session.workout={schema_version:1,sport:"running",steps:[{kind:"repeat",repetitions:5,steps:[{kind:"step",phase:"work",duration:{mode:"time",seconds:120},target:{metric:"pace",mode:"absolute",minimum:220,maximum:230,reference_unit:"seconds_per_km"}}]}]};
    session.evidence!.target_comparison=available?{matched_repetitions:5,planned_repetitions:5,target_hit_fraction:"1",execution_relation:"WITHIN_TARGET",confidence:"HIGH"}:null;
    render(<ExecutionOverviewSection client={clientFor(data)} athleteId="a"/>);
    await screen.findByRole("region",{name:"Ejecución de tus entrenamientos"});
    expect(screen.getAllByText(available?"Objetivos comprobados cumplidos":"No hay datos suficientes para comprobar los intervalos").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Ver entrenamiento/).length).toBeGreaterThan(0);
    if(available)expect(screen.getAllByText("Repeticiones comparadas: 5 de 5.").length).toBeGreaterThan(0);
  });
  it("refreshes on the existing successful sync event and ignores another athlete",async()=>{
    const client=clientFor(overview("UNMATCHED"));
    render(<ExecutionOverviewSection client={client} athleteId="a"/>);
    await screen.findByText("No se ha encontrado una actividad vinculada");
    act(()=>window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent,{detail:{athleteId:"b"}})));
    expect(client.executionOverview).toHaveBeenCalledTimes(1);
    vi.mocked(client.executionOverview!).mockResolvedValue(overview());
    act(()=>window.dispatchEvent(new CustomEvent(activitySyncCompletedEvent,{detail:{athleteId:"a"}})));
    await screen.findAllByText("Completado");expect(client.executionOverview).toHaveBeenCalledTimes(2);
  });
  it("clears previous athlete immediately and ignores a late response",async()=>{
    let finish!:(value:ExecutionOverview)=>void;
    const client=clientFor();vi.mocked(client.executionOverview!).mockResolvedValueOnce(overview()).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve})).mockResolvedValueOnce(overview("PARTIAL","c"));
    const view=render(<ExecutionOverviewSection client={client} athleteId="a"/>);
    await screen.findAllByText("Completado");
    view.rerender(<ExecutionOverviewSection client={client} athleteId="b"/>);
    expect(screen.queryByText("Completado")).not.toBeInTheDocument();
    view.rerender(<ExecutionOverviewSection client={client} athleteId="c"/>);
    await screen.findAllByText("Realizado parcialmente");
    await act(async()=>finish(overview("OVER_DURATION","b")));
    expect(screen.queryByText("Duración superior a la prevista")).not.toBeInTheDocument();
  });
  it("distinguishes query errors from unmatched sessions",async()=>{
    const client=clientFor();vi.mocked(client.executionOverview!).mockRejectedValue(new Error("network"));
    render(<ExecutionOverviewSection client={client} athleteId="a"/>);
    await screen.findByRole("alert");
    expect(screen.queryByText("No se ha encontrado una actividad vinculada")).not.toBeInTheDocument();
  });
  it("Home displays completed evidence after the actual sync button finishes",async()=>{
    const client={executionOverview:vi.fn().mockResolvedValueOnce(overview("UNMATCHED")).mockResolvedValue(overview()),
      health:vi.fn().mockResolvedValue({}),stravaStatus:vi.fn().mockResolvedValue({connected:true}),
      activities:vi.fn().mockResolvedValue({total:0,items:[]}),latestImport:vi.fn().mockResolvedValue({status:"not_started"}),
      dashboardSummary:vi.fn().mockResolvedValue(null),dashboardTrends:vi.fn().mockResolvedValue([]),dashboardConsistency:vi.fn().mockResolvedValue(null),
      startImport:vi.fn().mockResolvedValue({job_id:"job"}),importStatus:vi.fn().mockResolvedValue({job_id:"job",status:"succeeded",processed_count:1})} as unknown as ApiClient;
    render(<DashboardPage client={client} athleteId="a"/>);
    await screen.findByText("No se ha encontrado una actividad vinculada");
    await userEvent.click(screen.getByRole("button",{name:"Sincronizar actividades"}));
    await screen.findAllByText("Completado");
    await waitFor(()=>expect(client.executionOverview).toHaveBeenCalledTimes(2));
  });
  it("uses the central client and athlete-scoped GET",async()=>{
    const fetch=vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify(overview()),{status:200}));
    const client=new FetchApiClient("http://api");client.setActiveAthlete("a");await client.executionOverview();
    const [url,init]=fetch.mock.calls[0];expect(String(url)).toBe("http://api/dashboard/execution-overview");
    expect(new Headers(init?.headers).get("X-TriCoach-Athlete-Id")).toBe("a");
    expect(init?.method??"GET").toBe("GET");
  });
});
