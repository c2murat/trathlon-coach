import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../services/apiClient";
import type { CompetitionGoal } from "../../types/planning";
import { CalendarPage } from "./CalendarPage";
export const goal: CompetitionGoal = {
  id: "goal-1",
  athlete_profile_id: "athlete-a",
  name: "IRONMAN Valencia",
  event_date: "2027-04-19",
  event_start_time: null,
  timezone: "Europe/Madrid",
  event_category: "triathlon",
  event_format: "70.3",
  priority: "A",
  segments: [
    {
      position: 1,
      sport: "swim",
      distance_m: 1900,
      label: null,
      elevation_gain_m: null,
    },
    {
      position: 2,
      sport: "bike",
      distance_m: 90000,
      label: null,
      elevation_gain_m: null,
    },
    {
      position: 3,
      sport: "run",
      distance_m: 21100,
      label: null,
      elevation_gain_m: null,
    },
  ],
  distance_m: null,
  swim_distance_m: 1900,
  bike_distance_m: 90000,
  run_distance_m: 21100,
  target_finish_time_seconds: 18900,
  notes: null,
  city: null,
  region: null,
  country: null,
  source_provider: null,
  source_external_id: null,
  source_url: null,
  source_retrieved_at: null,
  status: "active",
  created_by_user_id: "user-1",
  created_at: "2026-08-15T10:00:00Z",
  updated_at: "2026-08-15T10:00:00Z",
};
function client(goals: CompetitionGoal[] = []): ApiClient {
  return {
    competitionGoals: vi.fn().mockResolvedValue(goals),
    createCompetitionGoal: vi.fn().mockResolvedValue(goal),
    updateCompetitionGoal: vi.fn().mockResolvedValue(goal),
    deleteCompetitionGoal: vi.fn().mockResolvedValue(undefined),
    competitionCatalogProviders: vi.fn().mockResolvedValue([]),
    importCompetitionGoal: vi.fn(),
  } as unknown as ApiClient;
}
describe("Calendar competition goals", () => {
  it("shows all translated categories and creates ordered preset segments", async () => {
    const api = client();
    render(<CalendarPage client={api} canManage athleteId="a" />);
    await screen.findByText("Todavía no tienes objetivos ni sesiones planificadas.");
    await userEvent.click(
      screen.getByRole("button", { name: /Añadir objetivo/ }),
    );
    const category = screen.getByLabelText("Tipo de competición");
    for (const label of [
      "Carrera",
      "Ciclismo",
      "Natación",
      "Triatlón",
      "Duatlón",
      "Acuatlón",
    ])
      expect(
        within(category).getByRole("option", { name: label }),
      ).toBeVisible();
    await userEvent.type(screen.getByLabelText("Nombre"), "Valencia");
    await userEvent.type(screen.getByLabelText("Fecha"), "2027-04-19");
    await userEvent.selectOptions(category, "duathlon");
    await userEvent.click(
      screen.getByRole("button", { name: "Guardar objetivo" }),
    );
    expect(api.createCompetitionGoal).toHaveBeenCalledWith(
      expect.objectContaining({
        event_category: "duathlon",
        segments: [
          expect.objectContaining({ sport: "run" }),
          expect.objectContaining({ sport: "bike" }),
          expect.objectContaining({ sport: "run" }),
        ],
      }),
    );
  });
  it("adds, edits and reorders repeated segments", async () => {
    const api = client([goal]);
    render(<CalendarPage client={api} canManage athleteId="a" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Editar objetivo" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Añadir segmento" }),
    );
    expect(screen.getAllByLabelText(/Deporte/)).toHaveLength(4);
    await userEvent.type(screen.getAllByLabelText("Distancia (km)")[3], "1");
    await userEvent.click(
      screen.getByRole("button", { name: "Subir segmento 4" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Guardar objetivo" }),
    );
    expect(api.updateCompetitionGoal).toHaveBeenCalledWith(
      "goal-1",
      expect.objectContaining({
        segments: expect.arrayContaining([
          expect.objectContaining({ sport: "run" }),
        ]),
      }),
    );
  });
  it("shows goals read-only to coach", async () => {
    render(
      <CalendarPage
        client={client([goal])}
        canManage={false}
        athleteName="CARLOS2"
        athleteId="b"
      />,
    );
    expect(await screen.findByText(goal.name)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /Añadir objetivo/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Editar objetivo" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/CARLOS2.*solo lectura/)).toBeVisible();
  });
  it("cancels by current goal id", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const api = client([goal]);
    render(<CalendarPage client={api} canManage athleteId="a" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Cancelar objetivo" }),
    );
    expect(api.deleteCompetitionGoal).toHaveBeenCalledWith("goal-1");
  });
  it("reloads on athlete switch without stale rows", async () => {
    const api = client([goal]);
    vi.mocked(api.competitionGoals!)
      .mockResolvedValueOnce([goal])
      .mockResolvedValueOnce([]);
    const view = render(<CalendarPage client={api} canManage athleteId="a" />);
    await screen.findByText(goal.name);
    view.rerender(
      <CalendarPage client={api} canManage={false} athleteId="b" />,
    );
    expect(
      await screen.findByText(
      "Este atleta todavía no tiene planificación.",
      ),
    ).toBeVisible();
    expect(screen.queryByText(goal.name)).not.toBeInTheDocument();
  });
  it("refreshes and shows an imported objective", async () => {
    const api = client([]);
    vi.mocked(api.competitionCatalogProviders!).mockResolvedValue([
      {
        provider: "fixture",
        label: "Fixture",
        configured: true,
        supported_categories: ["triathlon"],
      },
    ]);
    vi.mocked(api.competitionGoals!)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ ...goal, source_provider: "fixture" }]);
    api.searchCompetitionCatalog = vi
      .fn()
      .mockResolvedValue([
        {
          provider: "fixture",
          external_id: "e1",
          name: "Evento",
          start_date: "2027-04-19",
          end_date: null,
          category: "triathlon",
          event_format: "sprint",
          city: "Valencia",
          region: null,
          country: "España",
          latitude: null,
          longitude: null,
          source_url: null,
          segments: goal.segments,
          retrieved_at: "2026-08-15T10:00:00Z",
        },
      ]);
    api.importCompetitionGoal = vi.fn().mockResolvedValue(goal);
    render(<CalendarPage client={api} canManage athleteId="a" />);
    await screen.findByText("Todavía no tienes objetivos ni sesiones planificadas.");
    await userEvent.click(
      screen.getByRole("button", { name: "Buscar competición" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Buscar" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Añadir como objetivo" }),
    );
    await waitFor(() =>
      expect(api.importCompetitionGoal).toHaveBeenCalledWith(
        "fixture",
        "e1",
        "B",
      ),
    );
    expect(await screen.findByText(goal.name)).toBeVisible();
  });
});

