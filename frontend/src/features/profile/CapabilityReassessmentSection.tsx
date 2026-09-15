import {useEffect, useState} from "react";
import type {ApiClient} from "../../services/apiClient";
import type {CapabilityReassessmentResponse, CapabilityKind} from "./reassessmentTypes";
import {confidenceLabels, reasonLabel, reassessmentError, statusPresentation} from "./reassessmentPresentation";
import {formatReferenceValue, getReferenceOriginLabel, getReferenceQualityLabel} from "./referenceFormat";
import "./capabilityReassessment.css";

const labels: Record<CapabilityKind, [string, string, string]> = {
  CYCLING_FTP: ["Ciclismo / FTP", "cycling", "power"],
  RUNNING_THRESHOLD_PACE: ["Carrera / Ritmo umbral", "running", "pace"],
  SWIMMING_CSS: ["Natación / CSS", "swimming", "swim_pace"],
};
export function CapabilityReassessmentSection({client, athleteId, canEdit, onReview, revision = 0}: {
  client: ApiClient; athleteId: string; canEdit: boolean; onReview(): void; revision?: number;
}) {
  const [state, setState] = useState<{athleteId: string; revision: number; data?: CapabilityReassessmentResponse; error?: string} | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setState(null);
    if (!client.capabilityReassessment) {
      setState({athleteId, revision, error: "La revisión de referencias no está disponible. Inténtalo de nuevo."});
      return;
    }
    void client.capabilityReassessment().then(data => {
      if (!active) return;
      if (data.athlete_profile_id !== athleteId) throw new Error("athlete mismatch");
      setState({athleteId, revision, data});
    }).catch(error => {if (active) setState({athleteId, revision, error: reassessmentError(error)});});
    return () => {active = false;};
  }, [client, athleteId, revision, retry]);
  const current = state?.athleteId === athleteId && state.revision === revision ? state : null;
  return <section className="performance-references capability-reassessment" aria-labelledby="reassessment-heading">
    <h2 id="reassessment-heading">Revisión de referencias</h2>
    <p>Información para decidir si conviene volver a medir tus referencias. Cualquier actualización del perfil es manual.</p>
    {!current ? <p role="status">Cargando revisión de referencias…</p> : current.error ? <div role="alert"><p>{current.error}</p><button type="button" className="button button--secondary" onClick={() => setRetry(value => value + 1)}>Reintentar revisión</button></div> : current.data && <>
      <p>Valoración al {current.data.as_of_date.split("-").reverse().join("/")} · Últimas 12 semanas, anteriores a esa fecha.</p>
      {!current.data.candidates.length ? <p>No hay valoraciones de referencias disponibles.</p> : <div className="reassessment-grid">
        {current.data.candidates.map(candidate => {
          const [title, sport, metric] = labels[candidate.capability_kind];
          const status = statusPresentation[candidate.status];
          const ref = candidate.current_reference;
          return <article className="reference-card" key={candidate.capability_kind}>
            <h3>{title}</h3>
            <p><strong className="reassessment-value">{ref ? formatReferenceValue(sport, metric, Number(ref.value)) : "Sin definir"}</strong></p>
            <span className="status-badge">{status.label}</span><p>{status.description}</p>
            <p>Confianza en la recomendación de revisión: <strong>{confidenceLabels[candidate.confidence]}</strong></p>
            <dl>
              <div><dt>Sesiones estructuradas evaluables</dt><dd>{candidate.evidence.eligible_comparisons}</dd></div>
              <div><dt>Recientes (últimas 4 semanas)</dt><dd>{candidate.evidence.recent}</dd></div>
              <div><dt>Anteriores (4–12 semanas)</dt><dd>{candidate.evidence.background}</dd></div>
              <div><dt>Evidencia contradictoria</dt><dd>{candidate.evidence.contradicting}</dd></div>
              {ref?.effective_from && <div><dt>Vigente desde</dt><dd>{new Date(ref.effective_from).toLocaleDateString("es-ES")}</dd></div>}
              {ref && <><div><dt>Origen</dt><dd>{getReferenceOriginLabel(ref.source ?? "")}</dd></div><div><dt>Calidad</dt><dd>{getReferenceQualityLabel(ref.quality)}</dd></div></>}
            </dl>
            <ul>{candidate.reason_codes.map(code => <li key={code}>{reasonLabel(code)}</li>)}</ul>
            {canEdit && <button type="button" className="button button--secondary" onClick={onReview} aria-label={`Revisar referencia: ${title}`}>Revisar referencia</button>}
          </article>;
        })}
      </div>}
    </>}
  </section>;
}
