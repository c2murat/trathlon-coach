import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { ThemeProvider } from "./ThemeProvider";
import {AthleteContextProvider} from "./AthleteContext";
import type {ApiClient} from "../services/apiClient";

vi.mock("../features/manualStrength/ManualStrengthPage", () => ({
  ManualStrengthPage: () => <h1>Fuerza manual de prueba</h1>,
}));
vi.mock("../features/trainingStatus/TrainingStatusPage", () => ({
  TrainingStatusPage: () => <h1>Estado de entrenamiento de prueba</h1>,
}));
vi.mock("../components/ActivitySyncButton",()=>({ActivitySyncButton:()=>null,activitySyncCompletedEvent:"tricoach:activity-sync-completed"}));

const session={user:{id:"user-1",display_name:"Ana",email:"ana@example.test"},athletes:[{athlete_id:"athlete-a",label:"Mi atleta",role:"owner",is_default:true,capabilities:["read_athlete_data"]}],selected_athlete_id:"athlete-a",selection_required:false} as any;
function shellClient(context=session):ApiClient{return {sessionContext:vi.fn().mockResolvedValue(context),health:vi.fn().mockResolvedValue({status:"ok"}),stravaStatus:vi.fn().mockResolvedValue({connected:false}),activities:vi.fn().mockResolvedValue({total:0,limit:10,offset:0,items:[]}),browseActivities:vi.fn().mockResolvedValue({total:0,limit:20,offset:0,items:[]}),activityDetail:vi.fn().mockResolvedValue(null),activityFilterOptions:vi.fn().mockResolvedValue({sport_types:[],visibility_values:[],minimum_activity_date:null,maximum_activity_date:null}),latestImport:vi.fn().mockResolvedValue({status:"not_started"}),startImport:vi.fn().mockResolvedValue({job_id:"job",status:"queued"}),importStatus:vi.fn().mockResolvedValue({job_id:"job",status:"succeeded"}),dashboardSummary:vi.fn().mockResolvedValue(null),dashboardTrends:vi.fn().mockResolvedValue([]),dashboardConsistency:vi.fn().mockResolvedValue(null),performanceProfile:vi.fn().mockResolvedValue({profile:null,derived:{}}),performanceProfileHistory:vi.fn().mockResolvedValue([]),performanceReferences:vi.fn().mockResolvedValue([]),performanceZones:vi.fn().mockResolvedValue([]),startStravaConnection:vi.fn().mockResolvedValue({authorization_url:"https://www.strava.com/oauth/authorize?state=opaque"})} as unknown as ApiClient}
function renderShell(path: string,context=session) {
  window.history.replaceState({}, "", path);
  const client=shellClient(context);
  return render(
    <ThemeProvider>
      <AthleteContextProvider client={client}><AppShell client={client}/></AthleteContextProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();

  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AppShell", () => {
it("marks profile and reference actions as denied for read-only capabilities",async()=>{const viewer={...session,athletes:[{...session.athletes[0],role:"viewer",capabilities:["read_athlete_data","read_strava_integration"]}]};renderShell("/settings/performance-profile",viewer);const heading=await screen.findByRole("heading",{name:"Perfil de rendimiento"});expect(heading.closest(".deny-profile")).toHaveClass("deny-reference")});
  it("shows profile and reference actions from capabilities and translates the role",async()=>{const coach={...session,athletes:[{...session.athletes[0],role:"coach",capabilities:["read_athlete_data","create_performance_profile","create_performance_reference"]}]};renderShell("/settings/performance-profile",coach);expect(await screen.findByRole("button",{name:"Crear primera versión"})).toBeVisible();expect(screen.getByRole("button",{name:"Nueva referencia"})).toBeVisible();expect(screen.getByText("Entrenador")).toBeInTheDocument()});
  it("uses accessible decorative SVG icons for primary navigation and keeps subsections icon-free", () => {
    renderShell("/dashboard");
    const navigation=screen.getByRole("complementary",{name:"Navegación principal"});
    for(const name of ["Inicio","Actividades","Fuerza","Calendario","Estadísticas","Salud","Configuración"]){
      const link=screen.getByRole("link",{name});
      const icon=link.querySelector("svg");
      expect(icon).toBeInTheDocument();
      expect(icon).toHaveAttribute("aria-hidden","true");
      expect(icon).toHaveAttribute("focusable","false");
    }
    for(const name of ["Carga de entrenamiento","Estado de forma","Perfil de rendimiento"]){
      const link=screen.getByRole("link",{name});
      expect(link).toHaveClass("nav-subitem");
      expect(link.querySelector("svg")).not.toBeInTheDocument();
    }
    expect(navigation).not.toHaveTextContent("?");
  });

  it("shows and activates the training status route without breaking previous accesses", async () => {
    renderShell("/statistics/training-status");
    const statusLink=screen.getByRole("link",{name:"Estado de forma"});
    expect(statusLink).toHaveAttribute("href","/statistics/training-status");
    expect(statusLink).toHaveClass("nav-link--active");
    expect(await screen.findByRole("heading",{name:"Estado de entrenamiento de prueba"})).toBeInTheDocument();
    expect(screen.getByRole("link",{name:"Carga de entrenamiento"})).toHaveAttribute("href","/statistics/training-load");
    expect(screen.getByRole("link",{name:"Fuerza"})).toHaveAttribute("href","/activities/strength");
  });

  it("shows the strength access, renders its route and marks it active", async () => {
    renderShell("/activities/strength");
    const strengthLink = screen.getByRole("link", { name: "Fuerza" });
    expect(strengthLink).toHaveAttribute("href", "/activities/strength");
    expect(strengthLink).toHaveClass("nav-link--active");
    expect(await screen.findByRole("heading", { name: "Fuerza manual de prueba" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: "Calendario" })).toHaveAttribute("href", "/calendar");
  });

  it("redirects root to dashboard and marks it active", async () => {
    renderShell("/");

    await waitFor(() => {
      expect(window.location.pathname).toBe("/dashboard");
    });

    expect(
      screen.getByRole("link", { name: /Inicio/i }),
    ).toHaveClass("nav-link--active");
  });

  it("renders reusable coming-soon navigation pages", async () => {
    renderShell("/calendar");

    expect(
      await screen.findByRole("heading", { name: "Calendario" }),
    ).toBeInTheDocument();

    const versionText = document.querySelector(".coming-soon__version");

    expect(versionText).toBeInTheDocument();
    expect(versionText).toHaveTextContent(/Versión prevista:/i);
    expect(versionText).toHaveTextContent(/0\.9/);

    await userEvent.click(
      screen.getByRole("link", { name: /volver al inicio/i }),
    );

    expect(window.location.pathname).toBe("/dashboard");
  });

  it("shows a time-aware Spanish greeting", async () => {
    renderShell("/settings");

    await waitFor(()=>expect(document.querySelector(".topbar__greeting strong")).toHaveTextContent("Ana"));const greeting = document.querySelector(".topbar__greeting strong");

    expect(greeting).toBeInTheDocument();
    expect(greeting?.textContent).toContain("Ana");
    expect(screen.queryByText("Carlos")).not.toBeInTheDocument();
expect(greeting?.textContent?.toLowerCase()).toContain("buen");
  });

  it("opens and closes the accessible mobile navigation", async () => {
    renderShell("/health");

    const user = userEvent.setup();
    const openButton = screen.getByRole("button", { name: /Abrir/i });

    expect(openButton).toHaveAttribute("aria-expanded", "false");

    await user.click(openButton);

    expect(openButton).toHaveAttribute("aria-expanded", "true");

const closeButton = document.querySelector(
  ".mobile-menu",
) as HTMLButtonElement;

expect(closeButton).toBeTruthy();

await user.click(closeButton);

    expect(openButton).toHaveAttribute("aria-expanded", "false");
  });

  it("uses system theme, toggles it and persists the choice", async () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockReturnValue({
        matches: true,
      }),
    });

    renderShell("/settings");

    expect(
      await screen.findByRole("button", { name: "Activar tema claro" }),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Activar tema claro" }),
    );

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("tricoach-theme")).toBe("light");
  });

  it("restores a persisted theme", async () => {
    localStorage.setItem("tricoach-theme", "dark");

    renderShell("/settings");

    expect(
      await screen.findByRole("button", { name: "Activar tema claro" }),
    ).toBeInTheDocument();
  });
});
