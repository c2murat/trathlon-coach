import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DailyTrainingLoadAggregate, WeeklyTrainingLoadAggregate } from "../../../types/trainingLoad";
import { DailyLoadChart } from "./DailyLoadChart";
import { QualityBadge } from "./QualityBadge";
import { SummaryCard } from "./SummaryCard";
import { WeeklyLoadChart } from "./WeeklyLoadChart";

const common = { timezone_name: "Europe/Madrid", source_load_algorithm_version: "0.7b.1", aggregation_algorithm_version: "0.7c.1", activity_count: 1, loaded_activity_count: 1, null_load_activity_count: 0, total_duration_seconds: 1800, coverage: "complete" as const, quality: "high" as const, warnings: [], activity_ids: ["activity"], calculated_at: "2026-07-20T12:00:00Z" };
const daily = [{ ...common, id: "daily", local_date: "2026-07-20", total_load: 42.5 }] satisfies DailyTrainingLoadAggregate[];
const weekly = [{ ...common, id: "weekly", iso_year: 2026, iso_week: 30, week_start_date: "2026-07-20", week_end_date: "2026-07-26", total_load: 120 }] satisfies WeeklyTrainingLoadAggregate[];

describe("training load visual components", () => {
  it("exposes daily points as keyboard-focusable accessible tooltips", () => {
    render(<DailyLoadChart rows={daily} />);
    const point = screen.getByRole("img", { name: /20 de julio de 2026: 42,5 puntos/ });
    expect(point).toHaveAttribute("tabindex", "0");
    expect(point.querySelector("title")).toHaveTextContent("42,5 puntos");
    expect(point.querySelector(".training-chart__tooltip")).toBeInTheDocument();
  });

  it("exposes weekly bars as keyboard-focusable accessible tooltips", () => {
    render(<WeeklyLoadChart rows={weekly} />);
    const bar = screen.getByRole("img", { name: /Semana 30 . 2026: 120 puntos/ });
    expect(bar).toHaveAttribute("tabindex", "0");
    expect(bar.querySelector("title")).toHaveTextContent("120 puntos");
    expect(bar.querySelector(".training-chart__tooltip")).toBeInTheDocument();
  });


  it("renders consistent hidden SVG summary icons without emoji text", () => {
    const { container } = render(<>
      <SummaryCard icon="load" label="Carga total" value="100" detail="Acumulada" />
      <SummaryCard icon="activity" label="Actividades" value="4" detail="Calculadas" />
      <SummaryCard icon="duration" label="Tiempo total" value="2 h" detail="Duración" />
      <SummaryCard icon="average" label="Promedio semanal" value="25" detail="Media" />
    </>);
    const icons = container.querySelectorAll(".training-summary-card__icon svg");
    expect(icons).toHaveLength(4);
    icons.forEach((icon) => expect(icon).toHaveAttribute("aria-hidden", "true"));
    const forbiddenSymbols = [0xc3, 0xc2, 0xe2, 0x26a1, 0x1f3c3, 0x23f1, 0x25a5].map((codePoint) => String.fromCodePoint(codePoint));
    forbiddenSymbols.forEach((symbol) => expect(container.textContent).not.toContain(symbol));
  });
  it.each(["none", "low", "medium", "high"] as const)("renders the %s quality badge", (quality) => {
    render(<QualityBadge quality={quality} />);
    expect(screen.getByText(/No evaluable|Fiabilidad baja|Fiabilidad media|Fiabilidad alta/)).toHaveClass(`training-load-quality-badge--${quality}`);
  });
});




