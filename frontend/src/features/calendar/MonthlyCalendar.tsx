import type { CalendarItem } from "./calendarItems";
import { CalendarLegend, dateKey, mondayOffset } from "./AnnualCalendar";
import { dateLabel, localDate } from "./competitionLabels";

const weekdays = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const monthName = (year: number, month: number) => new Intl.DateTimeFormat("es-ES", { month: "long", year: "numeric" }).format(new Date(year, month, 1));
export function monthGridRange(year: number, month: number) {
  const start = new Date(year, month, 1); start.setDate(start.getDate() - mondayOffset(year, month));
  const end = new Date(start); end.setDate(start.getDate() + 41);
  return { start: dateKey(start), end: dateKey(end) };
}

export function MonthlyCalendar({ items, year, month, selectedDate, onMonthChange, onSelectDate, today = dateKey(new Date()) }: { items: CalendarItem[]; year: number; month: number; selectedDate: string | null; onMonthChange: (year: number, month: number) => void; onSelectDate: (date: string) => void; today?: string }) {
  const { start } = monthGridRange(year, month), first = localDate(start), grouped = new Map<string, CalendarItem[]>();
  items.forEach((item) => grouped.set(item.date, [...(grouped.get(item.date) ?? []), item]));
  const move = (amount: number) => { const value = new Date(year, month + amount, 1); onMonthChange(value.getFullYear(), value.getMonth()); };
  const selected = selectedDate ? grouped.get(selectedDate) ?? [] : [];
  return <section className="monthly-calendar" aria-labelledby="monthly-calendar-title">
    <header className="monthly-calendar__header"><button type="button" aria-label="Mes anterior" onClick={() => move(-1)}>←</button><h2 id="monthly-calendar-title">{monthName(year, month)}</h2><button type="button" aria-label="Mes siguiente" onClick={() => move(1)}>→</button></header>
    <CalendarLegend items={items} />
    <div className="monthly-calendar__scroll"><div className="monthly-calendar__grid" role="grid" aria-label={`Calendario de ${monthName(year, month)}`}>
      {weekdays.map((day) => <div role="columnheader" className="monthly-calendar__weekday" key={day}>{day}</div>)}
      {Array.from({ length: 42 }, (_, index) => { const value = new Date(first); value.setDate(first.getDate() + index); const key = dateKey(value), events = grouped.get(key) ?? [], outside = value.getMonth() !== month; return <button type="button" role="gridcell" key={key} aria-selected={selectedDate === key} aria-label={`${dateLabel(key)}, ${events.length} ${events.length === 1 ? "evento" : "eventos"}`} className={`monthly-day${outside ? " monthly-day--outside" : ""}${today === key ? " monthly-day--today" : ""}${selectedDate === key ? " monthly-day--selected" : ""}`} onClick={() => onSelectDate(key)}><span className="monthly-day__number">{value.getDate()} {today === key && <small>Hoy</small>}</span><span className="monthly-day__items">{events.slice(0, 3).map((item) => <span title={`${item.title}. ${item.subtitle}`} className={`monthly-event calendar-item--${item.variant}`} key={item.id}><strong>{item.title}</strong><small>{item.subtitle}</small></span>)}{events.length > 3 && <span className="monthly-day__more">+{events.length - 3} más</span>}</span></button>; })}
    </div></div>
    {selectedDate && <section className="monthly-day-detail" aria-labelledby="monthly-day-detail-title"><h3 id="monthly-day-detail-title">{dateLabel(selectedDate)}</h3>{selected.length ? selected.map((item) => <article className={`monthly-detail-item calendar-item--${item.variant}`} key={item.id}><strong>{item.title}</strong><span>{item.subtitle}</span></article>) : <p>No hay entrenamientos ni competiciones este día.</p>}</section>}
  </section>;
}
