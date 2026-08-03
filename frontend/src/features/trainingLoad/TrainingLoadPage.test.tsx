import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TrainingLoadPage } from "./TrainingLoadPage";
import { CALCULATION_RELIABILITY_HELP } from "./components/CalculationReliabilityHelp";

const common = { timezone_name: "Europe/Madrid", source_load_algorithm_version: "0.7b.1", aggregation_algorithm_version: "0.7c.1", total_load: 42, activity_count: 1, loaded_activity_count: 1, null_load_activity_count: 0, total_duration_seconds: 1800, coverage: "complete", quality: "medium", warnings: [], activity_ids: ["a"], calculated_at: "2026-07-20T12:00:00Z" };
const client: any = {
  getDailyTrainingLoad: async () => [{ ...common, id: "d", local_date: "2026-07-20" }],
  getWeeklyTrainingLoad: async () => [{ ...common, id: "w", iso_year: 2026, iso_week: 30, week_start_date: "2026-07-20", week_end_date: "2026-07-26" }],
};

function summaryValue(label: string) {
  const card = screen.getByText(label).closest(".training-summary-card");
  expect(card).not.toBeNull();
  return within(card as HTMLElement).getByText(/^\d+(?:[,.]\d+)?$/);
}

describe("TrainingLoadPage reliability terminology", () => {
  it("uses explicit table headers and accessible contextual help", async () => {
    const user = userEvent.setup();
    render(<TrainingLoadPage client={client} />);
    expect(await screen.findByText("Estadísticas")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evolución diaria" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evolución semanal" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Últimas 4 semanas" })).toBeInTheDocument();
    expect(screen.getAllByText("Duración", { selector: "th" })).toHaveLength(2);
    const headers = await screen.findAllByRole("columnheader", { name: /Fiabilidad del cálculo/ });
    expect(headers).toHaveLength(2);
    expect(screen.getAllByRole("columnheader", { name: "Cobertura de datos" })).toHaveLength(2);
    expect(screen.queryByRole("columnheader", { name: "Calidad" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Fiabilidad media")).toHaveLength(2);
    const helpButtons = screen.getAllByRole("button", { name: "Ayuda sobre la fiabilidad del cálculo" });
    expect(helpButtons[0]).toHaveAttribute("aria-describedby");
    expect(screen.getAllByRole("tooltip")[0]).toHaveTextContent(CALCULATION_RELIABILITY_HELP);
    expect(helpButtons[0].tabIndex).toBe(0);
  });

  it("shows the load split and supports legacy aggregate responses", async () => {
    render(<TrainingLoadPage client={client} />);
    expect(await screen.findByText("Estadísticas")).toBeInTheDocument();
    expect(summaryValue("Carga total")).toHaveTextContent("42");
    expect(summaryValue("Resistencia")).toHaveTextContent("42");
    expect(summaryValue("Fuerza")).toHaveTextContent("0");
    expect(summaryValue("Sesiones de fuerza")).toHaveTextContent("0");
  });

  it("reloads the requested range when selecting 4, 8 and 12 weeks", async () => {
    const getDailyTrainingLoad = vi.fn(client.getDailyTrainingLoad);
    const getWeeklyTrainingLoad = vi.fn(client.getWeeklyTrainingLoad);
    const rangeClient = { ...client, getDailyTrainingLoad, getWeeklyTrainingLoad };
    const user = userEvent.setup();
    render(<TrainingLoadPage client={rangeClient} />);
    const selector = await screen.findByLabelText("Periodo");
    expect(selector).toHaveValue("4");
    await user.selectOptions(selector, "8");
    await waitFor(() => expect(getDailyTrainingLoad).toHaveBeenCalledTimes(2));
    expect(selector).toHaveValue("8");
    await user.selectOptions(selector, "12");
    await waitFor(() => expect(getDailyTrainingLoad).toHaveBeenCalledTimes(3));
    expect(selector).toHaveValue("12");
    expect(getWeeklyTrainingLoad).toHaveBeenCalledTimes(3);
  });
});


