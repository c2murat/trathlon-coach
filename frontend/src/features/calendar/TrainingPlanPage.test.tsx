import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import type {ApiClient} from "../../services/apiClient";
import type {TrainingPlan} from "../../types/planning";
import {TrainingPlanPage} from "./TrainingPlanPage";

const plan=(status:string,title="Lifecycle plan"):TrainingPlan=>({
 id:"plan-a",athlete_profile_id:"athlete-a",title,
 start_date:"2026-08-27",end_date:"2026-08-29",status,
 origin:"ai",algorithm_version:"0.8F.6",goals:[],sessions:[],
});
const clientFor=(value:TrainingPlan)=>({trainingPlan:vi.fn().mockResolvedValue(value)}) as unknown as ApiClient;

describe("TrainingPlanPage lifecycle",()=>{
 beforeEach(()=>window.history.replaceState({},"","/calendar/training-plans/plan-a"));
 afterEach(()=>vi.restoreAllMocks());

 it.each([
  ["completed","Completado","Plan completado"],
  ["archived","Archivado","Plan archivado"],
 ])("shows final %s state without lifecycle actions",async(status,label,message)=>{
  render(<TrainingPlanPage client={clientFor(plan(status))} athleteId="athlete-a" canManage/>);
  expect(await screen.findByText(new RegExp(`Estado: ${label}`))).toBeVisible();
  expect(screen.getByText(message)).toBeVisible();
  expect(screen.queryByRole("button",{name:"Activar plan"})).not.toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Marcar como completado"})).not.toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Archivar"})).not.toBeInTheDocument();
 });

 it("does not complete when confirmation is cancelled",async()=>{
  vi.spyOn(window,"confirm").mockReturnValue(false);
  const client=clientFor(plan("active"));client.completeTrainingPlan=vi.fn();
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);
  await userEvent.click(await screen.findByRole("button",{name:"Marcar como completado"}));
  expect(window.confirm).toHaveBeenCalledOnce();
  expect(client.completeTrainingPlan).not.toHaveBeenCalled();
  expect(screen.getByText(/Estado: Activo/)).toBeVisible();
  expect(screen.getByRole("button",{name:"Marcar como completado"})).toBeEnabled();
 });

 it("completes once, shows loading and updates locally",async()=>{
  vi.spyOn(window,"confirm").mockReturnValue(true);
  let resolve!:(value:TrainingPlan)=>void;
  const client=clientFor(plan("active"));client.completeTrainingPlan=vi.fn().mockReturnValue(new Promise(done=>{resolve=done}));
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);
  const button=await screen.findByRole("button",{name:"Marcar como completado"});
  await userEvent.dblClick(button);
  expect(client.completeTrainingPlan).toHaveBeenCalledTimes(1);
  expect(client.completeTrainingPlan).toHaveBeenCalledWith("plan-a");
  expect(screen.getByRole("button",{name:"Completando…"})).toBeDisabled();
  resolve(plan("completed"));
  expect(await screen.findByText(/Estado: Completado/)).toBeVisible();
  expect(screen.getByText("Plan completado")).toBeVisible();
  expect(screen.queryByRole("button",{name:"Marcar como completado"})).not.toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Archivar"})).not.toBeInTheDocument();
 });

 it("resets complete loading after error and allows retry",async()=>{
  vi.spyOn(window,"confirm").mockReturnValue(true);
  const client=clientFor(plan("active"));client.completeTrainingPlan=vi.fn().mockRejectedValueOnce(new Error('(409) {"code":"training_plan_invalid_transition"}')).mockResolvedValueOnce(plan("completed"));
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);
  await userEvent.click(await screen.findByRole("button",{name:"Marcar como completado"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("El estado actual del plan");
  expect(screen.getByRole("button",{name:"Marcar como completado"})).toBeEnabled();
  await userEvent.click(screen.getByRole("button",{name:"Marcar como completado"}));
  expect(await screen.findByText(/Estado: Completado/)).toBeVisible();
  expect(client.completeTrainingPlan).toHaveBeenCalledTimes(2);
 });

 it("does not archive when confirmation is cancelled",async()=>{
  vi.spyOn(window,"confirm").mockReturnValue(false);
  const client=clientFor(plan("draft"));client.archiveTrainingPlan=vi.fn();
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);
  await userEvent.click(await screen.findByRole("button",{name:"Archivar"}));
  expect(client.archiveTrainingPlan).not.toHaveBeenCalled();
  expect(screen.getByText(/Estado: Borrador/)).toBeVisible();
  expect(screen.getByRole("button",{name:"Archivar"})).toBeEnabled();
 });

 it("translates active conflict without exposing technical JSON",async()=>{
  const client=clientFor(plan("draft"));client.activateTrainingPlan=vi.fn().mockRejectedValue(new Error('(409) {"code":"training_plan_active_conflict","existing_training_plan_id":"other"}'));
  render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);
  await userEvent.click(await screen.findByRole("button",{name:"Activar plan"}));
  const alert=await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Ya existe otro plan activo para este atleta.");
  expect(alert).not.toHaveTextContent("training_plan_active_conflict");
 });

 it("discards a stale plan response after athlete change",async()=>{
  const resolvers:Array<(value:TrainingPlan)=>void>=[];
  const client={trainingPlan:vi.fn().mockImplementation(()=>new Promise<TrainingPlan>(resolve=>resolvers.push(resolve)))} as unknown as ApiClient;
  const view=render(<TrainingPlanPage client={client} athleteId="athlete-a" canManage/>);
  await waitFor(()=>expect(resolvers).toHaveLength(1));
  view.rerender(<TrainingPlanPage client={client} athleteId="athlete-b" canManage/>);
  await waitFor(()=>expect(resolvers).toHaveLength(2));
  resolvers[0](plan("draft","Plan stale athlete A"));
  await waitFor(()=>expect(screen.queryByText("Plan stale athlete A")).not.toBeInTheDocument());
  resolvers[1]({...plan("active","Plan athlete B"),athlete_profile_id:"athlete-b"});
  expect(await screen.findByRole("heading",{name:"Plan athlete B"})).toBeVisible();
  expect(screen.queryByText("Plan stale athlete A")).not.toBeInTheDocument();
 });
});
