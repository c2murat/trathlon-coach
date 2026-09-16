import type {TrainingStatusInterpretation} from "./interpretationTypes";
import {interpretationCopy} from "./interpretationPresentation";
import {formatStatusDate} from "./trainingStatusFormat";
import "./trainingStatusSummary.css";

export function TrainingStatusSummary({interpretation}: {interpretation: TrainingStatusInterpretation}) {
  const copy = interpretationCopy(interpretation);
  return <section className="training-status-summary" aria-labelledby="status-summary-title">
    <header><h2 id="status-summary-title">Resumen de tu estado actual</h2><span className="status-badge">{copy.badge}</span></header>
    <h3>{copy.headline}</h3><p>{copy.summary}</p>
    {copy.contextUnavailable && <p className="status-summary-date">Aún no hay una secuencia completa de 21 días para contextualizar la carga.</p>}
    {interpretation.data_date && <p className="status-summary-date">Datos del {formatStatusDate(interpretation.data_date)}.</p>}
    {interpretation.reason_codes.includes("STALE_STATUS") && <p>Los últimos valores guardados necesitan actualizarse para describir tu estado actual.</p>}
    {interpretation.overall_state !== "INSUFFICIENT_DATA" && <>
      <div className="status-summary-explanations">
        <section data-series="fitness"><h4>Fitness</h4><p>{copy.fitness}</p></section>
        <section data-series="fatigue"><h4>Fatiga</h4><p>{copy.fatigue}</p></section>
        <section data-series="form"><h4>Forma</h4><p>{copy.form}</p></section>
      </div>
      <p className="status-summary-notable"><strong>Observación reciente: </strong>{copy.notable}</p>
    </>}
    <details><summary tabIndex={0}>Qué significa cada indicador</summary><dl>
      <dt>Fitness</dt><dd>Una estimación de la forma física que has ido construyendo durante varias semanas.</dd>
      <dt>Fatiga</dt><dd>Una estimación del cansancio acumulado principalmente por tus entrenamientos recientes.</dd>
      <dt>Forma</dt><dd>Una estimación de lo fresco o cargado que estás en relación con tu fitness.</dd>
    </dl></details>
    <p className="status-summary-caveat">Estos indicadores son una estimación matemática basada en tu carga de entrenamiento. Interprétalos junto con tus sensaciones, descanso y estado general.</p>
  </section>;
}
