import type { CalendarItem, CalendarItemVariant } from "./calendarItems";
import { localDate } from "./competitionLabels";

const months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const weekdays = ["L", "M", "X", "J", "V", "S", "D"];
const legend: Array<[CalendarItemVariant, string]> = [["running", "Carrera"], ["cycling", "Ciclismo"], ["swimming", "Natación"], ["strength", "Fuerza"], ["competition", "Competición"], ["recovery", "Recuperación"], ["other", "Otros"]];
const visiblePerDay = 2;

export function daysInMonth(year: number, month: number) { return new Date(year, month + 1, 0).getDate(); }
export function mondayOffset(year: number, month: number) { return (new Date(year, month, 1).getDay() + 6) % 7; }
export function dateKey(date: Date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }

export function CalendarLegend({ items }: { items: CalendarItem[] }) {
  const supported = new Set(items.map((item) => item.variant));
  return <div className="calendar-legend" aria-label="Leyenda del calendario">{legend.filter(([variant]) => !["other", "recovery"].includes(variant) || supported.has(variant)).map(([variant, label]) => <span key={variant}><i className={`calendar-legend__swatch calendar-item--${variant}`} aria-hidden="true" />{label}</span>)}</div>;
}

export function AnnualCalendar({ items, year, onYearChange, onSelectDate }: { items: CalendarItem[]; year: number; onYearChange: (year: number) => void; onSelectDate: (date: string) => void }) {
  const currentYear = new Date().getFullYear(), grouped = new Map<string, CalendarItem[]>();
  items.forEach((item) => grouped.set(item.date, [...(grouped.get(item.date) ?? []), item]));
  return <section className="annual-calendar" aria-labelledby="annual-calendar-title"><header className="annual-calendar__header"><h2 id="annual-calendar-title">Año {year}</h2><div><button onClick={() => onYearChange(year - 1)} aria-label="Año anterior">←</button><button onClick={() => onYearChange(currentYear)}>Año actual</button><button onClick={() => onYearChange(year + 1)} aria-label="Año siguiente">→</button></div></header><CalendarLegend items={items} /><div className="annual-calendar__months">{months.map((name, month) => <section className="year-month" key={name} aria-label={`${name} de ${year}`}><h3>{name}</h3><div className="year-month__grid year-month__weekdays" aria-hidden="true">{weekdays.map((day, index) => <span key={index}>{day}</span>)}</div><div className="year-month__grid">{Array.from({ length: mondayOffset(year, month) }, (_, index) => <span key={`blank-${index}`} />)}{Array.from({ length: daysInMonth(year, month) }, (_, index) => { const day = index + 1, date = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`, events = grouped.get(date) ?? [], label = new Intl.DateTimeFormat("es-ES", { dateStyle: "long" }).format(localDate(date)); return events.length ? <button type="button" key={date} className="calendar-day calendar-day--events" onClick={() => onSelectDate(date)} aria-label={`${label}, ${events.length} ${events.length === 1 ? "evento" : "eventos"}`}><span className="calendar-day__number">{day}</span><span className="calendar-day__items">{events.slice(0, visiblePerDay).map((item) => <span className={`calendar-event calendar-item--${item.variant}`} key={item.id}><strong>{item.title}</strong><small>{item.subtitle}</small></span>)}{events.length > visiblePerDay && <small className="calendar-day__more">+{events.length - visiblePerDay} más</small>}</span></button> : <span className="calendar-day" key={date}><span className="calendar-day__number">{day}</span></span>; })}</div></section>)}</div></section>;
}
