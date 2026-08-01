import { useId } from "react";

export const CALCULATION_RELIABILITY_HELP = "Indica la confianza del algoritmo en la estimación según los datos disponibles y el método utilizado. No representa la intensidad ni la calidad deportiva del entrenamiento.";

export function CalculationReliabilityHelp() {
  const tooltipId = useId();
  return <span className="calculation-help">
    <button type="button" className="calculation-help__trigger" aria-label="Ayuda sobre la fiabilidad del cálculo" aria-describedby={tooltipId}>?</button>
    <span id={tooltipId} role="tooltip" className="calculation-help__tooltip">{CALCULATION_RELIABILITY_HELP}</span>
  </span>;
}


