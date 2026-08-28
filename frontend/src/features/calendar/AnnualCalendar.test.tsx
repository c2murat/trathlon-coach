import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CalendarItem } from "./calendarItems";
import { AnnualCalendar, daysInMonth, mondayOffset } from "./AnnualCalendar";

const item = (id: string, title: string, variant: CalendarItem["variant"], kind: CalendarItem["kind"] = "training"): CalendarItem => ({ id, date: "2028-02-29", kind, sport: variant, title, subtitle: "45 min", status: "planned", durationSeconds: 2700, sourceId: id, variant });

describe("AnnualCalendar", () => {
  it("calculates leap years and Monday alignment", () => { expect(daysInMonth(2028, 1)).toBe(29); expect(daysInMonth(2027, 1)).toBe(28); expect(mondayOffset(2026, 7)).toBe(5); });
  it("renders competition and training together", async () => {
    const select = vi.fn();
    render(<AnnualCalendar items={[item("goal", "10K Villanueva", "competition", "competition"), item("run", "Carrera suave", "running")]} year={2028} onYearChange={vi.fn()} onSelectDate={select} />);
    const day = screen.getByRole("button", { name: /29 de febrero de 2028, 2 eventos/ });
    expect(day.querySelector(".calendar-item--competition")).toHaveTextContent("10K Villanueva");
    expect(day.querySelector(".calendar-item--running")).toHaveTextContent("Carrera suave");
    expect(document.querySelector(".calendar-legend")).toHaveTextContent("Carrera");
    await userEvent.click(day); expect(select).toHaveBeenCalledWith("2028-02-29");
  });
  it("shows two daily items and announces additional ones", () => {
    render(<AnnualCalendar items={[item("1", "Uno", "running"), item("2", "Dos", "cycling"), item("3", "Tres", "strength")]} year={2028} onYearChange={vi.fn()} onSelectDate={vi.fn()} />);
    const day = screen.getByRole("button", { name: /3 eventos/ });
    expect(day.querySelectorAll(".calendar-event")).toHaveLength(2); expect(day).toHaveTextContent("+1");
  });
  it.each(["running", "cycling", "swimming", "strength", "competition"] as const)("renders the %s semantic variant", (variant) => {
    render(<AnnualCalendar items={[item(variant, variant, variant, variant === "competition" ? "competition" : "training")]} year={2028} onYearChange={vi.fn()} onSelectDate={vi.fn()} />);
    expect(document.querySelector(`.calendar-event.calendar-item--${variant}`)).toBeVisible();
  });
  it("navigates previous, next and current year", async () => {
    const change = vi.fn(); render(<AnnualCalendar items={[]} year={2028} onYearChange={change} onSelectDate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /anterior/ })); await userEvent.click(screen.getByRole("button", { name: /siguiente/ })); await userEvent.click(screen.getByRole("button", { name: /actual/ }));
    expect(change).toHaveBeenNthCalledWith(1, 2027); expect(change).toHaveBeenNthCalledWith(2, 2029); expect(change).toHaveBeenLastCalledWith(new Date().getFullYear());
  });
});
