import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ActivityTrainingLoadSection } from "./ActivityTrainingLoadSection";
import { CALCULATION_RELIABILITY_HELP } from "../trainingLoad/components/CalculationReliabilityHelp";

const base = { activity_id: "a", load_value: 72.45, method: "cycling_power", unit: "load_points", coverage: "complete", quality: "high", reason: "calculated", algorithm_version: "0.7b.1", duration_seconds: 3600, effective_intensity: null, reference_value: 250, reference_metric: "W", source_metrics: {}, warnings: [], calculated_at: "2026-01-01T00:00:00Z" };
function client(get: () => Promise<any>, post = async () => base): any { return { trainingLoad: get, recalculateTrainingLoad: post }; }

describe("ActivityTrainingLoadSection", () => {
  it("shows unambiguous calculation terminology and keyboard-accessible help", async () => {
    const user = userEvent.setup();
    render(<ActivityTrainingLoadSection activityId="a" client={client(() => Promise.resolve(base))} />);
    expect(screen.getByText(/Cargando carga/)).toBeInTheDocument();
    expect(await screen.findByText("72,45 puntos")).toBeInTheDocument();
    expect(screen.getByText("Método de cálculo")).toBeInTheDocument();
    expect(screen.getByText("Cobertura de datos")).toBeInTheDocument();
    expect(screen.getByText("Fiabilidad del cálculo")).toBeInTheDocument();
    expect(screen.getByText("Fiabilidad alta")).toBeInTheDocument();
    expect(screen.getByText("Valor de referencia")).toBeInTheDocument();
    expect(screen.getByText("Estado del cálculo")).toBeInTheDocument();
    expect(screen.queryByText("Calidad")).not.toBeInTheDocument();
    const help = screen.getByRole("button", { name: "Ayuda sobre la fiabilidad del cálculo" });
    expect(help).toHaveAttribute("aria-describedby");
    expect(screen.getByRole("tooltip")).toHaveTextContent(CALCULATION_RELIABILITY_HELP);
    await user.tab();
    expect(help).toHaveFocus();
  });

  it("shows empty on 404 and calculates", async () => {
    let calls = 0;
    render(<ActivityTrainingLoadSection activityId="a" client={client(() => Promise.reject(new Error("404")), async () => { calls++; return base; })} />);
    expect(await screen.findByText(/Aún no se ha calculado/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Calcular carga" }));
    await waitFor(() => expect(calls).toBe(1));
    expect(await screen.findByText("72,45 puntos")).toBeInTheDocument();
  });

  it("does not render null load as zero", async () => {
    render(<ActivityTrainingLoadSection activityId="a" client={client(async () => ({ ...base, load_value: null, reason: "missing_duration", quality: "none" }))} />);
    expect(await screen.findByText(/no hay datos suficientes/)).toBeInTheDocument();
    expect(screen.getByText("No evaluable")).toBeInTheDocument();
    expect(screen.queryByText(/0 puntos/)).not.toBeInTheDocument();
  });
});
