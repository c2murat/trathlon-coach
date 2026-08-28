import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../services/apiClient";
import type { TrainingPlanSession } from "../../types/planning";
import { CalendarPage } from "./CalendarPage";
import { monthGridRange } from "./MonthlyCalendar";

const session: TrainingPlanSession = { id: "old", scheduled_date: "2026-08-27", sport: "running", title: "RUN_EASY", description: null, planned_duration_seconds: 2700, workout: null };
const api = (): ApiClient => ({ competitionGoals: vi.fn().mockResolvedValue([]), plannedTrainingSessions: vi.fn().mockResolvedValue([]), competitionCatalogProviders: vi.fn().mockResolvedValue([]) }) as unknown as ApiClient;

describe("CalendarPage monthly view", () => {
  it("offers Lista, Mes and Año and requests the visible monthly grid", async () => {
    const client = api(), now = new Date(), range = monthGridRange(now.getFullYear(), now.getMonth());
    render(<CalendarPage client={client} canManage athleteId="athlete-a" />);
    expect(screen.getByRole("button", { name: "Lista" })).toBeVisible(); expect(screen.getByRole("button", { name: "Mes" })).toBeVisible(); expect(screen.getByRole("button", { name: "Año" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Mes" }));
    expect(await screen.findByRole("grid")).toBeVisible();
    await waitFor(() => expect(client.plannedTrainingSessions).toHaveBeenLastCalledWith(range.start, range.end));
    await userEvent.click(screen.getByRole("button", { name: "Mes siguiente" }));
    const next = new Date(now.getFullYear(), now.getMonth() + 1, 1), nextRange = monthGridRange(next.getFullYear(), next.getMonth());
    await waitFor(() => expect(client.plannedTrainingSessions).toHaveBeenLastCalledWith(nextRange.start, nextRange.end));
  });

  it("clears old sessions immediately and ignores a stale athlete response", async () => {
    let release!: (value: TrainingPlanSession[]) => void; const client = api();
    vi.mocked(client.plannedTrainingSessions!).mockResolvedValueOnce([session]).mockImplementationOnce(() => new Promise((resolve) => { release = resolve; })).mockResolvedValueOnce([]);
    const view = render(<CalendarPage client={client} canManage athleteId="athlete-a" />); expect(await screen.findByText("RUN_EASY")).toBeVisible();
    view.rerender(<CalendarPage client={client} canManage athleteId="athlete-b" />); expect(screen.queryByText("RUN_EASY")).not.toBeInTheDocument();
    view.rerender(<CalendarPage client={client} canManage athleteId="athlete-c" />); await waitFor(() => expect(client.plannedTrainingSessions).toHaveBeenCalledTimes(3)); release([session]);
    await Promise.resolve(); expect(screen.queryByText("RUN_EASY")).not.toBeInTheDocument();
  });
});
