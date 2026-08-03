import type { TrainingStatusPeriodWeeks } from "../../types/trainingStatus";

const numberFormatter = new Intl.NumberFormat("es-ES", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatStatusValue(value: number): string {
  return Number.isFinite(value) ? numberFormatter.format(value) : "—";
}

export function formatForm(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value > 0) return `+${formatStatusValue(value)}`;
  if (value < 0) return formatStatusValue(value).replace("-", "−");
  return formatStatusValue(0);
}

export function formatDailyLoad(value: number): string {
  return `${formatStatusValue(value)} puntos`;
}

export function formatStatusDate(value: string): string {
  return new Intl.DateTimeFormat("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function formatCalculatedAt(value: string): string {
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatHistoryDay(value: number): string {
  return `Día histórico ${value}`;
}

function localIsoDate(value: Date): string {
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}

export function getTrainingStatusRange(
  weeks: TrainingStatusPeriodWeeks,
  now = new Date(),
) {
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const start = new Date(end);
  start.setDate(start.getDate() - weeks * 7 + 1);
  return { startDate: localIsoDate(start), endDate: localIsoDate(end) };
}

export function getBrowserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Madrid";
}
