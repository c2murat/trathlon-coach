import type {FatigueTrend, FitnessTrend, FormState, NotableTrend, OverallState, TrainingStatusInterpretation} from "./interpretationTypes";

const headlines: Record<OverallState, string> = {
  RECOVERING: "La fatiga ha bajado respecto a hace siete días",
  FRESH: "El modelo muestra mayor frescura",
  BALANCED: "Fitness y fatiga están próximos",
  BUILDING: "Estás acumulando fitness",
  LOADED: "Estás en un periodo de carga",
  HIGH_LOAD: "La carga acumulada pesa en tu frescura",
  REDUCED_LOAD: "Fitness y fatiga han bajado respecto a hace siete días",
  INSUFFICIENT_DATA: "Todavía no hay suficientes datos para interpretar tu estado de forma.",
};
const badges: Record<OverallState, string> = {
  RECOVERING: "Frescura en recuperación", FRESH: "Mayor frescura", BALANCED: "Equilibrio relativo",
  BUILDING: "Fitness en crecimiento", LOADED: "Periodo de carga", HIGH_LOAD: "Carga relativa alta",
  REDUCED_LOAD: "Carga en descenso", INSUFFICIENT_DATA: "Datos insuficientes",
};
const fitness: Record<FitnessTrend, string> = {
  RISING: "Tu fitness estimado ha crecido respecto a hace siete días.",
  STABLE: "Tu fitness se mantiene bastante estable.",
  FALLING: "Tu fitness estimado ha bajado respecto a hace siete días.",
  INSUFFICIENT_DATA: "Aún no hay un histórico reciente suficiente para describir su tendencia.",
};
const fatigue: Record<FatigueTrend, string> = {
  RISING_FAST: "La fatiga ha aumentado con rapidez en los últimos siete días.",
  RISING: "La fatiga estimada ha aumentado en los últimos siete días.",
  STABLE: "Tu nivel de fatiga se mantiene bastante estable.",
  FALLING: "La fatiga estimada ha bajado respecto a hace siete días.",
  INSUFFICIENT_DATA: "Aún no hay un histórico reciente suficiente para describir su tendencia.",
};
const form: Record<FormState, string> = {
  VERY_FRESH: "La fatiga calculada está claramente por debajo del fitness: el modelo muestra mucha frescura relativa.",
  FRESH: "La fatiga calculada está por debajo del fitness: el modelo muestra mayor frescura.",
  BALANCED: "El fitness y la fatiga están en valores próximos.",
  LOADED: "Ahora mismo estás más cargado que fresco dentro de este modelo.",
  HIGHLY_LOADED: "La fatiga calculada supera ampliamente al fitness y la frescura relativa es baja.",
  INSUFFICIENT_DATA: "Faltan datos recientes suficientes para situar tu frescura actual.",
};
const notable: Record<NotableTrend, string> = {
  FATIGUE_RISING_FASTER_THAN_FITNESS: "En los últimos siete días, la fatiga ha aumentado más que el fitness.",
  RECOVERY_TREND: "La fatiga está descendiendo mientras el fitness se mantiene o crece.",
  BOTH_STABLE: "Fitness y fatiga se mantienen bastante estables.",
  BOTH_FALLING: "Ambos indicadores descienden; estos datos por sí solos no distinguen una recuperación planificada de una reducción del entrenamiento.",
  NO_NOTABLE_TREND: "Los cambios recientes no muestran una relación destacada entre ambos indicadores.",
  INSUFFICIENT_HISTORY: "Se necesita una secuencia reciente de datos diarios para comparar su evolución.",
};
const summaries: Record<OverallState, string> = {
  RECOVERING: "El modelo refleja una recuperación de frescura relativa.",
  FRESH: "El modelo muestra mayor frescura relativa.",
  BALANCED: "La diferencia entre fitness y fatiga es pequeña dentro del modelo.",
  BUILDING: "La diferencia entre fitness y fatiga sigue siendo pequeña dentro del modelo.",
  LOADED: "Ahora mismo estás más cargado que fresco dentro de este modelo.",
  HIGH_LOAD: "La frescura relativa es baja dentro del modelo, algo que puede aparecer en un bloque exigente.",
  REDUCED_LOAD: "El contexto de tu entrenamiento ayuda a entender este cambio.",
  INSUFFICIENT_DATA: "A medida que acumules entrenamientos, TriCoach podrá mostrar cómo evolucionan tu fitness, fatiga y frescura.",
};
function temporalCopy(value: TrainingStatusInterpretation, metric: "fitness" | "fatigue") {
  const broad = metric === "fitness" ? value.broader_context.fitness_trend : value.broader_context.fatigue_trend;
  const short = metric === "fitness" ? fitness[value.fitness_explanation_key] : fatigue[value.fatigue_explanation_key];
  const label = metric === "fitness" ? "Tu aptitud física estimada" : "Tu fatiga estimada";
  const context: Record<FatigueTrend, string> = {
    RISING: `${label} sigue por encima de hace tres semanas`,
    RISING_FAST: `${label} ha aumentado claramente respecto a hace tres semanas`,
    STABLE: `${label} está cerca del valor de hace tres semanas`,
    FALLING: `${label} está por debajo del valor de hace tres semanas`,
    INSUFFICIENT_DATA: short.slice(0, -1),
  };
  const recent = value.recent[metric];
  const ending = {
    RISING: ", y en los últimos tres días ha aumentado",
    FALLING: ", aunque en los últimos tres días ha descendido",
    STABLE: ", y en los últimos tres días se mantiene estable",
    MIXED: ", con oscilaciones en los últimos tres días",
    INSUFFICIENT_DATA: "",
  }[recent.direction];
  const clause = recent.direction === "FALLING" && broad === "FALLING"
    ? ", y en los últimos tres días también ha descendido" : ending;
  return context[broad] + clause + ".";
}

