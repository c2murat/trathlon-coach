# Bloque 4B.5 — Strength Timing Eligibility and Safe Closure

Version publicable. Los enlaces a informe/ remiten a evidencia privada local no distribuida. Las frases sobre ausencia de commits/push describen la entrega original; el estado Git actual figura en integral-consolidation-status.md.

El bloque 4B queda cerrado en su alcance shadow. La duración efectiva sigue siendo legacy para todas las sesiones, incluidas las complete y temporalmente elegibles sintéticas. No se activa duración independiente ni se modifica el entrenamiento.

## Auditoría inicial y hallazgos

Se revisaron las entregas 4B.1–4B.4, matrices, contratos y estimador `strength_timing.py`, inputs/compilador, política, Strength Intent, builder, catálogo, pruebas, integración de preview y diseño original del motor. El estado y diff acumulados anteriores se conservan en [baseline](../informe/block4b5-baseline/manifest.json), [status previo](../informe/block4b5-baseline/status.txt) y [diff previo](../informe/block4b5-baseline/diff.txt). Se preserva todo el trabajo anterior.

| Aspecto | Comprobación / conclusión |
|---|---|
| Intención y prescripción | Strength Intent observa contenido y explicita la dependencia legacy; Workout Builder conserva recetas. La política shadow no modifica ninguno |
| Cálculo | Un solo agregador: `estimate_strength_timing`; el compilador 4B.2 deriva inputs al mismo snapshot. No se crea otro estimador |
| Prescrito frente a observado | TimingProvenance distingue explícito, configurable, revisado, derivado y medido. Complete no cambia `validation_state=not_evaluated` |
| Inmutabilidad e intervalos | FrozenModel, extra forbid, tuples; validación defensiva al entrar al estimador y al nuevo evaluador. `model_copy` puede saltar validadores: no se confía en objetos copiados |
| Cobertura | Complete exige componentes o ausencias explícitas; partial ofrece subtotal, no total; unavailable no proporciona comparación completa |
| Aditividad | Rutas/ocurrencias y ámbitos de ejecución, pausas, huecos y extremos disjuntos. Se rechazan duplicidades, descanso final fuera de ámbito y extremos duplicados |
| Identidad | Atleta, contexto, workout y definición vinculados al snapshot; un hash sirve para binding, nunca como fuente temporal |
| Circularidad | Selector sin presupuesto/legacy; aritmética solo con tiempos independientes. Reconciliación consulta legacy después. La independencia semántica de una fuente externa requiere revisión explícita |
| Dependencias | Solo librería estándar y Pydantic ya existente. Sin nuevas dependencias, modelos persistentes ni duplicación de diagnósticos del estimador |
| Integración activa | Preview conserva los sidecars anteriores. La elegibilidad nueva no tiene consumidores en `backend/app`; no existe selector de duración ni flag de activación |

No se identificó un defecto reproducible en el comportamiento previo que justificara modificarlo. Se detectó una ausencia concreta: no existía un evaluador de elegibilidad temporal con evidencia de integridad. Se añade únicamente ese contrato y evaluador. Durante las pruebas nuevas se corrigió un fixture que usaba como supuesto fingerprint incompatible el mismo valor que el contexto original; no era un fallo del motor.

## Archivos nuevos

- `backend/app/domains/planning/strength_timing_eligibility.py`: revisión interna vinculada, resultado de elegibilidad y evaluador shadow mínimo.
- `backend/tests/test_strength_timing_eligibility.py`: 22 casos nuevos, incluidos los parametrizados.
- `backend/scripts/audit_strength_timing_eligibility.py`: reutiliza el worker offline de 4B.4 en un directorio separado; genera nuevas evidencias sin sobrescribir las anteriores.
- Este informe y [resumen final 4B](block4b-final-summary.md).
- `informe/block4b5-*`: baseline, capturas de replay, cinco sidecars de elegibilidad, validación, logs y checks finales. Las copias de inputs dentro de `block4b5-replay` son evidencia local, no datos persistidos de atletas.

No se modifica ningún archivo preexistente de aplicación/dominio, esquema, API, frontend, BD, migración o test. No se refactorizan los auditores previos; se reutiliza su worker en procesos aislados.

## Contrato y límites de elegibilidad

