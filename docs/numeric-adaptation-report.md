# TriCoach AI — 0.8G.2C.5: informe de implementación

Implementada la resolución conservadora e integrada en la generación normal de
previews. **No se ha encontrado un nivel adyacente autorizado dentro de la misma
prescripción. Esta versión no emite `RESOLVED`.** Para propuestas direccionales
compatibles devuelve `NO_SAFE_STEP`, o un guard explícito si el target es ambiguo
o inválido. No se han construido magnitudes para conseguir `APPLIED`.

## A–G. Auditoría, arquitectura y origen del paso

| Apartado | Resultado |
|---|---|
| A. Auditoría inicial | Rama `sprint-0.8a-authentication`; HEAD local, origin y remoto real `444f602a5cd03ee14ff0fb5af196be2db81037b0`. Remoto verificado mediante `git ls-remote`. Árbol inicialmente con seis archivos modificados y borradores numeric_adaptation/test_numeric_adaptation sin seguimiento. No se descartó trabajo ajeno. |
| B. Arquitectura C.5 | Dominio puro `resolve_numeric_adaptations`, después del builder base y antes de C.4. C.1/C.2/C.3 conservan su responsabilidad. La auditoría se documentó antes de revisar el borrador del resolver en `numeric-adaptation-audit.md`. |
| C. Numeric adaptation model | `NumericAdaptationResolution` y contexto inmutables: atleta, cutoff, sport, session type, kind, unidad, propuesta de origen, dirección, confianza, rangos Decimal, estado, razones, guards propios/de origen y versiones. Estados RESOLVED, NO_SAFE_STEP, NOT_APPLICABLE, GUARDED, UNSUPPORTED y CONFLICT. |
| D. Step source-of-truth | El target actual procede de los drafts que Planning acaba de construir con capability/adaptive targets. Se comprueba fingerprint de contexto y correspondencia draft/prescripción. Rangos históricos de C.3 se consideran únicamente para detectar conflictos; nunca son el target base. |
| E. Existing target primitives found | Rangos de ratios por familia/rol, zonas sin mapping ejecutable, dimensiones capability de duración/distancia, interpolación, blends, límites, precisión numérica y patrones de plantilla. Ninguno es una escala de alternativas para la misma prescripción. |
| F. Adjacent-level policy | No se introduce `LEVELS` enlazando easy/tempo/threshold/interval. Ordenar esas familias por intensidad no autoriza aplicar otra familia manteniendo tipo, estructura y bounds de la sesión original. El requisito condicional de avanzar exactamente un nivel no es ejecutable con las primitivas actuales. |
| G. No-safe-step semantics | `NO_ORDERED_TARGET_LEVELS`, `proposed_range=None`; C.4 informa `SKIPPED_NO_SAFE_STEP` y no genera input efectivo. El estado RESOLVED y su transporte versionado quedan reservados; no hay proveedor ficticio de candidatos. |

## H–P. Disciplinas, guards e integración

| Apartado | Resultado |
|---|---|
| H. Running | Solo RUN_PACE / seconds_per_km. INCREASE exige FASTER_PACE; DECREASE exige SLOWER_PACE. La validación del contrato numérico exige movimiento estricto de ambos extremos. Sin escala compatible, no cambia el pace. |
| I. Cycling | Solo POWER / watts y HIGHER_POWER/LOWER_POWER coherentes. FTP y capacidades no se convierten en destinos de progresión. |
| J. Swimming | Solo SWIM_PACE / seconds_per_100m. Las sesiones con varios rangos work diferentes son ambiguas y quedan guardadas; no se elige arbitrariamente el bloque principal o el residual. No se adapta técnica ni CSS. |
| K. Strength | NOT_APPLICABLE y STRENGTH_UNSUPPORTED para sus propuestas normales o direccionales. Sin cambios de kg, reps, series, RIR, RPE o ejercicios. |
| L. Confidence gate | LOW/INSUFFICIENT bloquean; MEDIUM/HIGH permiten examinar el target. Se copia exactamente la confianza de C.3. Nunca determina una magnitud. |
| M. Safety guards | Atleta y cutoff de C.3/contexto/capability; contexto base sin adaptación previa; draft del mismo contexto; tipo y deporte compatibles; kind/unidad/métrica; dirección coherente; rangos positivos, finitos y ordenados; ambigüedad y guards de origen. No hay candidato y por ello no se afirma haber validado bounds/adyacencia de un paso inexistente. |
| N. Conflict policy | Agrupación por sport/session type/target kind en contexto de atleta único. Firma canónica incluye intención, dirección, confianza, guards y campos numéricos legacy. Todas las variantes incompatibles quedan en CONFLICT; los duplicados equivalentes se colapsan. Orden de entrada y duplicados no afectan el resultado. |
| O. Determinism | Orden explícito por clave y firma, Decimal y serialización canónica; sin reloj ni aleatoriedad. C.5 no hace cálculos de target; el ROUND_HALF_UP existente del builder/C.2B permanece intacto. |
| P. C.3→C.5→C.4 | La aplicación genera drafts base, llama C.5 y normaliza el resultado mediante C.4. Solo RESOLVED puede proyectarse a PlanningAdaptationInput. C.4 no calcula steps. C.3 sigue versionado 0.8G.2C.3; versión C.5 explícita 0.8G.2C.5. |

