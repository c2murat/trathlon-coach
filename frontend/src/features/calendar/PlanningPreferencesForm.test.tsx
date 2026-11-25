import {render,screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,expect,it,vi} from "vitest";
import {emptyPreferences,PlanningPreferencesForm} from "./PlanningPreferencesForm";
it("separates nullable weekly intent from the weekly limit",async()=>{
 const change=vi.fn();
 const value={...emptyPreferences(),max_sessions_per_week:12};
 render(<PlanningPreferencesForm value={value} onChange={change} disabled={false}/>);
 const target=screen.getByLabelText("Sesiones por semana");
 expect(target).toHaveValue(null);
 expect(screen.getByLabelText("Máximo de sesiones por semana")).toHaveValue(12);
 await userEvent.type(target,"6");
 expect(change).toHaveBeenLastCalledWith(expect.objectContaining({target_sessions_per_week:6,max_sessions_per_week:12}));
});
describe("PlanningPreferencesForm",()=>{it("exposes seven accessible day controls and emits changes",async()=>{const change=vi.fn();render(<PlanningPreferencesForm value={emptyPreferences()} onChange={change} disabled={false}/>);expect(screen.getByLabelText("Minutos Lunes")).toBeInTheDocument();expect(screen.getByLabelText("Sesiones Domingo")).toBeInTheDocument();await userEvent.click(screen.getByRole("checkbox",{name:"Disponibilidad Lunes"}));expect(change).toHaveBeenCalled()})});
