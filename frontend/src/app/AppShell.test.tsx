import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { ThemeProvider } from "./ThemeProvider";
import {AthleteContextProvider} from "./AthleteContext";
import type {ApiClient} from "../services/apiClient";
import {AuthProvider} from "./AuthContext";

vi.mock("../features/manualStrength/ManualStrengthPage", () => ({
  ManualStrengthPage: () => <h1>Fuerza manual de prueba</h1>,
}));
vi.mock("../features/trainingStatus/TrainingStatusPage", () => ({
  TrainingStatusPage: () => <h1>Estado de entrenamiento de prueba</h1>,
}));
vi.mock("../components/ActivitySyncButton",()=>({ActivitySyncButton:()=>null,activitySyncCompletedEvent:"tricoach:activity-sync-completed"}));

const session={user:{id:"user-1",display_name:"Ana",email:"ana@example.test"},athletes:[{athlete_id:"athlete-a",label:"Mi atleta",role:"owner",is_default:true,capabilities:["read_athlete_data"]}],selected_athlete_id:"athlete-a",selection_required:false} as any;
function shellClient(context=session):ApiClient{return {authMe:vi.fn().mockResolvedValue({id:"user-1",display_name:"Ana",email:"ana@example.test",authentication_mode:"session"}),login:vi.fn(),logout:vi.fn(),getAccount:vi.fn().mockResolvedValue({id:"user-1",email:"ana@example.test",display_name:"Ana",created_at:"2026-08-10T10:00:00Z",last_login_at:null}),updateAccount:vi.fn().mockResolvedValue({id:"user-1",email:"ana@example.test",display_name:"Ana Nueva",created_at:"2026-08-10T10:00:00Z",last_login_at:null}),changePassword:vi.fn(),sessionContext:vi.fn().mockResolvedValue(context),health:vi.fn().mockResolvedValue({status:"ok"}),stravaStatus:vi.fn().mockResolvedValue({connected:false}),activities:vi.fn().mockResolvedValue({total:0,limit:10,offset:0,items:[]}),browseActivities:vi.fn().mockResolvedValue({total:0,limit:20,offset:0,items:[]}),activityDetail:vi.fn().mockResolvedValue(null),activityFilterOptions:vi.fn().mockResolvedValue({sport_types:[],visibility_values:[],minimum_activity_date:null,maximum_activity_date:null}),latestImport:vi.fn().mockResolvedValue({status:"not_started"}),startImport:vi.fn().mockResolvedValue({job_id:"job",status:"queued"}),importStatus:vi.fn().mockResolvedValue({job_id:"job",status:"succeeded"}),dashboardSummary:vi.fn().mockResolvedValue(null),dashboardTrends:vi.fn().mockResolvedValue([]),dashboardConsistency:vi.fn().mockResolvedValue(null),performanceProfile:vi.fn().mockResolvedValue({profile:null,derived:{}}),performanceProfileHistory:vi.fn().mockResolvedValue([]),performanceReferences:vi.fn().mockResolvedValue([]),performanceZones:vi.fn().mockResolvedValue([]),startStravaConnection:vi.fn().mockResolvedValue({authorization_url:"https://www.strava.com/oauth/authorize?state=opaque"})} as unknown as ApiClient}
function renderShell(path: string,context=session) {
  window.history.replaceState({}, "", path);
  const client=shellClient(context);
  return {client,...render(
    <ThemeProvider>
      <AuthProvider client={client}><AthleteContextProvider client={client}><AppShell client={client}/></AthleteContextProvider></AuthProvider>
    </ThemeProvider>,
  )};
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
  it("uses technical capabilities without rendering the membership role in the athlete header",async()=>{const coach={...session,athletes:[{...session.athletes[0],role:"coach",capabilities:["read_athlete_data","create_performance_profile","create_performance_reference"]}]};renderShell("/settings/performance-profile",coach);expect(await screen.findByRole("button",{name:"Crear primera versión"})).toBeVisible();expect(screen.getByRole("button",{name:"Nueva referencia"})).toBeVisible();expect(screen.queryByText("Entrenador")).not.toBeInTheDocument()});
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
    for(const name of ["Carga de entrenamiento","Estado de forma","Cuenta","Perfil de rendimiento"]){
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

  it("shows and activates Cuenta before Perfil de rendimiento",async()=>{renderShell("/settings/account");const accountLink=screen.getByRole("link",{name:"Cuenta"});expect(accountLink).toHaveAttribute("href","/settings/account");expect(accountLink).toHaveClass("nav-link--active");expect(await screen.findByRole("heading",{name:"Cuenta"})).toBeVisible();const labels=screen.getAllByRole("link").map(link=>link.textContent);expect(labels.indexOf("Cuenta")).toBeLessThan(labels.indexOf("Perfil de rendimiento"))});

  it("refreshes the shell name and avatar after a successful account update",async()=>{const {client}=renderShell("/settings/account");vi.mocked(client.authMe).mockResolvedValue({id:"user-1",display_name:"Ana Nueva",email:"ana@example.test",authentication_mode:"session"});const input=await screen.findByLabelText("Nombre visible");await userEvent.clear(input);await userEvent.type(input,"Ana Nueva");await userEvent.click(screen.getByRole("button",{name:"Guardar nombre"}));await waitFor(()=>expect(document.querySelector(".topbar__greeting strong")).toHaveTextContent("Ana Nueva"));expect(screen.getByLabelText("Usuario: Ana Nueva")).toHaveTextContent("A")});

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
  it("opens the shared accessible new-athlete form from the selector",async()=>{renderShell("/dashboard");const trigger=await screen.findByRole("button",{name:/Nuevo atleta/});await userEvent.click(trigger);expect(screen.getByRole("dialog",{name:"Nuevo atleta"})).toBeInTheDocument();await userEvent.click(screen.getByRole("button",{name:"Cancelar"}));await waitFor(()=>expect(trigger).toHaveFocus())});
  it("lets a user without athletes create the first one",async()=>{renderShell("/dashboard",{...session,athletes:[],selected_athlete_id:null,selection_required:false});const trigger=await screen.findByRole("button",{name:"Crear mi primer atleta"});await userEvent.click(trigger);expect(screen.getByRole("dialog",{name:"Nuevo atleta"})).toBeInTheDocument()});  it("shows only athlete names for two owner memberships and keeps the account identity while switching both ways",async()=>{const owners={...session,athletes:[{...session.athletes[0],athlete_id:"athlete-a",label:"Carlos Murat",role:"owner"},{...session.athletes[0],athlete_id:"athlete-b",label:"Jenny Ruiz",role:"owner",is_default:false}],selected_athlete_id:"athlete-a"};renderShell("/dashboard",owners);const selector=await screen.findByRole("combobox",{name:"Seleccionar atleta"});expect(Array.from((selector as HTMLSelectElement).options).map(option=>option.textContent)).toEqual(["Selecciona…","Carlos Murat","Jenny Ruiz"]);expect(screen.queryByText("Propietario")).not.toBeInTheDocument();expect(document.querySelector(".topbar__greeting strong")).toHaveTextContent("Ana");await userEvent.selectOptions(selector,"athlete-b");expect(selector).toHaveValue("athlete-b");expect(document.querySelector(".topbar__greeting strong")).toHaveTextContent("Ana");expect(screen.queryByText("Propietario")).not.toBeInTheDocument();await userEvent.selectOptions(selector,"athlete-a");expect(selector).toHaveValue("athlete-a");expect(screen.queryByText("Propietario")).not.toBeInTheDocument()});  it("renders a single owner athlete by profile name without a membership label",async()=>{renderShell("/dashboard",{...session,athletes:[{...session.athletes[0],label:"Jenny Ruiz",role:"owner"}]});expect(await screen.findByText("Jenny Ruiz")).toBeInTheDocument();expect(screen.queryByText("Propietario")).not.toBeInTheDocument();expect(screen.queryByText("Jenny Ruiz · Propietario")).not.toBeInTheDocument()});});