## Q–V. Fingerprints, artifacts y aislamiento

| Apartado | Resultado |
|---|---|
| Q. Planning/fingerprint behavior | Sin input efectivo se reutiliza el contexto y no se recalcula Planning. Previews y workouts coinciden íntegramente con baseline. La versión numérica opcional nula se excluye de la representación canónica para preservar hashes C.4 anteriores. Una versión presente participa en el hash. |
| R. Artifact auditability | El transporte C.4 admite versión C.5 en metadata de target y decisión de workout, junto a propuesta/dirección/confianza/before/after. Las pruebas de transporte usan rangos sintéticos explícitos: no son evidencia de resolución fisiológica C.5. No existen artifacts reales RESOLVED en esta política. Intentos fallidos no añaden evidencia ni datos de activities/laps al artifact. |
| S. Acceptance behavior | Sin modificaciones de la implementación de acceptance. Pruebas con artifact legacy y C.4, con/sin versión numérica: acceptance materializa lo almacenado aunque los puntos de entrada de generación estén bloqueados por el test. |
| T. Active-plan isolation | Generación crea únicamente el preview pendiente. Prueba de aplicación con plan activo: plan conservado y ninguna PlannedTrainingSession/StructuredWorkout materializada por generación. |
| U. Multiathlete | Mismatch de atleta rechazado. Scope/versiones del resultado validados. Auditor real sin incidencias. |
| V. Query count | C.5 y su normalización C.4: 0 queries, comprobado con listener SQL en pruebas de aplicación. C.2/C.3: puro dominio. C.1 mantiene hasta 3 consultas constantes y en la validación real ejecutó 1 por atleta por ausencia de sesiones. No hay lecturas nuevas de activities/laps/streams en C.5. |

## W. Archivos creados/modificados

| Archivo | Cambio |
|---|---|
| `backend/app/domains/planning/numeric_adaptation.py` | Revisión del borrador existente: modelo, guards, resolución conservadora, proyección. |
| `backend/app/application/planning_preview.py` | Composición base→C.5→C.4 durante generación. |
| `backend/app/domains/planning/contracts.py` | Versión numérica opcional y equivalencia canónica legacy. |
| `backend/app/domains/planning/models.py` | Versión opcional en metadata de target adaptado. |
| `backend/app/domains/planning/planning_adaptation.py` | Normalización de resultados C.5 y transporte de versión. |
| `backend/app/domains/planning/workout_builder.py` | Versión en decisión de adaptación del workout. |
| `backend/tests/test_numeric_adaptation.py` | Pruebas C.5, cadena completa, aplicación, hashes, acceptance y guards exactos. |
| `backend/tests/test_planning_adaptation.py` | Regresión de acceptance con C.5 bloqueado. |
| `backend/scripts/validate_numeric_adaptation_readonly.py` | Validación reproducible, cutoff obligatorio, READ ONLY y rollback. |
| `docs/numeric-adaptation-audit.md` | Auditoría y decisión anterior a revisar arquitectura. |
| `docs/numeric-adaptation-report.md` | Este informe. |

## X–AG. Validaciones

Comandos ejecutados desde backend con `.venv/Scripts/python.exe`. Tests con
`-q -p no:cacheprovider`. Suite global y Planning con
`TC_AUTH_MODE=development` solo en el proceso; `.env` no modificado.

