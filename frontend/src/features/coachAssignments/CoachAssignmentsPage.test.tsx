import {render,screen,waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,it,expect,vi} from "vitest";
import {CoachAssignmentsPage} from "./CoachAssignmentsPage";
import type {ApiClient} from "../../services/apiClient";

const candidates={coaches:[{user_id:"coach-1",display_name:"Entrenador Uno",email:"coach@example.test"}],athletes:[{athlete_profile_id:"athlete-1",display_name:"Atleta Uno"}]};
const assignment={membership_id:"membership-1",coach_user_id:"coach-1",coach_display_name:"Entrenador Uno",coach_email:"coach@example.test",athlete_profile_id:"athlete-1",athlete_display_name:"Atleta Uno",is_active:true,is_default:true};
function setup(items:any[]=[]){const client={coachAssignmentCandidates:vi.fn().mockResolvedValue(candidates),coachAssignments:vi.fn().mockResolvedValue(items),createCoachAssignment:vi.fn().mockResolvedValue(assignment),revokeCoachAssignment:vi.fn().mockResolvedValue({...assignment,is_active:false})} as unknown as ApiClient;return{client,...render(<CoachAssignmentsPage client={client}/>)}}

describe("CoachAssignmentsPage",()=>{
 it("loads candidates and shows the empty assignment state",async()=>{setup();expect(await screen.findByText("Todavía no hay asignaciones activas.")).toBeVisible();expect(screen.getByRole("option",{name:/Entrenador Uno/})).toBeVisible();expect(screen.getByRole("option",{name:"Atleta Uno"})).toBeVisible()});
 it("assigns and refreshes",async()=>{const {client}=setup();await screen.findByText("Todavía no hay asignaciones activas.");await userEvent.click(screen.getByRole("button",{name:"Asignar entrenador"}));await waitFor(()=>expect(client.createCoachAssignment).toHaveBeenCalledWith({coach_user_id:"coach-1",athlete_profile_id:"athlete-1"}));expect(client.coachAssignments).toHaveBeenCalledTimes(2)});
 it("confirms revocation and refreshes",async()=>{vi.spyOn(window,"confirm").mockReturnValue(true);const {client}=setup([assignment]);await screen.findAllByText("Atleta Uno");await userEvent.click(screen.getByRole("button",{name:"Quitar acceso"}));expect(window.confirm).toHaveBeenCalledWith("¿Quitar a Entrenador Uno el acceso a Atleta Uno?");await waitFor(()=>expect(client.revokeCoachAssignment).toHaveBeenCalledWith("membership-1"))});
 it("shows a retryable load error",async()=>{const client={coachAssignmentCandidates:vi.fn().mockRejectedValueOnce(new Error("network")).mockResolvedValue(candidates),coachAssignments:vi.fn().mockRejectedValueOnce(new Error("network")).mockResolvedValue([])} as unknown as ApiClient;render(<CoachAssignmentsPage client={client}/>);await userEvent.click(await screen.findByRole("button",{name:"Reintentar"}));expect(await screen.findByText("Todavía no hay asignaciones activas.")).toBeVisible()});
});
