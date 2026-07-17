import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { ThemeProvider } from "./ThemeProvider";
function renderShell(path:string){window.history.replaceState({},"",path);return render(<ThemeProvider><AppShell/></ThemeProvider>)}
beforeEach(()=>{localStorage.clear();Object.defineProperty(window,"matchMedia",{writable:true,value:vi.fn().mockReturnValue({matches:false,addEventListener:vi.fn(),removeEventListener:vi.fn()})})});afterEach(()=>vi.useRealTimers());
describe("AppShell",()=>{
 it("redirects root to dashboard and marks it active",async()=>{renderShell("/");await waitFor(()=>expect(window.location.pathname).toBe("/dashboard"));expect(screen.getByRole("link",{name:/Inicio/i})).toHaveClass("nav-link--active")});
 it("renders reusable coming-soon navigation pages",async()=>{renderShell("/calendar");expect(screen.getByRole("heading",{name:"Calendario"})).toBeInTheDocument();expect(screen.getByText("Versión prevista: 0.9")).toBeInTheDocument();await userEvent.click(screen.getByRole("link",{name:/volver al inicio/i}));expect(window.location.pathname).toBe("/dashboard")});
 it("shows a time-aware Spanish greeting",()=>{vi.useFakeTimers();vi.setSystemTime(new Date("2026-07-14T07:00:00"));renderShell("/settings");expect(screen.getByText(/Buenos días/)).toBeInTheDocument()});
 it("opens and closes the accessible mobile navigation",async()=>{renderShell("/health");const button=screen.getByRole("button",{name:"Abrir menú"});await userEvent.click(button);expect(button).toHaveAttribute("aria-expanded","true");expect(screen.getByRole("button",{name:"Cerrar navegación"})).toBeInTheDocument()});
 it("uses system theme, toggles it and persists the choice",async()=>{Object.defineProperty(window,"matchMedia",{writable:true,value:vi.fn().mockReturnValue({matches:true})});renderShell("/settings");expect(await screen.findByRole("button",{name:"Activar tema claro"})).toBeInTheDocument();await userEvent.click(screen.getByRole("button",{name:"Activar tema claro"}));expect(document.documentElement.dataset.theme).toBe("light");expect(localStorage.getItem("tricoach-theme")).toBe("light")});
 it("restores a persisted theme",async()=>{localStorage.setItem("tricoach-theme","dark");renderShell("/settings");expect(await screen.findByRole("button",{name:"Activar tema claro"})).toBeInTheDocument()});
});
