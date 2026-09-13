# 0.8G.2C.5 — auditoría previa a la revisión del resolver

Fecha: 2026-09-13. Rama: `sprint-0.8a-authentication`.
HEAD local, referencia origin y remoto consultado con `git ls-remote`:
`444f602a5cd03ee14ff0fb5af196be2db81037b0`.

El árbol ya contenía cambios C.5 en planning_preview, contracts, models,
planning_adaptation, workout_builder y test_planning_adaptation, y dos archivos
nuevos numeric_adaptation/test_numeric_adaptation. Se revisan como trabajo previo.
`backups/`, `informe/` y temporales quedan fuera del alcance.

## Primitivas encontradas

* `workout_builder.WorkoutBuilderConfig`: rangos de ratios por familia y rol
  (easy, aerobic/endurance, tempo, sweet_spot, threshold, interval, warmup,
  recovery, cooldown, drill). Algunos extremos son ordenables numéricamente,
  pero son prescripciones de familias distintas, no niveles alternativos
  autorizados dentro de la misma sesión. Cambiar threshold por interval rebasa
  el rango de la familia actual; no hay política que autorice esa transición.
* `_progression_level`: ciclo temporal de tres estados usado por las plantillas
  para duración, distancia y repeticiones. No es una escala de targets de pace
  o power y reutilizarlo violaría las exclusiones de C.5.
* `WorkoutTarget.mode=zone`: admite índices, sin correspondencia numérica
  atleta/unidad ni política de adyacencia para estas prescripciones.
* Capability 0.8G.2A: RUN_DURATIONS, BIKE_DURATIONS, SWIM_DISTANCES ordenan
  dimensiones de esfuerzo. No ordenan alternativas para un esfuerzo fijo.
  Distribuciones de intensidad y clasificación resumen actividad, no prescriben.
* Adaptive targets 0.8G.2B: interpolación entre dimensiones; blends por confianza,
  fase, recencia y repetición; límites derivados de capability. Producen un único
  rango continuo. No contienen colección de candidatos ni paso adyacente.
* `_resolved_target`: referencia por ratios y ROUND_HALF_UP a vatios/segundos
  enteros. `_target_float` controla precisión de ratios. Son resolución numérica,
  no pasos fisiológicos. Ningún redondeo, blend, midpoint o bound será un step.
* C.3 sigue direccional y versionado 0.8G.2C.3. C.4 mantiene integración por
  identidad exacta del target; acceptance materializa el artifact almacenado.

## Decisión por disciplina, antes de modificar arquitectura

RUN pace, BIKE power y SWIM pace: no existe nivel adyacente reutilizable que
preserve tipo y límites de prescripción. Resultado elegible: `NO_SAFE_STEP`,
`proposed_range=None`. Strength: `NOT_APPLICABLE` con razón explícita.

Se elimina del borrador local la escala nueva `LEVELS` que enlazaba familias.
No se añade un proveedor genérico de candidatos artificiales para obtener
`RESOLVED`. El contrato reserva ese estado y la proyección versionada hacia C.4,
pero esta política no lo emite hasta disponer de una primitiva real del dominio.
C.5 trabaja sobre drafts ya resueltos por Planning/C.2B, en memoria, sin queries.
Los intentos sin adaptación no entran en fingerprints ni alteran artifacts.