`StrengthTimingReview` es una declaración de revisión explícita e inmutable con `review_id`, versión, fingerprint exacto del snapshot, hashes de las procedencias revisadas, versiones de política revisadas e independencia `verified/unverifiable/circular`. Su identidad de procedencia abarca fuente, identificador, versión, derivación y referencias de entrada. No equivale a autenticación criptográfica de las fuentes ni a calibración empírica. Una futura fuente de revisiones deberá tener control de confianza; este bloque no incorpora un endpoint, repositorio de revisiones ni revisiones para atletas reales.

`evaluate_strength_timing_eligibility(context, workout, snapshot, review=None)` recalcula mediante el estimador existente. No acepta un resultado complete suministrado por el llamador como prueba. El estimador vuelve a validar intervalos, ámbito, estructura, aditividad y binding. Para resultar elegible debe cumplirse todo lo siguiente:

1. Cobertura complete, sin componentes desconocidos ni diagnósticos.
2. Snapshot y workout correctamente vinculados; intervalos y ocurrencias válidos.
3. Revisión válida, con versión e identificador, vinculada al fingerprint del snapshot calculado.
4. Todas las procedencias agregadas revisadas explícitamente; incluye la declaración de la cadena de derivación, no solo el nombre de la fuente.
5. Versión del snapshot/política y versiones de políticas directas identificadas y revisadas.
6. Independencia verificada en esa revisión, sin dependencia circular demostrada.

La revisión es evidencia explícita de una comprobación externa, no una deducción de campos poblados. Sin ella, incluso un complete válido sigue no elegible por integridad no verificable. Un identificador de revisión no demuestra por sí solo exactitud predictiva. La elegibilidad aquí certifica requisitos temporales mínimos bajo la evidencia declarada, no calidad deportiva global ni duración efectiva.

`StrengthTimingEligibility` devuelve versión `strength-timing-eligibility-shadow-4b5-v1`, modo SHADOW_ONLY, resultado, estimación original, referencia de revisión y motivos ordenados sin duplicados. Conserva por separado `daily_availability`, `weekly_distribution`, `double_sessions` y `load_budget`, todos `not_evaluated`. `activation_authorized` solo admite el literal false. No contiene una duración seleccionada.

Se reutilizan literalmente los diagnósticos del estimador, incluidos `INVALID_TIMING_SNAPSHOT_CONTRACT`, `TIMING_SNAPSHOT_BINDING_MISMATCH` y `UNSUPPORTED_REPEAT_STRUCTURE`. Solo se añaden motivos propios de esta decisión: `COVERAGE_PARTIAL/UNAVAILABLE`, `UNKNOWN_COMPONENTS`, `INSUFFICIENT_PROVENANCE`, `INTEGRITY_REQUIREMENTS_UNVERIFIABLE` y `CIRCULAR_TIMING_DEPENDENCY`. No hay un segundo árbol de errores ni cambios en los reportes protegidos.

## Protección legacy y ausencia de activación

El nuevo módulo no se importa desde la aplicación ni desde el planificador, builder, Volume Intent o Strength Intent. Su único consumo es en pruebas y auditoría offline. Una prueba verifica esa ausencia de consumidores productivos. La API no expone ni acepta revisiones. No se introduce un selector, feature flag, ajuste de series/reps, reprogramación ni escritura de planes. Incluso cuando un fixture resulta elegible, el workout permanece idéntico y el resultado mantiene activación false y viabilidad no evaluada.

La estimación y elegibilidad no leen duración objetivo/legacy, disponibilidad, carga ni presupuesto semanal. Las pruebas cambian disponibilidad e historial/carga/segundos asignados conservando la receta, revinculan identidades y obtienen el mismo intervalo y elegibilidad. Los tests acumulados de política cubren además target_duration 24/40, target_load y weekly_budget. El evaluador no recibe SessionPrescription ni un presupuesto que pueda usar como dato temporal. La distinta identidad de un contexto exige nueva vinculación/revisión, pero no cambia la aritmética de una receta idéntica.

## Resultado de las 468 evaluaciones

| Dato | Resultado |
|---|---:|
| Evaluaciones | 468 |
| Complete / partial / unavailable | 0 / 468 / 0 |
| Temporalmente elegibles / no elegibles | 0 / 468 |
| Activaciones | 0 |
| Cambios de duración legacy | 0 |
| Workouts, artefactos y fingerprints idénticos | Cinco escenarios |
| Reportes temporales anteriores idénticos byte a byte | Cinco escenarios |

