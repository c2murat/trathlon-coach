import { useEffect, useState } from "react";
import type { ApiClient } from "../../services/apiClient";
import type { TrainingLoadResponse } from "../../types/api";
import { getTrainingLoadQualityLabel } from "../../utils/trainingLoadFormat";
import { CalculationReliabilityHelp } from "../trainingLoad/components/CalculationReliabilityHelp";

const method = (value: string) => ({ cycling_power: "Potencia de ciclismo", heart_rate: "Frecuencia cardiaca", running_pace: "Ritmo de carrera", swimming_css: "CSS de natación", duration_only: "Duración" } as Record<string, string>)[value] ?? "No especificado";
const coverage = (value: string) => ({ complete: "Completa", partial: "Parcial", unavailable: "No disponible", not_applicable: "No aplicable" } as Record<string, string>)[value] ?? "No especificada";
const reason = (value: string | null) => ({ missing_duration: "Falta la duración", missing_reference: "Falta una referencia", unsupported_sport: "Deporte no compatible", insufficient_data: "Datos insuficientes", invalid_value: "Valor no válido", calculated: "Calculada" } as Record<string, string>)[value ?? ""] ?? "No especificado";
const finite = (value: number | null | undefined) => value != null && Number.isFinite(value) ? value : null;
function isNotFound(error: unknown) { return String(error).includes("404"); }

export function ActivityTrainingLoadSection({ activityId, client }: { activityId: string; client: ApiClient }) {
  const [load, setLoad] = useState<TrainingLoadResponse | null>(null);
  const [empty, setEmpty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true); setLoad(null); setEmpty(false); setError("");
    if (!client.trainingLoad) { setLoading(false); return () => { alive = false; }; }
    void client.trainingLoad(activityId).then((result) => { if (alive) { setLoad(result); setEmpty(false); } }).catch((requestError) => { if (!alive) return; if (isNotFound(requestError)) setEmpty(true); else setError("No se pudo consultar la carga de entrenamiento."); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [activityId, client]);

  const calculate = () => {
    if (!client.recalculateTrainingLoad || busy) return;
    setBusy(true); setError("");
    void client.recalculateTrainingLoad(activityId).then((result) => { setLoad(result); setEmpty(false); }).catch((requestError) => setError(String(requestError).includes("422") ? "Los datos de la solicitud no son válidos." : String(requestError).includes("404") ? "No se pudo acceder a la actividad." : "No se pudo calcular la carga de entrenamiento.")).finally(() => setBusy(false));
  };

  return <section className="summary-section training-load-section" aria-labelledby="training-load-title">
    <h2 id="training-load-title">Carga de entrenamiento</h2>
    {loading && <p aria-live="polite">Cargando carga de entrenamiento…</p>}
    {error && <p role="alert" className="error-banner">{error}</p>}
    {!loading && empty && !load && <div><p>Aún no se ha calculado la carga de esta actividad.</p><button className="button button--primary" type="button" onClick={calculate} disabled={busy}>{busy ? "Calculando carga…" : "Calcular carga"}</button></div>}
    {!loading && load && <div aria-live="polite">
      <p className="training-load-value">{finite(load.load_value) === null ? "La carga se calculó, pero no hay datos suficientes para obtener un valor numérico." : `${new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 }).format(load.load_value as number)} puntos`}</p>
      <dl className="training-load-meta">
        <div><dt>Método de cálculo</dt><dd>{method(load.method)}</dd></div>
        <div><dt>Cobertura de datos</dt><dd>{coverage(load.coverage)}</dd></div>
        <div><dt><span className="label-with-help">Fiabilidad del cálculo <CalculationReliabilityHelp /></span></dt><dd>{getTrainingLoadQualityLabel(load.quality)}</dd></div>
        {finite(load.duration_seconds) != null && <div><dt>Duración</dt><dd>{Math.round(load.duration_seconds! / 60)} min</dd></div>}
        {finite(load.reference_value) != null && <div><dt>Valor de referencia</dt><dd>{load.reference_value} {load.reference_metric ?? ""}</dd></div>}
        {load.reason && <div><dt>Estado del cálculo</dt><dd>{reason(load.reason)}</dd></div>}
      </dl>
      {load.warnings?.length > 0 && <div><h3>Advertencias</h3><ul>{load.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}
      <button className="button button--secondary" type="button" onClick={calculate} disabled={busy}>{busy ? "Recalculando carga…" : "Recalcular carga"}</button>
    </div>}
  </section>;
}