import { CompetitionCatalogSearch } from "./CompetitionCatalogSearch";
describe("AI Web competition search", () => {
  it("shows AI Web, source confidence and imports a selected result", async () => {
    const api = client();
    api.competitionCatalogProviders = vi
      .fn()
      .mockResolvedValue([
        {
          provider: "ai_web",
          label: "Búsqueda web con IA",
          configured: true,
          supported_categories: [
            "running",
            "cycling",
            "swimming",
            "triathlon",
            "duathlon",
            "aquathlon",
          ],
        },
      ]);
    api.searchCompetitionCatalog = vi
      .fn()
      .mockResolvedValue([
        {
          provider: "ai_web",
          external_id: "stable-id",
          name: "10K Consuegra",
          start_date: "2026-10-18",
          end_date: null,
          category: "running",
          event_format: "10 km",
          city: "Consuegra",
          region: "Castilla-La Mancha",
          country: "España",
          latitude: null,
          longitude: null,
          source_url: "https://organizer.example/event",
          segments: [],
          confidence: "high",
          evidence: [
            {
              url: "https://organizer.example/event",
              title: "Oficial",
              official: true,
            },
          ],
          retrieved_at: "2026-08-15T10:00:00Z",
        },
      ]);
    api.importCompetitionGoal = vi.fn().mockResolvedValue(goal);
    const imported = vi.fn().mockResolvedValue(undefined);
    render(<CompetitionCatalogSearch client={api} onImported={imported} />);
    expect(
      await screen.findByRole("option", { name: "Búsqueda web con IA" }),
    ).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText("Proveedor"), "ai_web");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText(/Confianza alta/)).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Fuente oficial" }),
    ).toHaveAttribute("rel", "noopener noreferrer");
    await userEvent.click(
      screen.getByRole("button", { name: "Añadir como objetivo" }),
    );
    expect(api.importCompetitionGoal).toHaveBeenCalledWith(
      "ai_web",
      "stable-id",
      "B",
    );
    expect(imported).toHaveBeenCalled();
  });
  it("keeps the not-configured state when AI Web is disabled", async () => {
    const api = client();
    api.competitionCatalogProviders = vi
      .fn()
      .mockResolvedValue([
        {
          provider: "ai_web",
          label: "Búsqueda web con IA",
          configured: false,
          supported_categories: ["running"],
        },
      ]);
    render(<CompetitionCatalogSearch client={api} onImported={vi.fn()} />);
    expect(await screen.findByText("Catálogo no configurado")).toBeVisible();
  });
});