Cada una conserva `COVERAGE_PARTIAL`, `UNKNOWN_COMPONENTS` e `INTEGRITY_REQUIREMENTS_UNVERIFIABLE`: faltan componentes y no existe revisión independiente vinculada. No se inventan revisiones para mejorar elegibilidad. Los motivos no son excluyentes y no deben sumarse como número de sesiones. Las carencias son las auditadas en 4B.4: ejecución, alcance unilateral, transiciones y extremos. No hay cambios en las 468 reconciliaciones inconclusas ni nuevas incompatibilidades demostradas.

La evidencia detallada se encuentra en [validación](../informe/block4b5-validation.json) y `informe/block4b5-<escenario>-eligibility.json`. Se repiten current-null, current-target6, reference-target6, reference-race-cap y double-target6 sobre inputs congelados, sin leer la BD. Cada artefacto completo se compara byte a byte con 4B.4; adicionalmente se comparan los workouts serializados, fingerprints y los bytes completos del reporte temporal. Los nuevos diagnósticos están solo en ficheros separados.

## Escenarios sintéticos y validación

22 pruebas nuevas cubren: complete revisado elegible; complete sin revisión; independencia no verificable/circular; procedencia insuficiente; política no revisada; revisión con binding incorrecto o inválida; partial y unavailable; snapshot incompatible por definición/workout/contexto/atleta; intervalo inválido; duplicidad de pausas; procedencia ausente; repeat ambiguo; inmutabilidad y rechazo de activación true; determinismo; independencia de variables de planificación y ausencia de consumidores activos. Los tiempos/revisiones sintéticos no se incorporan a ningún plan.

La suite acumulada temporal pasa **147 pruebas, 1 warning** (39 de 4B.1 + 30 de 4B.2 + 34 de 4B.3 + 22 de 4B.4 + 22 de 4B.5). Estos números son casos de pytest, no afirmaciones de validación estadística. La entrega inicial 4B tiene otros **20 casos** en `test_strength_intent_shadow.py`, incluidos en la regresión backend: el inventario completo de fuerza 4B reúne **167 casos**, de los cuales 147 son temporales. No se suman de nuevo al total backend.

Comandos reproducibles desde raíz: `backend\.venv\Scripts\python.exe backend/scripts/audit_strength_timing_eligibility.py` y `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_strength_timing_eligibility.py backend/tests/test_strength_temporal_completion.py backend/tests/test_strength_timing_policy.py backend/tests/test_strength_timing_inputs.py backend/tests/test_strength_timing.py -q -p no:cacheprovider`. Regresión desde backend: `.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` con TC_AUTH_MODE y TC_ENVIRONMENT=development. Se utiliza ejecución fuera del sandbox para los temporales de pytest, tras el WinError 5 reproducido en 4B.4. No cambia producto ni usa datos reales.

## Limitaciones y continuación

No se valida empíricamente el tiempo total; `validation_state` sigue not_evaluated. Las revisiones son declaraciones de evidencia, cuya autenticidad/aplicabilidad no puede demostrar el contrato por sí solo. No existe revisión aceptada para las capturas reales. La concurrencia general y los repeats sin orden siguen sin total seguro. La política de descansos 4B.3 se conserva como prescripción normativa, no como observación ni validación científica de los descansos existentes.

No se exigen complete reales para cerrar esta infraestructura shadow. El enriquecimiento temporal y una eventual activación requieren trabajo posterior expresamente autorizado, con evidencia suficiente, evaluación de carga/capacidad e intención deportiva y fallback legacy. La hoja de ruta original y siguiente bloque recomendado se documentan en [resumen final](block4b-final-summary.md); no se implementan aquí.

Sin modificación de datos reales, aceptación de planes, staging, commit ni push.

## Cierre de validacion

**2034 pruebas backend pasan, 8 warnings, en 365.60 s; codigo 0.** Incluyen los 167 casos de fuerza (147 temporales y 20 de Strength Intent). Suite temporal dirigida: 147 passed, 1 warning; 22 casos nuevos. Compileall y git diff --check: codigo 0. Los 358 archivos preexistentes protegidos conservan sus hashes. No se detectan regresiones.

[Backend completo](../informe/block4b5-backend.log), [suite dirigida](../informe/block4b5-directed.log), [checks finales](../informe/block4b5-final-checks.json), [validacion de escenarios](../informe/block4b5-validation.json), [status final acumulado](../informe/block4b5-git-status.txt), [diff check](../informe/block4b5-diff-check.txt). El workspace mantiene sus cambios previos sin staging. No hay commit ni push.
