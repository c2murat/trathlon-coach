import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../services/apiClient";
import type { TrainingPlanSession } from "../../types/planning";
import { CalendarPage } from "./CalendarPage";
import { monthGridRange } from "./MonthlyCalendar";

const session: TrainingPlanSession = {
  id: "old",
  scheduled_date: "2026-08-27",
  sport: "running",
  title: "RUN_EASY",
  description: null,
  planned_duration_seconds: 2700,
  workout: null,
};
const api = (): ApiClient =>
  ({
    competitionGoals: vi.fn().mockResolvedValue([]),
    plannedTrainingSessions: vi.fn().mockResolvedValue([]),
    competitionCatalogProviders: vi.fn().mockResolvedValue([]),
  }) as unknown as ApiClient;

describe("CalendarPage monthly view", () => {
  beforeEach(() => window.history.replaceState({}, "", "/calendar"));
  afterEach(() => vi.restoreAllMocks());

  it("opens Mes by default and requests the visible monthly grid", async () => {
    const client = api(),
      now = new Date(),
      range = monthGridRange(now.getFullYear(), now.getMonth());
    render(<CalendarPage client={client} canManage athleteId="athlete-a" />);
    expect(screen.getByRole("button", { name: "Lista" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Mes" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Año" })).toBeVisible();
    expect(await screen.findByRole("grid")).toBeVisible();
    expect(screen.getByRole("button", { name: "Mes" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await waitFor(() =>
      expect(client.plannedTrainingSessions).toHaveBeenLastCalledWith(
        range.start,
        range.end,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Mes siguiente" }));
    const next = new Date(now.getFullYear(), now.getMonth() + 1, 1),
      nextRange = monthGridRange(next.getFullYear(), next.getMonth());
    await waitFor(() =>
      expect(client.plannedTrainingSessions).toHaveBeenLastCalledWith(
        nextRange.start,
        nextRange.end,
      ),
    );
  });

  it("respects explicit list and year URL views", async () => {
    window.history.replaceState({}, "", "/calendar?view=list");
    const list = api();
    list.plannedTrainingSessions = vi.fn().mockResolvedValue([session]);
    const view = render(
      <CalendarPage client={list} canManage athleteId="athlete-a" />,
    );
    expect(await screen.findByText("RUN_EASY")).toBeVisible();
    expect(screen.getByRole("button", { name: "Lista" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await waitFor(() =>
      expect(list.plannedTrainingSessions).toHaveBeenLastCalledWith(
        `${new Date().getFullYear()}-01-01`,
        `${new Date().getFullYear()}-12-31`,
      ),
    );

    view.unmount();
    window.history.replaceState({}, "", "/calendar?view=year");
    const year = api();
    render(<CalendarPage client={year} canManage athleteId="athlete-a" />);
    expect(
      await screen.findByRole("heading", {
        name: `Año ${new Date().getFullYear()}`,
      }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Año" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("keeps a manual view choice across ordinary rerenders", async () => {
    const client = api();
    const view = render(
      <CalendarPage client={client} canManage athleteId="athlete-a" />,
    );
    expect(await screen.findByRole("grid")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Lista" }));
    expect(screen.getByRole("button", { name: "Lista" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    view.rerender(
      <CalendarPage client={client} canManage={false} athleteId="athlete-a" />,
    );
    expect(screen.getByRole("button", { name: "Lista" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("clears old sessions immediately and ignores a stale athlete response", async () => {
    window.history.replaceState({}, "", "/calendar?view=list");
    let release!: (value: TrainingPlanSession[]) => void;
    const client = api();
    vi.mocked(client.plannedTrainingSessions!)
      .mockResolvedValueOnce([session])
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            release = resolve;
          }),
      )
      .mockResolvedValueOnce([]);
    const view = render(
      <CalendarPage client={client} canManage athleteId="athlete-a" />,
    );
    expect(await screen.findByText("RUN_EASY")).toBeVisible();
    view.rerender(
      <CalendarPage client={client} canManage athleteId="athlete-b" />,
    );
    expect(screen.queryByText("RUN_EASY")).not.toBeInTheDocument();
    view.rerender(
      <CalendarPage client={client} canManage athleteId="athlete-c" />,
    );
    await waitFor(() =>
      expect(client.plannedTrainingSessions).toHaveBeenCalledTimes(3),
    );
    release([session]);
    await Promise.resolve();
    expect(screen.queryByText("RUN_EASY")).not.toBeInTheDocument();
  });
});
