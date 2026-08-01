import type { DailyTrainingLoadAggregate, TrainingLoadQuality } from "../types/trainingLoad";

export function formatTrainingLoad(value: number): string {
  if (!Number.isFinite(value)) throw new Error("Invalid training load");
  return value.toLocaleString("es-ES", { maximumFractionDigits: 1 });
}

export function formatTrainingDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) throw new Error("Invalid duration");
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return hours ? `${hours} h ${minutes} min` : `${minutes} min`;
}

export function formatTrainingLoadDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) throw new Error("Invalid date");
  return new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(+match[1], +match[2] - 1, +match[3])));
}

export function formatIsoWeekLabel(year: number, week: number): string {
  return `Semana ${week} · ${year}`;
}

export function getTrainingLoadCoverageLabel(value: DailyTrainingLoadAggregate["coverage"]): string {
  return ({ complete: "Completa", partial: "Parcial", unavailable: "No disponible" })[value];
}

export function getTrainingLoadQualityLabel(value: TrainingLoadQuality | string | null | undefined): string {
  return ({ high: "Fiabilidad alta", medium: "Fiabilidad media", low: "Fiabilidad baja", none: "No evaluable" } as Record<string, string>)[value ?? "none"] ?? "No evaluable";
}