export function interpretationCopy(value: TrainingStatusInterpretation) {
  const sufficient = value.summary_key !== "INSUFFICIENT_DATA";
  const fitnessText = sufficient ? temporalCopy(value, "fitness") : fitness[value.fitness_explanation_key];
  const fatigueText = sufficient ? temporalCopy(value, "fatigue") : fatigue[value.fatigue_explanation_key];
  const formText = value.form_state === "LOADED" && value.recent.recovery_turn
    ? "La forma sigue siendo negativa: estás más cargado que fresco, aunque la bajada reciente de fatiga coincide con una recuperación de frescura."
    : form[value.form_explanation_key];
  const recentText = value.recent.recovery_turn
    ? "La fatiga ha cambiado de dirección: tras subir, lleva tres días descendiendo y la forma ha mejorado."
    : value.recent.fatigue.changed_direction
      ? (value.recent.fatigue.direction === "FALLING"
        ? "La fatiga ha empezado a descender en los últimos tres días tras un aumento previo."
        : "La fatiga ha empezado a subir en los últimos tres días tras un descenso previo.")
      : value.recent.fitness.changed_direction
        ? (value.recent.fitness.direction === "FALLING"
          ? "La aptitud física estimada ha empezado a descender en los últimos tres días tras un aumento previo."
          : "La aptitud física estimada ha empezado a subir en los últimos tres días tras un descenso previo.")
        : notable[value.notable_trend_key];
  return {headline: headlines[value.headline_key], badge: badges[value.overall_state],
    summary: sufficient ? `${fatigueText} ${fitnessText} ${formText}` : summaries[value.summary_key],
    fitness: fitness[value.fitness_explanation_key],
    fatigue: value.recent.fatigue.changed_direction
      ? fatigue[value.fatigue_explanation_key].slice(0,-1) + (value.recent.fatigue.direction === "FALLING"
        ? ", aunque ha descendido en los últimos tres días." : ", aunque ha aumentado en los últimos tres días.")
      : fatigue[value.fatigue_explanation_key],
    form: formText,
    notable: recentText,
    contextUnavailable: sufficient && value.broader_context.fitness_trend === "INSUFFICIENT_DATA"};
}
