# Cierre del bloque 4B — Fuerza temporal independiente

Version publicable. Los enlaces a informe/ remiten a evidencia privada local no distribuida. Las frases sobre ausencia de commits/push describen la entrega original; el estado Git actual figura en integral-consolidation-status.md.

**4B queda cerrado funcional y arquitectónicamente en shadow. La duración efectiva de fuerza sigue siendo legacy.** No hay activación implícita por complete, por elegibilidad ni por ausencia de incompatibilidad demostrable.

## Arquitectura y capacidades

```mermaid
flowchart LR
    I[Strength Intent] --> W[Workout Builder existente]
    W --> T[Independent Timing Inputs]
    T --> S[Strength Timing]
    S --> E[Temporal Eligibility shadow]
    E -. futuro .-> F[Planning Feasibility]
    F -. futuro .-> A[Activation Decision]
```

Este es el flujo de integración conceptual; no significa que los inputs o la elegibilidad gobiernen actualmente el builder. El workout legacy se construye primero y sirve como referencia inmutable a los sidecars. La aplicación obtiene reportes 4B/4B.1/4B.3 efímeros al finalizar el artefacto. La elegibilidad 4B.5 se ejecuta únicamente desde auditorías y pruebas, sin consumidor productivo. Planning Feasibility y Activation Decision de esta cadena no están implementados.

| Entrega | Capacidad | Evidencia / límite |
|---|---|---|
| 4B inicial | Structured Strength Intent observacional, estructura y progresión explicadas | Duración histórica conservada; sin segundos independientes |
| 4B.1 | Snapshot privado ligado a atleta/workout/ruta, intervalos y suma disjunta | 468 unavailable; 39 casos temporales |
| 4B.2 | Inputs explícitos de reps/tempo/timed/isométrico/lados, huecos, extremos y repeats secuenciales | Un solo compilador/estimador; 30 casos adicionales; no defaults |
| 4B.3 | Política versionada del alcance de descansos bilaterales existentes y reconciliación posterior | 468 partial; 34 casos adicionales; cero complete |
| 4B.4 | Auditoría diferenciada, fuentes verificadas y fronteras diagnósticas | 468 partial sin cambios; 22 casos adicionales; no selección injustificada de tempos |
| 4B.5 | Elegibilidad temporal mínima con evidencia de revisión vinculada y separación de responsabilidades | 468 partial, cero elegibles, cero activaciones; 22 casos adicionales |

Los contratos son internos e inmutables; schemas públicos, contenido fingerprinted y datos persistentes no se amplían. Los snapshots poseen su propia identidad. Las fuentes prescriptivas y medidas se distinguen; intervalos min/max no son intervalos probabilísticos. Partial nunca se presenta como total, ni unknown como cero. No se usan puntos medios ni confianza estadística inventada.

## Resultados acumulados

La suite temporal acumulada pasa **147 casos**: 39 + 30 + 34 + 22 + 22. El inventario completo de fuerza 4B incluye además 20 casos de Strength Intent, **167 en total**, todos incluidos en backend. En 4B.4 la regresión backend era 2012 casos; el cierre 4B.5 añade 22. El resultado final verificado de backend y checks está en el cierre de [block4b5-delivery.md](block4b5-delivery.md) y su JSON de validación final; no se suman los 167 de nuevo al total backend.

Se mantienen 468 evaluaciones de escenarios solapados: 0 complete, 468 partial, 0 unavailable; 0 temporalmente elegibles y 468 no elegibles. No hay incompatibilidades temporales demostradas con los subtotales; tampoco evidencia de compatibilidad completa. Continúan desconocidas 2768 ejecuciones, 1394 requisitos de alcance unilateral, 2300 huecos y 936 extremos. Son requisitos de información, no eventos que sumar como tiempo.

Los cinco escenarios NULL/explícitos, referencia/límite de carrera y dobles preservan los bytes de artefactos, workouts, fingerprints y reportes temporales anteriores. Los diagnósticos de elegibilidad son un sidecar nuevo. Ni siquiera las sesiones sintéticas elegibles activan duración nueva.

## Inventario y puntos de integración

| Archivo | Responsabilidad |
|---|---|
| `strength_intent.py` | Observar estructura y explicar legacy/progresión; sin autoridad temporal independiente |
| `strength_timing.py` | Únicos snapshot, intervalos, identidad, componentes y agregador temporal |
| `strength_timing_inputs.py` | Inputs concretos por sesión y compilación al mismo snapshot |
| `strength_timing_policy.py` | Selección prescriptiva shadow y comparación con legacy después del cálculo |
| `strength_timing_eligibility.py` | Recalcular integridad, exigir revisión vinculada y separar elegibilidad de activación |
| `workout_builder.py`, `workout_labels.py` | Recetas/catálogo existentes; sin nuevos tempos fijos ni datos observados fabricados |
| `intent_workouts.py` | Adaptador de contenido desde intents, preservando ancla e identidad al distribuir |
| `application/planning_preview.py` | Sidecars previos efímeros; ningún consumo de elegibilidad nuevo |

Estos módulos se sitúan en `backend/app/domains/planning/` salvo el de aplicación. Pruebas: `test_strength_intent_shadow.py` y los cinco ficheros `test_strength_timing.py`, `test_strength_timing_inputs.py`, `test_strength_timing_policy.py`, `test_strength_temporal_completion.py`, `test_strength_timing_eligibility.py`. El test inicial de intención no forma parte de las 147 temporales. Auditores: `audit_strength_timing.py`, `audit_strength_timing_inputs.py`, `audit_strength_temporal_policy.py`, `audit_strength_temporal_completion.py` y `audit_strength_timing_eligibility.py`, además de la auditoría inicial de Strength Intent. Las entregas y matrices `docs/block4b*` e `informe/block4b*` contienen las evidencias de cada etapa.

