import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../services/apiClient";
import type {
  ActivityPage,
  ImportStatus,
  StravaStatus,
} from "../../types/api";
import { DashboardPage } from "./DashboardPage";

const connected: StravaStatus = {
  provider: "strava",
  connection_status: "connected",
  connected: true,
  external_athlete_id: "123",
  granted_scopes: ["read", "activity:read_all"],
  connected_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  token_expires_at: "2026-07-02T10:00:00Z",
  requires_reconnect: false,
  last_sync_at: "2026-07-14T10:00:00Z",
  message: "Strava is connected.",
};

const noImport: ImportStatus = {
  job_id: null,
  provider: "strava",
  status: "not_started",
  imported_count: 0,
  updated_count: 0,
  skipped_count: 0,
  failed_count: 0,
  page: 0,
  last_external_activity_id: null,
  started_at: null,
  updated_at: "2026-07-14T10:00:00Z",
  completed_at: null,
  next_resume_at: null,
  error_category: null,
};

const activityPage: ActivityPage = {
  total: 1381,
  limit: 10,
  offset: 0,
  items: [
    {
      id: "activity-1",
      external_activity_id: "987",
      name: "Morning Run",
      sport_type: "running",
      start_time: "2026-07-14T06:00:00Z",
      athlete_timezone: "Europe/Madrid",
      distance_metres: 8200,
      moving_time_seconds: 2538,
      elapsed_time_seconds: 2600,
      elevation_metres: 74,
      average_heart_rate: 145,
      average_watts: null,
      trainer: false,
      manual: false,
      visibility: "everyone",
    },
  ],
};

function fakeClient(
  overrides: Partial<ApiClient> = {},
  activities: ActivityPage = activityPage,
): ApiClient {
  return {
    health: vi.fn().mockResolvedValue({ status: "ok", service: "triathlon-coach" }),
    stravaStatus: vi.fn().mockResolvedValue(connected),
    activities: vi.fn().mockResolvedValue(activities),
    latestImport: vi.fn().mockResolvedValue(noImport),
    startImport: vi.fn().mockResolvedValue({
      job_id: "job-1",
      status: "queued",
    }),
    importStatus: vi.fn().mockResolvedValue({
      ...noImport,
      job_id: "job-1",
      status: "succeeded",
      imported_count: 1,
    }),
    browseActivities: vi.fn().mockResolvedValue(activities),
    activityDetail: vi.fn().mockRejectedValue(new Error("not used")),
    activityFilterOptions: vi.fn().mockResolvedValue({ sport_types: [], visibility_values: [], minimum_activity_date: null, maximum_activity_date: null }),
    dashboardSummary: vi.fn().mockResolvedValue({ period: "week", period_start: "2026-07-13T00:00:00Z", period_end: "2026-07-20T00:00:00Z", activity_count: 2, total_moving_time_seconds: 3600, total_distance_metres: 10000, total_elevation_metres: 120, active_days: 2, longest_activity_seconds: 2400, longest_activity_distance_metres: 8000, sport_breakdown: [{ sport_type: "running", activity_count: 2, moving_time_seconds: 3600, distance_metres: 10000, elevation_metres: 120 }] }),
    dashboardTrends: vi.fn().mockResolvedValue([]),
    dashboardConsistency: vi.fn().mockResolvedValue({ weeks: 12, active_weeks: 8, current_training_streak_weeks: 3, longest_training_streak_weeks: 5, average_active_days_per_week: 2.5, average_moving_time_seconds_per_week: 2400, last_activity_at: "2026-07-14T06:00:00Z" }),
    connectUrl: vi.fn().mockReturnValue(
      "http://127.0.0.1:8000/integrations/strava/connect",
    ),
    ...overrides,
  };
}

describe("DashboardPage", () => {
  it("shows a loading state while requests are pending", () => {
    const pending = new Promise<never>(() => undefined);
    render(<DashboardPage client={fakeClient({ health: () => pending })} />);
    expect(screen.getByText(/cargando tu espacio de entrenamiento/i)).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    render(
      <DashboardPage
        client={fakeClient({}, { ...activityPage, total: 0, items: [] })}
      />,
    );
    expect(await screen.findByText("Todavía no hay actividades")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("shows connected Strava status and synchronize action", async () => {
    render(<DashboardPage client={fakeClient()} />);
    expect(await screen.findByText("Conectado")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sincronizar actividades" }),
    ).toBeInTheDocument();
  });

  it("shows disconnected status with a direct OAuth link", async () => {
    const client = fakeClient({
      stravaStatus: vi.fn().mockResolvedValue({
        ...connected,
        connected: false,
        connection_status: "not_connected",
        message: "Strava is not connected.",
      }),
    });
    render(<DashboardPage client={client} />);
    const link = await screen.findByRole("link", { name: "Conectar Strava" });
    expect(link).toHaveAttribute(
      "href",
      "http://127.0.0.1:8000/integrations/strava/connect",
    );
  });

  it("renders activity summary metrics", async () => {
    render(<DashboardPage client={fakeClient()} />);
    expect(await screen.findByText("Morning Run")).toBeInTheDocument();
    expect(screen.getAllByText("Carrera").length).toBeGreaterThan(0);
    expect(screen.getByText("8,2 km")).toBeInTheDocument();
    expect(screen.getByText("42:18")).toBeInTheDocument();
    expect(screen.getByText("74 m")).toBeInTheDocument();
    expect(screen.getByText("1381")).toBeInTheDocument();
  });

  it("starts synchronization, polls, and refreshes activities", async () => {
    const client = fakeClient();
    const user = userEvent.setup();
    render(<DashboardPage client={client} pollDelayMs={0} />);
    const button = await screen.findByRole("button", {
      name: "Sincronizar actividades",
    });
    await user.click(button);
    await waitFor(() => expect(client.startImport).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(client.importStatus).toHaveBeenCalledWith("job-1"),
    );
    await waitFor(() => expect(client.activities).toHaveBeenCalledTimes(2));
  });
});