describe("Tavily competition search", () => {
  const tavily = {
    provider: "tavily",
    label: "Búsqueda web · Tavily",
    configured: true,
    supported_categories: [
      "running",
      "cycling",
      "swimming",
      "triathlon",
      "duathlon",
      "aquathlon",
    ],
    search_mode: "web",
    supports_search_to_manual_goal: true,
  } as const;
  it("shows candidates and listings with the correct actions", async () => {
    const api = client();
    api.competitionCatalogProviders = vi.fn().mockResolvedValue([tavily]);
    api.searchWebCompetitions = vi.fn().mockResolvedValue({
      phase: "initial",
      has_more: true,
      results: [
        {
          id: "one",
          title: "XII Carrera Popular Villa X",
          url: "https://example.org/race",
          snippet: "Inscripciones abiertas",
          source_domain: "example.org",
          source_label: "Example",
          source_kind: "web",
          result_kind: "event_candidate",
          hints: {
            possible_date: null,
            possible_location: null,
            possible_category: "running",
            possible_distance: "10 km",
          },
        },
        {
          id: "two",
          title: "Calendario de carreras 2026",
          url: "https://example.org/calendar",
          snippet: "Listado",
          source_domain: "example.org",
          source_label: "Example",
          source_kind: "specialized_calendar",
          result_kind: "event_listing",
          hints: {
            possible_date: null,
            possible_location: null,
            possible_category: "running",
            possible_distance: null,
          },
        },
      ],
    });
    const manual = vi.fn();
    render(
      <CompetitionCatalogSearch
        client={api}
        onImported={vi.fn()}
        onManualGoal={manual}
      />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Buscar" }),
    );
    expect(
      await screen.findByText("XII Carrera Popular Villa X"),
    ).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Abrir fuente" })).toHaveLength(
      2,
    );
    expect(
      screen.getAllByRole("button", { name: "Añadir como objetivo" }),
    ).toHaveLength(1);
    await userEvent.click(
      screen.getByRole("button", { name: "Añadir como objetivo" }),
    );
    expect(manual).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "XII Carrera Popular Villa X",
        sourceProvider: "tavily",
        sourceUrl: "https://example.org/race",
      }),
    );
    expect(api.importCompetitionGoal).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Cargar más resultados" }),
    ).toBeVisible();
  });
  it("does not disable other providers when Tavily is not configured", async () => {
    const api = client();
    api.competitionCatalogProviders = vi.fn().mockResolvedValue([
      { ...tavily, configured: false },
      {
        provider: "ai_web",
        label: "Búsqueda web con IA",
        configured: true,
        supported_categories: ["running"],
      },
    ]);
    render(<CompetitionCatalogSearch client={api} onImported={vi.fn()} />);
    expect(
      await screen.findByRole("option", { name: "Búsqueda web con IA" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("option", { name: "Búsqueda web · Tavily" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Catálogo no configurado"),
    ).not.toBeInTheDocument();
  });
  it("shows a safe provider error", async () => {
    const api = client();
    api.competitionCatalogProviders = vi.fn().mockResolvedValue([tavily]);
    api.searchWebCompetitions = vi
      .fn()
      .mockRejectedValue(new Error("secret remote body"));
    render(<CompetitionCatalogSearch client={api} onImported={vi.fn()} />);
    await screen.findByRole("option", { name: "Búsqueda web · Tavily" });
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se ha podido realizar la búsqueda.",
    );
    expect(screen.queryByText(/secret remote body/)).not.toBeInTheDocument();
  });
  it("replaces the first batch with the combined backend ranking on load more", async () => {
    const api = client();
    api.competitionCatalogProviders = vi.fn().mockResolvedValue([tavily]);
    const result = (id: string, title: string) => ({
      id,
      title,
      url: `https://example.org/${id}`,
      snippet: "Carrera popular",
      source_domain: "example.org",
      source_label: "Example",
      source_kind: "web",
      result_kind: "event_candidate" as const,
      hints: {
        possible_date: null,
        possible_location: null,
        possible_category: "running",
        possible_distance: null,
      },
    });
    api.searchWebCompetitions = vi
      .fn()
      .mockResolvedValueOnce({
        phase: "initial",
        has_more: true,
        results: [result("madrid", "10K Madrid")],
      })
      .mockResolvedValueOnce({
        phase: "more",
        has_more: false,
        results: [
          result("tomelloso", "10K Tomelloso"),
          result("madrid", "10K Madrid"),
        ],
      });
    render(<CompetitionCatalogSearch client={api} onImported={vi.fn()} />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Buscar" }),
    );
    await screen.findByText("10K Madrid");
    await userEvent.click(
      screen.getByRole("button", { name: "Cargar más resultados" }),
    );
    await screen.findByText("10K Tomelloso");
    expect(
      screen
        .getAllByRole("heading", { level: 3 })
        .map((node) => node.textContent),
    ).toEqual(["10K Tomelloso", "10K Madrid"]);
  });
});
