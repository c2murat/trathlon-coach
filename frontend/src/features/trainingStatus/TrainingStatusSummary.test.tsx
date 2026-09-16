import {act, cleanup, render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, describe, expect, it, vi} from "vitest";
import type {ApiClient} from "../../services/apiClient";
import {FetchApiClient} from "../../services/apiClient";
import {TrainingStatusPage} from "./TrainingStatusPage";
import {TrainingStatusSummary} from "./TrainingStatusSummary";
import {interpretationCopy} from "./interpretationPresentation";
import type {TrainingStatusOverview, TrainingStatusInterpretation} from "./interpretationTypes";

afterEach(() => {cleanup(); vi.restoreAllMocks();});

export function interpretation(athlete = "a"): TrainingStatusInterpretation {
  return {athlete_id: athlete, as_of_date: "2026-09-16", interpretation_version: "0.8G.2D.1",
    short_term: {days:7,start_date:"2026-09-09",fitness_delta:"3",fatigue_delta:"12",fitness_trend:"RISING",fatigue_trend:"RISING_FAST"},
    broader_context: {days:21,start_date:"2026-08-26",fitness_delta:"8",fatigue_delta:"20",fitness_trend:"RISING",fatigue_trend:"RISING_FAST"},
    recent: {days:3,start_date:"2026-09-13",fitness:{delta:"1.2",direction:"RISING",changed_direction:false},fatigue:{delta:"5",direction:"RISING",changed_direction:false},form_delta:"-3.8",recovery_turn:false},
    data_date: "2026-09-16", window_start_date: "2026-09-09", trend_days: 7,
    fitness: "46.31", fatigue: "71.42", form: "-25.11", fitness_delta: "3", fatigue_delta: "12",
    fitness_trend: "RISING", fatigue_trend: "RISING_FAST", form_state: "HIGHLY_LOADED", overall_state: "HIGH_LOAD",
    headline_key: "HIGH_LOAD", summary_key: "HIGH_LOAD", fitness_explanation_key: "RISING",
    fatigue_explanation_key: "RISING_FAST", form_explanation_key: "HIGHLY_LOADED",
    notable_trend_key: "FATIGUE_RISING_FASTER_THAN_FITNESS", reason_codes: ["FITNESS_RISING", "FATIGUE_RISING_FAST"]};
}
function overview(athlete = "a"): TrainingStatusOverview {
  const value = {date: "2026-09-16", timezone_name: "UTC", total_load: 75, fitness: 46.31, fatigue: 71.42,
    form: -25.11, history_day_number: 100, is_warmup: false, training_load_algorithm_version: "0.7b.1",
    manual_strength_algorithm_version: "0.7e.1", training_status_algorithm_version: "0.7f.1", calculated_at: "2026-09-16T12:00:00Z"};
  return {series: [value], latest: value, interpretation: interpretation(athlete)};
}
function api(data = overview()) {
  return {trainingStatusOverview: vi.fn().mockResolvedValue(data), recalculateTrainingStatus: vi.fn()} as unknown as ApiClient;
}