## Condiciones para retomar duración independiente

Se necesita enriquecer la descripción de capacidades del catálogo y la prescripción concreta de cada sesión sin confundirlas: tempo completo o tiempo por serie/hold, semántica de lados/reps, descanso entre series/lados/rondas, huecos/transiciones y extremos. Datos observados solo con fuente válida y ámbitos claros. Ningún nombre/patrón, RPE ni presupuesto determina automáticamente segundos.

Después del cálculo independiente harían falta revisión temporal trazable y elegibilidad, evaluación separada de disponibilidad diaria/distribución/dobles/carga/presupuesto, conservación de intención deportiva, criterio explícito para consumir un intervalo y una decisión de activación expresamente autorizada, reversible y con fallback legacy. Complete y elegible no sustituyen esas etapas. No se implementa ninguna de ellas como ruta activa en este cierre.

Riesgos/deuda: autenticidad y aplicabilidad de revisiones externas; falta de evidencia segmentada; semántica de catálogo insuficiente; protocolos deportivos todavía no seleccionables con el contexto actual; incertidumbre de material/preparación; concurrencia general no soportada; política top-down de minutos aún no definida. La evidencia actual no permite calibración ni certificación empírica del total. No se resuelve esa deuda cambiando duración para coincidir con legacy.

## Hoja de ruta original y continuación

Fuente: [diseño original, sección M](coherent-weekly-planning-engine-design.md), contrastado con el encargo original 0.8G.2E.1 y las entregas posteriores. La numeración original es **0–8**; 4A, 4B y sus subbloques son desgloses posteriores. La entrega llamada «Bloque 3: Weekly Volume Intent» no coincide uno a uno con todas las responsabilidades del bloque 3 del diseño: el estado se mapea por funcionalidad, no solo por título.

| Original | Objetivo | Estado verificable actual / pendiente |
|---|---|---|
| 0 | Evidencia congelada | Cubierto para los escenarios auditados; ampliar si cambia el alcance |
| 1 | Contratos y modo sombra | WeeklyPlanningIntent/SessionIntent/trazas implementados |
| 2 | Frecuencia y composición | Target total y autoridad explícita de intents implementados; NULL conserva legacy y capacidad se explica |
| 3 | Progresión explicada | Reglas/caps/variantes existentes observados y preservados en informes e intents; no se ha creado una nueva progresión deportiva |
| 4 | Envelope y asignación | Volume Intent bottom-up y autoridad de resistencia 4A implementados; fuerza 4B cerrada con legacy. Un target top-down independiente sigue pendiente de política específica, no se declara resuelto |
| 5 | Construcción de contenido | Núcleo existente en IntentWorkoutBuild/WorkoutBuilder: recetas desde intent antes de distribución, ancla estable y equivalencia. Fuerza/tiempo ya contrastados; cualquier cambio temporal posterior sigue fuera de activación. No hace falta fabricar minutos para conservar esta construcción |
| 6 | Calendario global semanal | Existe búsqueda acotada y scoring previo; pendiente completar el diseño original de semillas/poda/precedencia, desglose y estados de búsqueda/fronteras con evidencia de rendimiento |
| 7 | Evaluación única | Hay diagnósticos/reconciliación previos; pendiente unificar intención frente a final, warnings y trade-offs, sin confundir unknown/review con cumplimiento |
| 8 | Comparación de horizonte | Hay replays/goldens parciales y completos de etapas; pendiente comparación/activación de la arquitectura final como conjunto tras 6/7 |

**Siguiente bloque recomendado: 6, «Calendario global semanal», de la hoja de ruta original.** Antes de sus cambios, contrastar sus precondiciones con los contratos de contenido ya existentes del bloque 5; no renumerar esa comprobación como una fase nueva ni reabrir fuerza para inventar duración. Trabajar con identidades, conteos, minutos y recetas congelados, manteniendo explícita la limitación bottom-up del envelope. El calendario no necesita resolver una política top-down inexistente para mejorar la colocación de esas mismas sesiones.

Propuesta concreta, sin implementación: medir saturación de la búsqueda actual a 12000 nodos y calidad de sus testigos; comparar semilla greedy y semillas factibles que preserven largos/días libres; añadir poda admisible y orden determinista; completar precedencia de preferencias frente a costes blandos; distinguir solución factible no probada óptima de límite sin testigo. Validar fronteras entre semanas, objetivo total seis, una clave por día, capacidad/dobles y contenido idéntico. La aceptación debe exigir causas explicables de pérdida de frecuencia, ninguna falsa prueba de inviabilidad y costes de búsqueda medidos en todo el horizonte.

La utilidad inmediata para el deportista es preservar días preferidos libres y largos, agrupar dobles compatibles solo cuando ayudan y explicar conflictos reales sin cambiar sesiones ni fabricar carga. Después corresponde el bloque 7 para consolidar avisos/evaluación y el 8 para comparar/activar el conjunto bajo sus propias condiciones. No se avanza a ninguno en 4B.5.

Estado final: infraestructura temporal disponible para datos futuros, cierre seguro en shadow, duración legacy conservada, limitaciones explícitas. Sin datos reales modificados, planes aceptados, staging, commit ni push.

## Resultado final verificado

Backend: **2034 passed, 8 warnings**. Fuerza 4B: **167 casos**, incluidos **147 temporales**. Compileall y diff-check correctos; cinco escenarios con identidad completa de bytes/fingerprints/reportes protegidos; 468 partial, cero elegibles y cero activaciones. Duracion legacy intacta. [Evidencia final](../informe/block4b5-final-checks.json).
