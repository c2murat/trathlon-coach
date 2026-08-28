import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ApiClient } from "../../services/apiClient";
import type {
  CompetitionCategory,
  CompetitionGoal,
  CompetitionGoalCreate,
  CompetitionGoalSegment,
  CompetitionPriority,
  CompetitionSegmentSport,
  TrainingPlanSession,
} from "../../types/planning";
import { AnnualCalendar } from "./AnnualCalendar";
import { calendarItems } from "./calendarItems";
import { monthGridRange, MonthlyCalendar } from "./MonthlyCalendar";
import { CompetitionCatalogSearch } from "./CompetitionCatalogSearch";
import { AppLink } from "../../app/usePathname";
import { durationLabel, sportLabel } from "./planningFormat";
import { categoryLabels, dateLabel, segmentLabels } from "./competitionLabels";
type SegmentDraft = {
  sport: CompetitionSegmentSport;
  distanceKm: string;
  label: string;
  elevation: string;
};
type Form = {
  name: string;
  eventDate: string;
  category: CompetitionCategory;
  format: string;
  priority: CompetitionPriority;
  targetTime: string;
  notes: string;
  city: string;
  region: string;
  country: string;
  segments: SegmentDraft[];
  sourceProvider?: "tavily";
  sourceUrl?: string;
};
const segment = (
  sport: CompetitionSegmentSport,
  distance_m?: number,
): SegmentDraft => ({
  sport,
  distanceKm: distance_m ? String(distance_m / 1000) : "",
  label: "",
  elevation: "",
});
const presetSegments: Record<string, SegmentDraft[]> = {
  "triathlon:sprint": [
    segment("swim", 750),
    segment("bike", 20000),
    segment("run", 5000),
  ],
  "triathlon:olympic": [
    segment("swim", 1500),
    segment("bike", 40000),
    segment("run", 10000),
  ],
  "triathlon:70.3": [
    segment("swim", 1900),
    segment("bike", 90000),
    segment("run", 21100),
  ],
  "triathlon:ironman": [
    segment("swim", 3800),
    segment("bike", 180000),
    segment("run", 42195),
  ],
  "duathlon:standard": [
    segment("run", 10000),
    segment("bike", 40000),
    segment("run", 5000),
  ],
  "aquathlon:standard": [
    segment("run", 2500),
    segment("swim", 1000),
    segment("run", 2500),
  ],
  "running:10k": [segment("run", 10000)],
  "running:half_marathon": [segment("run", 21097)],
  "running:marathon": [segment("run", 42195)],
  "cycling:custom": [segment("bike")],
  "swimming:custom": [segment("swim")],
};
const formats: Record<CompetitionCategory, { value: string; label: string }[]> =
  {
    triathlon: [
      { value: "sprint", label: "Sprint" },
      { value: "olympic", label: "Olímpico" },
      { value: "70.3", label: "70.3 / Media distancia" },
      { value: "ironman", label: "Ironman / Larga distancia" },
      { value: "custom", label: "Personalizado" },
    ],
    duathlon: [
      { value: "standard", label: "Estándar" },
      { value: "custom", label: "Personalizado" },
    ],
    aquathlon: [
      { value: "standard", label: "Estándar" },
      { value: "custom", label: "Personalizado" },
    ],
    running: [
      { value: "10k", label: "10K" },
      { value: "half_marathon", label: "Media maratón" },
      { value: "marathon", label: "Maratón" },
      { value: "custom", label: "Personalizado" },
    ],
    cycling: [{ value: "custom", label: "Personalizado" }],
    swimming: [{ value: "custom", label: "Personalizado" }],
  };
