import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { TrainingLoadPage } from "./TrainingLoadPage";
import { CALCULATION_RELIABILITY_HELP } from "./components/CalculationReliabilityHelp";

const common = { timezone_name: "Europe/Madrid", source_load_algorithm_version: "0.7b.1", aggregation_algorithm_version: "0.7c.1", total_load: 42, activity_count: 1, loaded_activity_count: 1, null_load_activity_count: 0, total_duration_seconds: 1800, coverage: "complete", quality: "medium", warnings: [], activity_ids: ["a"], calculated_at: "2026-07-20T12:00:00Z" };
const client: any = {
  getDailyTrainingLoad: async () => [{ ...common, id: "d", local_date: "2026-07-20" }],
  getWeeklyTrainingLoad: async () => [{ ...common, id: "w", iso_year: 2026, iso_week: 30, week_start_date: "2026-07-20", week_end_date: "2026-07-26" }],
};

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
});


