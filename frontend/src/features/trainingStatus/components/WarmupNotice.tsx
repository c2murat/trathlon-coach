import type { DailyTrainingStatus } from "../../../types/trainingStatus";

export function WarmupNotice({ status }: { status: DailyTrainingStatus }) {
  if (!status.is_warmup) {
    return <span className="status-history-badge">Historial consolidado</span>;
  }
  return (
    <section className="status-warmup" aria-label="Periodo de adaptación del modelo">
      <strong>Periodo de adaptación del modelo</strong>
      <p>
        El estado todavía se está estabilizando porque hay menos de 85 días
        completos de historial.
      </p>
      <span>Día del historial: {status.history_day_number} de 84</span>
    </section>
  );
}