const initial = (): Form => ({
  name: "",
  eventDate: "",
  category: "running",
  format: "10k",
  priority: "A",
  targetTime: "",
  notes: "",
  city: "",
  region: "",
  country: "",
  segments: presetSegments["running:10k"].map((value) => ({ ...value })),
});
function seconds(value: string) {
  if (!value.trim()) return null;
  const parts = value.split(":").map(Number);
  return parts.length === 3 &&
    parts.every(
      (x, index) => Number.isInteger(x) && x >= 0 && (index === 0 || x < 60),
    )
    ? parts[0] * 3600 + parts[1] * 60 + parts[2]
    : NaN;
}
function humanTime(value: number | null) {
  if (value === null) return "";
  return `${Math.floor(value / 3600)}:${String(Math.floor((value % 3600) / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}
function draft(value: CompetitionGoalSegment): SegmentDraft {
  return {
    sport: value.sport,
    distanceKm: String(value.distance_m / 1000),
    label: value.label ?? "",
    elevation:
      value.elevation_gain_m === null ? "" : String(value.elevation_gain_m),
  };
}
export function CalendarPage({
  client,
  canManage,
  canGenerate = false,
  athleteName,
  athleteId,
}: {
  client: ApiClient;
  canManage: boolean;
  canGenerate?: boolean;
  athleteName?: string;
  athleteId?: string | null;
}) {
  const [goals, setGoals] = useState<CompetitionGoal[]>([]),
    [planned, setPlanned] = useState<TrainingPlanSession[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [form, setForm] = useState<Form>(initial),
    [editing, setEditing] = useState<string | null>(null),
    [saving, setSaving] = useState(false),
    [feedback, setFeedback] = useState(""),
    [panel, setPanel] = useState<"none" | "form" | "catalog">("none"),
    [view, setView] = useState<"list" | "month" | "year">("list"),
    [year, setYear] = useState(new Date().getFullYear()),
    [month, setMonth] = useState(new Date().getMonth()),
    [selectedDate, setSelectedDate] = useState<string | null>(null);
  const generation = useRef(0);
  const load = async () => {
    const current = ++generation.current;
    const range = view === "month" ? monthGridRange(year, month) : { start: `${year}-01-01`, end: `${year}-12-31` };
    setLoading(true);
    setError("");
    try {
      const [value, sessions] = await Promise.all([
        client.competitionGoals?.(),
        client.plannedTrainingSessions?.(range.start, range.end) ??
          Promise.resolve([]),
      ]);
      if (current === generation.current) {
        setGoals(value ?? []);
        setPlanned(sessions);
      }
    } catch {
      if (current === generation.current)
        setError("No se ha podido cargar el calendario.");
    } finally {
      if (current === generation.current) setLoading(false);
    }
  };
  useEffect(() => {
    setGoals([]);
    setPlanned([]);
    setPanel("none");
    setSelectedDate(null);
    void load();
    return () => {
      generation.current++;
    };
  }, [client, athleteId, view, year, month]);
  const chooseFormat = (category: CompetitionCategory, format: string) =>
    setForm((value) => ({
      ...value,
      category,
      format,
      segments: (presetSegments[`${category}:${format}`] ?? value.segments).map(
        (item) => ({ ...item }),
      ),
    }));
  const updateSegment = (
    index: number,
    key: keyof SegmentDraft,
    value: string,
  ) =>
    setForm((current) => ({
      ...current,
      segments: current.segments.map((item, i) =>
        i === index ? { ...item, [key]: value } : item,
      ),
    }));
  const move = (index: number, offset: number) =>
    setForm((current) => {
      const segments = [...current.segments],
        target = index + offset;
      if (target < 0 || target >= segments.length) return current;
      [segments[index], segments[target]] = [segments[target], segments[index]];
      return { ...current, segments };
    });
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const target = seconds(form.targetTime);
    if (Number.isNaN(target)) {
      setError("Introduce el objetivo de tiempo como h:mm:ss.");
      return;
    }
    const segments = form.segments.map((item) => ({
      sport: item.sport,
      distance_m: Math.round(Number(item.distanceKm) * 1000),
      label: item.label.trim() || null,
      elevation_gain_m: item.elevation
        ? Math.round(Number(item.elevation))
        : null,
    }));
    if (segments.some((item) => !item.distance_m || item.distance_m < 1)) {
      setError("Cada segmento debe tener una distancia válida.");
      return;
    }
    const payload: CompetitionGoalCreate = {
      name: form.name.trim(),
      event_date: form.eventDate,
      event_category: form.category,
      event_format: form.format,
      priority: form.priority,
      segments,
      target_finish_time_seconds: target,
      notes: form.notes.trim() || null,
      city: form.city.trim() || null,
      region: form.region.trim() || null,
      country: form.country.trim() || null,
      ...(form.sourceProvider && form.sourceUrl
        ? { source_provider: form.sourceProvider, source_url: form.sourceUrl }
        : {}),
    };
    setSaving(true);
    setError("");
    try {
      if (editing) await client.updateCompetitionGoal?.(editing, payload);
      else await client.createCompetitionGoal?.(payload);
      setPanel("none");
      setFeedback(editing ? "Objetivo actualizado." : "Objetivo añadido.");
      setEditing(null);
      setForm(initial());
      await load();
    } catch {
      setError("No se ha podido guardar el objetivo.");
    } finally {
      setSaving(false);
    }
  };
  const edit = (goal: CompetitionGoal) => {
    setEditing(goal.id);
    setForm({
      name: goal.name,
      eventDate: goal.event_date,
      category: goal.event_category,
      format: goal.event_format,
      priority: goal.priority,
      targetTime: humanTime(goal.target_finish_time_seconds),
      notes: goal.notes ?? "",
      city: goal.city ?? "",
      region: goal.region ?? "",
      country: goal.country ?? "",
      segments: goal.segments.map(draft),
    });
    setPanel("form");
  };
  const cancel = async (goal: CompetitionGoal) => {
    if (!confirm(`¿Cancelar ${goal.name}?`)) return;
    try {
      await client.deleteCompetitionGoal?.(goal.id);
      setFeedback("Objetivo cancelado.");
      await load();
    } catch {
      setError("No se ha podido cancelar el objetivo.");
    }
  };
  const shown = selectedDate
    ? goals.filter((goal) => goal.event_date === selectedDate)
    : goals;
  return (
    <section className="calendar-page" aria-labelledby="calendar-title">
      <header className="calendar-header">
        <div>
          <p className="eyebrow">PLANIFICACIÓN</p>
          <h1 id="calendar-title">Calendario</h1>
          <p>Competiciones y objetivos de temporada.</p>
        </div>
        <div className="calendar-actions">
          {canGenerate && (
            <AppLink
              className="button button--primary"
              to="/calendar/planning/new"
            >
              Generar plan de entrenamiento
            </AppLink>
          )}
          {canManage && (
            <>
              <button
                className="button"
                onClick={() => {
                  setEditing(null);
                  setForm(initial());
                  setPanel("form");
                }}
              >
                + Añadir objetivo
              </button>
              <button className="button" onClick={() => setPanel("catalog")}>
                Buscar competición
              </button>
            </>
          )}
        </div>
      </header>
      <div className="view-switch" aria-label="Vista de calendario">
        <button aria-pressed={view === "list"} onClick={() => setView("list")}>
          Lista
        </button>
        <button aria-pressed={view === "month"} onClick={() => setView("month")}>
          Mes
        </button>
        <button aria-pressed={view === "year"} onClick={() => setView("year")}>
          Año
        </button>
      </div>
      {feedback && (
        <p role="status" className="success-banner">
          {feedback}
        </p>
      )}
      {error && (
        <div role="alert" className="error-banner">
          <span>{error}</span>
          <button onClick={() => void load()}>Reintentar</button>
        </div>
      )}
      {panel === "catalog" && canManage && (
        <CompetitionCatalogSearch
          client={client}
          onImported={async () => {
            setFeedback("Competición añadida como objetivo.");
            await load();
          }}
          onManualGoal={(value) => {
            const category = value.category ?? "running",
              format = formats[category][0].value;
            setEditing(null);
            setForm({
              ...initial(),
              name: value.name,
              category,
              format,
              segments: (presetSegments[`${category}:${format}`] ?? []).map(
                (item) => ({ ...item }),
              ),
              sourceProvider: value.sourceProvider,
              sourceUrl: value.sourceUrl,
            });
            setFeedback(
              "Completa o corrige los datos de la competición antes de guardarla.",
            );
            setPanel("form");
          }}
        />
      )}
      {panel === "form" && canManage && (
        <form className="goal-form" onSubmit={submit}>
          <fieldset>
            <legend>
              {editing ? "Editar objetivo" : "Nuevo objetivo de competición"}
            </legend>
            <label>
              Nombre
              <input
                required
                value={form.name}
                onChange={(e) =>
                  setForm((x) => ({ ...x, name: e.target.value }))
                }
              />
            </label>
            <label>
              Fecha
              <input
                required
                type="date"
                value={form.eventDate}
                onChange={(e) =>
                  setForm((x) => ({ ...x, eventDate: e.target.value }))
                }
              />
            </label>
            <label>
              Tipo de competición
              <select
                value={form.category}
                onChange={(e) =>
                  chooseFormat(
                    e.target.value as CompetitionCategory,
                    formats[e.target.value as CompetitionCategory][0].value,
                  )
                }
              >
                {Object.entries(categoryLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Formato/distancia
              <select
                value={form.format}
                onChange={(e) => chooseFormat(form.category, e.target.value)}
              >
                {formats[form.category].map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="segment-editor">
              <legend>Segmentos</legend>
              {form.segments.map((item, index) => (
                <div className="segment-row" key={index}>
                  <span>{index + 1}</span>
                  <label>
                    Deporte
                    <select
                      value={item.sport}
                      onChange={(e) =>
                        updateSegment(index, "sport", e.target.value)
                      }
                    >
                      {Object.entries(segmentLabels).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Distancia (km)
                    <input
                      required
                      type="number"
                      min="0.001"
                      step="0.001"
                      value={item.distanceKm}
                      onChange={(e) =>
                        updateSegment(index, "distanceKm", e.target.value)
                      }
                    />
                  </label>
                  <label>
                    Etiqueta opcional
                    <input
                      value={item.label}
                      onChange={(e) =>
                        updateSegment(index, "label", e.target.value)
                      }
                    />
                  </label>
                  <label>
                    Desnivel + (m)
                    <input
                      type="number"
                      min="0"
                      value={item.elevation}
                      onChange={(e) =>
                        updateSegment(index, "elevation", e.target.value)
                      }
                    />
                  </label>
                  <div>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                      aria-label={`Subir segmento ${index + 1}`}
                    >
                      Subir
                    </button>
                    <button
                      type="button"
                      disabled={index === form.segments.length - 1}
                      onClick={() => move(index, 1)}
                      aria-label={`Bajar segmento ${index + 1}`}
                    >
                      Bajar
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setForm((x) => ({
                          ...x,
                          segments: x.segments.filter((_, i) => i !== index),
                        }))
                      }
                      aria-label={`Eliminar segmento ${index + 1}`}
                    >
                      Eliminar
                    </button>
                  </div>
                </div>
              ))}
              <button
                type="button"
                onClick={() =>
                  setForm((x) => ({
                    ...x,
                    segments: [...x.segments, segment("run")],
                  }))
                }
              >
                Añadir segmento
              </button>
            </fieldset>
            <fieldset className="priority-field">
              <legend>Prioridad</legend>
              {(["A", "B", "C"] as const).map((value) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="priority"
                    checked={form.priority === value}
                    onChange={() => setForm((x) => ({ ...x, priority: value }))}
                  />
                  {value}
                </label>
              ))}
            </fieldset>
            <label>
              Objetivo de tiempo opcional
              <input
                placeholder="5:15:00"
                value={form.targetTime}
                onChange={(e) =>
                  setForm((x) => ({ ...x, targetTime: e.target.value }))
                }
              />
            </label>
            <div className="custom-distances">
              <label>
                Ciudad
                <input
                  value={form.city}
                  onChange={(e) =>
                    setForm((x) => ({ ...x, city: e.target.value }))
                  }
                />
              </label>
              <label>
                Región
                <input
                  value={form.region}
                  onChange={(e) =>
                    setForm((x) => ({ ...x, region: e.target.value }))
                  }
                />
              </label>
              <label>
                País
                <input
                  value={form.country}
                  onChange={(e) =>
                    setForm((x) => ({ ...x, country: e.target.value }))
                  }
                />
              </label>
            </div>
            <label>
              Notas opcionales
              <textarea
                value={form.notes}
                onChange={(e) =>
                  setForm((x) => ({ ...x, notes: e.target.value }))
                }
              />
            </label>
            <div className="goal-form__actions">
              <button className="button button--primary" disabled={saving}>
                {saving ? "Guardando…" : "Guardar objetivo"}
              </button>
              <button
                type="button"
                className="button"
                onClick={() => setPanel("none")}
              >
                Cancelar
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {view === "year" ? (
        <AnnualCalendar
          items={calendarItems(goals,planned)}
          year={year}
          onYearChange={setYear}
          onSelectDate={(date) => {
            setSelectedDate(date);
            setView("list");
          }}
        />
      ) : view === "month" ? (
        <MonthlyCalendar
          items={calendarItems(goals, planned)}
          year={year}
          month={month}
          selectedDate={selectedDate}
          onMonthChange={(nextYear, nextMonth) => {
            setSelectedDate(null);
            setYear(nextYear);
            setMonth(nextMonth);
          }}
          onSelectDate={setSelectedDate}
        />
      ) : loading ? (
        <p className="loading-state">Cargando calendario…</p>
      ) : shown.length === 0 && planned.length === 0 ? (
        <div className="empty-state">
          <h2>
            {selectedDate
              ? `No hay elementos el ${dateLabel(selectedDate)}.`
              : canManage
                ? "Todavía no tienes objetivos ni sesiones planificadas."
                : "Este atleta todavía no tiene planificación."}
          </h2>
        </div>
      ) : (
        <div className="goal-list" aria-label="Calendario de entrenamiento">
          {selectedDate && (
            <button onClick={() => setSelectedDate(null)}>
              Ver todo el calendario
            </button>
          )}
          {shown.map((goal) => (
            <article className="goal-card calendar-item--goal" key={goal.id}>
              <time dateTime={goal.event_date}>
                {dateLabel(goal.event_date)}
              </time>
              <div>
                <span
                  className={`priority-badge priority-badge--${goal.priority}`}
                >
                  ◆ OBJETIVO {goal.priority}
                </span>
                <h2>{goal.name}</h2>
                <p>
                  {categoryLabels[goal.event_category]} ·{" "}
                  {formats[goal.event_category].find(
                    (item) => item.value === goal.event_format,
                  )?.label ?? goal.event_format}
                </p>
              </div>
              {canManage && (
                <div className="goal-card__actions">
                  <button onClick={() => edit(goal)}>Editar objetivo</button>
                  <button onClick={() => void cancel(goal)}>
                    Cancelar objetivo
                  </button>
                </div>
              )}
            </article>
          ))}
          {planned
            .filter((x) => !selectedDate || x.scheduled_date === selectedDate)
            .map((session) => (
              <article
                className={`goal-card calendar-item--planned calendar-item--${session.sport}`}
                key={session.id}
              >
                <time dateTime={session.scheduled_date}>
                  {dateLabel(session.scheduled_date)}
                </time>
                <div>
                  <span className="session-badge">● PLANIFICADA</span>
                  <h2>{session.title}</h2>
                  <p>
                    {sportLabel(session.sport)} ·{" "}
                    {durationLabel(session.planned_duration_seconds)}
                  </p>
                </div>
              </article>
            ))}
        </div>
      )}
      {!canManage && goals.length > 0 && (
        <p className="read-only-note">
          Puedes consultar la planificación de {athleteName ?? "este atleta"} en
          modo solo lectura.
        </p>
      )}
    </section>
  );
}
