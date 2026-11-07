import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { activitySyncCompletedEvent } from "../../components/ActivitySyncButton";
import type { ApiClient } from "../../services/apiClient";
import { ManualStrengthPage } from "./ManualStrengthPage";

const session = {
  id: "s1",
  started_at: "2026-08-02T16:00:00Z",
  timezone_name: "Europe/Madrid",
  duration_minutes: 45,
  body_regions: ["back", "arms"] as const,
  perceived_exertion: 7,
  notes: "Trabajo general",
  created_at: "2026-08-02T16:00:00Z",
  updated_at: "2026-08-02T16:00:00Z",
  training_load: {
    load_value: 52.5,
    method: "strength_rpe" as const,
    unit: "points" as const,
    quality: "medium" as const,
    warnings: [],
    algorithm_version: "0.7e.1",
    calculated_at: "2026-08-02T16:00:00Z",
  },
};

function client(overrides = {}) {
  return {
    listManualStrengthSessions: vi.fn().mockResolvedValue([session]),
    createManualStrengthSession: vi.fn().mockResolvedValue(session),
    updateManualStrengthSession: vi.fn().mockResolvedValue(session),
    deleteManualStrengthSession: vi.fn().mockResolvedValue(undefined),
    recalculateManualStrengthLoad: vi.fn().mockResolvedValue({
      ...session.training_load,
      load_value: 55,
    }),
    ...overrides,
  } as unknown as ApiClient;
}

describe("ManualStrengthPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows loading then sessions", async () => {
    render(<ManualStrengthPage client={client()} />);
    expect(screen.getByRole("status")).toHaveTextContent(/Cargando/);
    expect(await screen.findByText("Trabajo general")).toBeInTheDocument();
    expect(screen.getByText(/Espalda y brazos/)).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    render(
      <ManualStrengthPage
        client={client({ listManualStrengthSessions: vi.fn().mockResolvedValue([]) })}
      />,
    );
    expect(await screen.findByText(/Todavía no has registrado/)).toBeInTheDocument();
  });

  it("refreshes training views after saving without starting a Strava sync", async () => {
    const api = client({ listManualStrengthSessions: vi.fn().mockResolvedValue([]) });
    const listener = vi.fn();
    window.addEventListener(activitySyncCompletedEvent, listener);
    render(<ManualStrengthPage client={api} athleteId="athlete-a" />);
    await userEvent.click(await screen.findByRole("button", { name: "Añadir entrenamiento de fuerza" }));
    await userEvent.click(screen.getByRole("button", { name: "Pecho" }));
    fireEvent.submit(document.querySelector(".strength-modal form")!);
    await waitFor(() => expect(api.createManualStrengthSession).toHaveBeenCalledOnce());
    expect(listener).toHaveBeenCalledOnce();
    expect(listener.mock.calls[0][0].detail.athleteId).toBe("athlete-a");
    window.removeEventListener(activitySyncCompletedEvent, listener);
  });

  it("recalculates without removing the card", async () => {
    const api = client();
    render(<ManualStrengthPage client={api} />);
    await userEvent.click(await screen.findByRole("button", { name: "Recalcular" }));
    await waitFor(() => expect(screen.getByText("55,00 puntos")).toBeInTheDocument());
    expect(screen.getByText("Trabajo general")).toBeInTheDocument();
  });

  it("confirms and deletes", async () => {
    const api = client();
    render(<ManualStrengthPage client={api} />);
    await userEvent.click(await screen.findByRole("button", { name: "Eliminar" }));
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Eliminar" }).at(-1)!);
    await waitFor(() => expect(screen.queryByText("Trabajo general")).not.toBeInTheDocument());
  });
});
