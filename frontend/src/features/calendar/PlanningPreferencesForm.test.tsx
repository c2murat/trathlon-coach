import {render,screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe,expect,it,vi} from "vitest";
import {emptyPreferences,PlanningPreferencesForm} from "./PlanningPreferencesForm";
describe("PlanningPreferencesForm",()=>{it("exposes seven accessible day controls and emits changes",async()=>{const change=vi.fn();render(<PlanningPreferencesForm value={emptyPreferences()} onChange={change} disabled={false}/>);expect(screen.getByLabelText("Minutos Lunes")).toBeInTheDocument();expect(screen.getByLabelText("Sesiones Domingo")).toBeInTheDocument();await userEvent.click(screen.getByRole("checkbox",{name:"Disponibilidad Lunes"}));expect(change).toHaveBeenCalled()})});