describe("Training status descriptive summary", () => {
  it("renders headline, short summary, three explanations and notable trend without enums", () => {
    render(<TrainingStatusSummary interpretation={interpretation()}/>);
    const region = screen.getByRole("region", {name: "Resumen de tu estado actual"});
    expect(within(region).getByRole("heading", {name: "La carga acumulada pesa en tu frescura"})).toBeInTheDocument();
    expect(within(region).getByText(interpretationCopy(interpretation()).summary)).toBeInTheDocument();
    for (const name of ["Fitness", "Fatiga", "Forma"]) expect(within(region).getByRole("heading", {name})).toBeInTheDocument();
    expect(within(region).getByText("Tu fitness estimado ha crecido respecto a hace siete días.")).toBeInTheDocument();
    expect(within(region).getByText("La fatiga ha aumentado con rapidez en los últimos siete días.")).toBeInTheDocument();
    expect(within(region).getByText(/En los últimos siete días, la fatiga ha aumentado más/)).toBeInTheDocument();
    expect(region.textContent).not.toMatch(/FATIGUE_|HIGH_LOAD|FITNESS_/);
    expect(region.textContent).not.toMatch(/descansa mañana|haz intervalos|sobreentrenado|listo para competir/);
    expect(within(region).getByText(/Estos indicadores son una estimación matemática/)).toBeInTheDocument();
  });
  it("provides accessible keyboard help", async () => {
    render(<TrainingStatusSummary interpretation={interpretation()}/>);
    const help = screen.getByText("Qué significa cada indicador");
    await userEvent.tab();
    expect(help).toHaveFocus();
    expect(help.tagName).toBe("SUMMARY");
    expect(help.closest("details")).not.toBeNull();
  });
  it("shows legitimate insufficient and stale state without claiming a trend", () => {
    const value: TrainingStatusInterpretation = {...interpretation(), overall_state: "INSUFFICIENT_DATA",
      headline_key: "INSUFFICIENT_DATA", summary_key: "INSUFFICIENT_DATA", reason_codes: ["STALE_STATUS"]};
    render(<TrainingStatusSummary interpretation={value}/>);
    expect(screen.getByRole("heading", {name: "Todavía no hay suficientes datos para interpretar tu estado de forma."})).toBeInTheDocument();
    expect(screen.getByText(/A medida que acumules entrenamientos/)).toBeInTheDocument();
    expect(screen.getByText(/Los últimos valores guardados necesitan actualizarse/)).toBeInTheDocument();
    expect(screen.queryByText("Observación reciente:")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("orders current values, chart and interpretation consecutively", async () => {
    const client = api();
    render(<TrainingStatusPage client={client} athleteId="a"/>);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando");
    const summary = await screen.findByRole("region", {name: "Resumen de tu estado actual"});
    const chart = screen.getByRole("img", {name: "Gráfico diario del fitness, la fatiga y la forma"});
    const values = screen.getByRole("region", {name: "Estado más reciente"});
    expect(values.nextElementSibling).toBe(chart.closest("section"));
    expect(chart.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(chart.closest("section")?.nextElementSibling).toBe(summary);
    expect(client.trainingStatusOverview).toHaveBeenCalledOnce();
    expect(client.recalculateTrainingStatus).not.toHaveBeenCalled();
  });
  it("does not turn a query failure into insufficient data", async () => {
    const client = {trainingStatusOverview: vi.fn().mockRejectedValue(new Error("403"))} as unknown as ApiClient;
    render(<TrainingStatusPage client={client} athleteId="a"/>);
    expect(await screen.findByRole("alert")).toHaveTextContent("No se ha podido consultar");
    expect(screen.queryByText(/Todavía no hay suficientes datos/)).not.toBeInTheDocument();
  });
  it("clears a previous athlete and ignores late responses", async () => {
    let complete!: (data: TrainingStatusOverview) => void;
    const client = {trainingStatusOverview: vi.fn().mockResolvedValueOnce(overview("a"))
      .mockImplementationOnce(() => new Promise(resolve => {complete = resolve;}))
      .mockResolvedValueOnce(overview("c"))} as unknown as ApiClient;
    const view = render(<TrainingStatusPage client={client} athleteId="a"/>);
    await screen.findByRole("region", {name: "Resumen de tu estado actual"});
    view.rerender(<TrainingStatusPage client={client} athleteId="b"/>);
    expect(screen.queryByRole("region", {name: "Resumen de tu estado actual"})).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Cargando");
    view.rerender(<TrainingStatusPage client={client} athleteId="c"/>);
    await screen.findByRole("region", {name: "Resumen de tu estado actual"});
    await act(async () => {complete({...overview("b"), interpretation: {...interpretation("b"), headline_key: "FRESH"}});});
    expect(screen.queryByRole("heading", {name: "El modelo muestra mayor frescura"})).not.toBeInTheDocument();
  });
  it("rejects response for a different athlete", async () => {
    render(<TrainingStatusPage client={api(overview("other"))} athleteId="a"/>);
    await screen.findByRole("alert");
    expect(screen.queryByRole("region", {name: "Resumen de tu estado actual"})).not.toBeInTheDocument();
  });
  it("renders empty interpretation without automatically calculating status", async () => {
    const data = overview(); data.latest = null; data.series = [];
    data.interpretation = {...data.interpretation, overall_state: "INSUFFICIENT_DATA", headline_key: "INSUFFICIENT_DATA", summary_key: "INSUFFICIENT_DATA", data_date: null};
    const client = api(data);
    render(<TrainingStatusPage client={client} athleteId="a"/>);
    await screen.findByText(/A medida que acumules entrenamientos/);
    expect(client.recalculateTrainingStatus).not.toHaveBeenCalled();
  });
  it("central client uses scoped GET and explicit dates", async () => {
    const fetch = vi.spyOn(globalThis,"fetch").mockResolvedValue(new Response(JSON.stringify(overview()), {status: 200}));
    const client = new FetchApiClient("http://api"); client.setActiveAthlete("a");
    await client.trainingStatusOverview({startDate:"2026-08-20",endDate:"2026-09-16",timezoneName:"UTC"});
    const [url, init] = fetch.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/training-status/overview");
    expect(new URL(String(url)).searchParams.get("end_date")).toBe("2026-09-16");
    expect(new Headers(init?.headers).get("X-TriCoach-Athlete-Id")).toBe("a");
    expect(init?.method ?? "GET").toBe("GET");
  });
  it("explains elevated three-week fatigue with a recent decline without enum leakage", () => {
    const value = interpretation();
    value.form_state = value.form_explanation_key = "LOADED";
    value.recent = {...value.recent, fatigue:{delta:"-10",direction:"FALLING",changed_direction:true},
      fitness:{delta:"0",direction:"STABLE",changed_direction:false},form_delta:"10",recovery_turn:true};
    render(<TrainingStatusSummary interpretation={value}/>);
    const copy = interpretationCopy(value);
    expect(copy.summary).toContain("tres semanas, aunque en los últimos tres días ha descendido");
    expect(copy.summary).toContain("por encima de hace tres semanas, y en los últimos tres días se mantiene estable");
    expect(copy.summary).toContain("recuperación de frescura");
    expect(copy.summary.split(".").filter(Boolean)).toHaveLength(3);
    expect(copy.summary.split(/\s+/).length).toBeLessThan(100);
    expect(screen.getByText(copy.fatigue)).toHaveTextContent("siete días, aunque ha descendido");
    expect(screen.getByRole("region").textContent).not.toMatch(/RECENT_RECOVERY_TURN|RISING_FAST|FATIGUE_|FITNESS_/);
  });
  it("does not describe recovering freshness without a supported recovery turn", () => {
    const value = interpretation(); value.form_state = value.form_explanation_key = "LOADED";
    expect(interpretationCopy(value).form).not.toContain("recuperación");
  });
  it("reports missing broader context without discarding valid weekly interpretation", () => {
    const value = interpretation();
    value.broader_context = {...value.broader_context,fitness_delta:null,fatigue_delta:null,
      fitness_trend:"INSUFFICIENT_DATA",fatigue_trend:"INSUFFICIENT_DATA"};
    render(<TrainingStatusSummary interpretation={value}/>);
    expect(screen.getByText(/Aún no hay una secuencia completa de 21 días/)).toBeInTheDocument();
    expect(interpretationCopy(value).summary).toContain("siete días");
    expect(interpretationCopy(value).summary).not.toContain("tres semanas");
  });
});
