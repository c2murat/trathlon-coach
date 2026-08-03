import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { ThemeProvider } from "./ThemeProvider";

vi.mock("../features/manualStrength/ManualStrengthPage", () => ({
  ManualStrengthPage: () => <h1>Fuerza manual de prueba</h1>,
}));

function renderShell(path: string) {
  window.history.replaceState({}, "", path);

  return render(
    <ThemeProvider>
      <AppShell />
    </ThemeProvider>,
  );
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
  it("shows the strength access, renders its route and marks it active", () => {
    renderShell("/activities/strength");
    const strengthLink = screen.getByRole("link", { name: "Fuerza" });
    expect(strengthLink).toHaveAttribute("href", "/activities/strength");
    expect(strengthLink).toHaveClass("nav-link--active");
    expect(screen.getByRole("heading", { name: "Fuerza manual de prueba" })).toBeInTheDocument();
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
      screen.getByRole("heading", { name: "Calendario" }),
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

  it("shows a time-aware Spanish greeting", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-14T09:00:00"));

    renderShell("/settings");

    const greeting = document.querySelector(".topbar__greeting strong");

    expect(greeting).toBeInTheDocument();
    expect(greeting?.textContent).toContain("Carlos");
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
});
