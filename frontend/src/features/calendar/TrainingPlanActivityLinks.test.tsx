import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import type {ApiClient} from "../../services/apiClient";
import type {PlannedSessionActivityLink,TrainingPlan} from "../../types/planning";
import {TrainingPlanPage} from "./TrainingPlanPage";

const session={id:"session-a",scheduled_date:"2026-08-28",sport:"running",title:"Easy",description:null,planned_duration_seconds:2700,workout:null};
const plan:TrainingPlan={id:"plan-a",athlete_profile_id:"athlete-a",title:"Plan",start_date:"2026-08-27",end_date:"2026-08-29",status:"active",origin:"ai",algorithm_version:"0.8F.6",goals:[],sessions:[session]};
const link:PlannedSessionActivityLink={id:"link-a",planned_training_session_id:"session-a",completed_activity_id:"activity-a",match_source:"automatic",match_confidence:"high",created_at:"2026-08-28T10:00:00Z",activity:{id:"activity-a",name:"Run",sport:"running",started_at:"2026-08-28T08:00:00Z",timezone:"Europe/Madrid",duration_seconds:2640,distance_meters:8100}};
const base=()=>({trainingPlan:vi.fn().mockResolvedValue(plan),plannedSessionActivityLinks:vi.fn().mockResolvedValue([])}) as unknown as ApiClient;

describe("planned session activity links",()=>{
 beforeEach(()=>window.history.replaceState({},"","/calendar/training-plans/plan-a"));afterEach(()=>vi.restoreAllMocks());
 it("shows automatic link, activity navigation and confirmed unlink",async()=>{
  const client=base();client.plannedSessionActivityLinks=vi.fn().mockResolvedValue([link]);client.unlinkPlannedSessionActivity=vi.fn().mockResolvedValue(undefined);vi.spyOn(window,"confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);
  expect(await screen.findByText("Vinculada automáticamente")).toBeVisible();expect(screen.getByRole("link",{name:"Ver actividad"})).toHaveAttribute("href","/activities/activity-a");
  await userEvent.click(screen.getByRole("button",{name:"Desvincular"}));expect(client.unlinkPlannedSessionActivity).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Desvincular"}));await waitFor(()=>expect(client.unlinkPlannedSessionActivity).toHaveBeenCalledTimes(1));expect(screen.getByText("No hay una actividad vinculada.")).toBeVisible();
 });
 it("loads candidates, blocks duplicate submit and creates a manual N:M link",async()=>{
  let resolve!:(value:PlannedSessionActivityLink)=>void;const client=base();client.plannedSessionActivityCandidates=vi.fn().mockResolvedValue([{...link.activity,local_date:"2026-08-28",confidence:"high",evidence:[]}]);client.linkPlannedSessionActivity=vi.fn().mockReturnValue(new Promise(done=>{resolve=done}));
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);await userEvent.click(await screen.findByRole("button",{name:"Buscar actividad"}));expect(await screen.findByText(/28.*ago.*2026.*10:00/i)).toBeVisible();expect(screen.queryByText(link.activity.started_at)).not.toBeInTheDocument();const button=screen.getByRole("button",{name:"Vincular"});await userEvent.dblClick(button);expect(client.linkPlannedSessionActivity).toHaveBeenCalledTimes(1);expect(screen.getByRole("button",{name:"Vinculando…"})).toBeDisabled();resolve({...link,match_source:"manual"});expect(await screen.findByText("Vinculada manualmente")).toBeVisible();
 });
 it("keeps ambiguous auto-match candidates reviewable without creating a link",async()=>{
  const candidate={...link.activity,local_date:"2026-08-28",confidence:"high" as const,evidence:[]};const client=base();client.autoMatchPlannedSessionActivity=vi.fn().mockResolvedValue({classification:"ambiguous",reason:"insufficient_margin",candidates:[candidate],link:null});
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);await userEvent.click(await screen.findByRole("button",{name:"Buscar coincidencia automática"}));expect(await screen.findByText("Hemos encontrado varias actividades posibles. Selecciona la correcta.")).toBeVisible();expect(screen.getByRole("button",{name:"Vincular"})).toBeEnabled();expect(screen.getByRole("button",{name:"Buscar coincidencia automática"})).toBeEnabled();expect(screen.queryByText(/AMBIGUOUS/)).not.toBeInTheDocument();expect(screen.queryByText(/Vinculada (manual|automáticamente)/)).not.toBeInTheDocument();
 });
 it("releases auto-match after an error, blocks double submit and allows retry",async()=>{
  let reject!:(reason:Error)=>void;const pending=new Promise((_,fail)=>{reject=fail});const client=base();client.autoMatchPlannedSessionActivity=vi.fn().mockReturnValueOnce(pending).mockResolvedValueOnce({classification:"no_match",reason:"threshold_not_met",candidates:[],link:null});
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);const button=await screen.findByRole("button",{name:"Buscar coincidencia automática"});await userEvent.dblClick(button);expect(client.autoMatchPlannedSessionActivity).toHaveBeenCalledTimes(1);expect(screen.getByRole("button",{name:"Buscando…"})).toBeDisabled();reject(new Error("controlled_failure"));expect(await screen.findByRole("alert")).toHaveTextContent("No se ha podido completar la operación");expect(screen.getByRole("button",{name:"Buscar coincidencia automática"})).toBeEnabled();await userEvent.click(screen.getByRole("button",{name:"Buscar coincidencia automática"}));expect(client.autoMatchPlannedSessionActivity).toHaveBeenCalledTimes(2);expect(await screen.findByText("No hemos encontrado una coincidencia segura.")).toBeVisible();expect(screen.queryByText(/Vinculada (manual|automáticamente)/)).not.toBeInTheDocument();
 });
 it("discards stale link responses when athlete changes",async()=>{
  let oldResolve!:(value:PlannedSessionActivityLink[])=>void;let calls=0;const client=base();client.plannedSessionActivityLinks=vi.fn().mockImplementation(()=>++calls===1?new Promise(done=>{oldResolve=done}):Promise.resolve([]));const view=render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);await screen.findByText("Easy");view.rerender(<TrainingPlanPage client={client} athleteId="athlete-b" canManage/>);oldResolve([link]);await waitFor(()=>expect(client.plannedSessionActivityLinks).toHaveBeenCalledTimes(2));expect(screen.queryByText("Vinculada automáticamente")).not.toBeInTheDocument();
 });
});