| Apartado | Resultado |
|---|---|
| X. Tests focales | 75 casos C.5; incluidos límites de familias, ambas direcciones, capability real del builder, targets inválidos, confianza, conflictos, versiones, generación y acceptance. Los tres casos de mismatch exacto también se ejecutaron en las suites finales de cadena y Planning. |
| Y. C.1+C.2+C.3+C.5+C.4 | **144 passed**. Incluye pruebas que calculan C.1 desde prescripción/laps de prueba antes de C.2/C.3, y equivalencia de preview para RUN progresión/regresión, BIKE progresión, SWIM regresión y cero evidencia. |
| Z. Adaptive target/capability regressions | **81 passed**: test_adaptive_targets, test_athlete_capability y test_workout_builder. |
| AA. Preview/fingerprint/acceptance | **45 passed**, un aviso de deprecación Starlette/httpx: artifact, application, API y contratos. Cobertura adicional en los focales C.5. |
| AB. Planning completo | **398 passed**, un aviso, 22.45 s. Selección de todos los test_planning*, training_planning*, execution*, numeric_adaptation, adaptive_targets, athlete_capability, workout_builder, season_structure, weekly_budget y session_planning. |
| AC. Backend completo | **1400 passed**, 8 avisos, 147.43 s. Después se añadieron tres casos de mismatch exacto y se reforzó el cálculo C.1 de cuatro casos; todos pasaron en la suite final de Planning y la cadena (sin cambios adicionales de código productivo). El primer intento global en sandbox falló por permisos del temporal; la ejecución autorizada con un directorio nuevo pasó. |
| AD. compileall | `-m compileall -q app scripts tests`: exit 0. |
| AE. Auditor multiatleta | 0 incidencias en los 28 checks de integridad, dentro de la misma validación READ ONLY. |
| AF. Alembic | current = heads = `0026_session_activity_links (head)`. Sin migraciones. |
| AG. Git status/diff | `git diff --check` limpio. Seis archivos tracked modificados; cinco archivos del trabajo sin seguimiento. Índice vacío. backups/informe y temporales fuera del cambio. HEAD conservado. |

Los avisos globales proceden de Starlette/httpx, serialización Pydantic de tests
de catálogo y un match vacío en pytest; no hubo fallos en la ejecución autorizada.

## AH. Validación real READ ONLY

Comando:

```powershell
.venv/Scripts/python.exe scripts/validate_numeric_adaptation_readonly.py --cutoff 2026-09-13
```

Se ejecutó `SET TRANSACTION READ ONLY`, se comprobó `transaction_read_only=on`
y se efectuó rollback en `finally`. Ventana C.1: **2026-06-21 inclusive a
2026-09-13 exclusive** (84 días).

| Atleta (prefijo UUID) | C.1 sesiones | Queries C.1 | C.2 señales agrupadas | C.3 direccionales | C.5 resultados | C.4 APPLIED |
|---|---:|---:|---:|---:|---:|---:|
| 2b3fe99c | 0 | 1 | 0 | 0 | 0 | 0 |
| 3d74bef7 | 0 | 1 | 0 | 0 | 0 | 0 |
| 542a8eeb | 0 | 1 | 0 | 0 | 0 | 0 |

Cada atleta tiene la señal global C.2 `INSUFFICIENT_EVIDENCE`; esta señal global
no se cuenta como señal agrupada ni como propuesta direccional. Totales:
RESOLVED=0, NO_SAFE_STEP=0, NOT_APPLICABLE=0, GUARDED=0, UNSUPPORTED=0,
CONFLICT=0. Ningún target before/after adaptado y ningún ejemplo real
RUN/BIKE/SWIM disponible. No se inventaron ejemplos ni fixtures en la DB real.

Dos atletas carecen de objetivos futuros: no se fabricó un PlanningContext.
Para el tercero se construyó Planning en memoria y se ejecutaron C.5/C.4 con
propuestas vacías, sin guardar preview. No es una demostración real de APPLIED.

## AI. Exclusiones y cierre

Confirmado: sin constantes fisiológicas arbitrarias; sin cambios de FTP, CSS o
threshold persistido; sin cambios de volumen, frecuencia o repeticiones; sin
scheduler changes; sin modificación automática de planes activos; sin aceptación
automática; sin frontend; sin endpoints nuevos; sin tablas, columnas ni
migraciones; sin staging; sin commit; sin push. **No se inició C.6.**

`backups/`, `informe/`, `.tmp_pytest_*` y
`frontend/tsconfig.app.tsbuildinfo` quedan fuera del trabajo entregado.
