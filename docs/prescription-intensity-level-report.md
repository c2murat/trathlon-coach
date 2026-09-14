# 0.8G.2C.6 — Explicit Prescription Intensity Levels

Implementación conservadora conforme a la corrección arquitectónica confirmada
por el usuario. **El catálogo productivo no publica ninguna ladder.** No se ha
convertido una zona, un extremo de rango, un blend o una variante de duración en
un escalón de intensidad. C.6 devuelve `NO_SUPPORTED_LADDER` y C.5 conserva
`NO_SAFE_STEP` cuando no hay una escala real.

## A–J. Auditoría y arquitectura

| Apartado | Resultado |
|---|---|
| A. Auditoría inicial | Rama sprint-0.8a-authentication. HEAD local, origin y remoto real d992da05c06a5172074727649475d4689b2a33ea. Código tracked limpio al inicio; backups/informe excluidos. Auditoría previa en prescription-intensity-level-audit.md. |
| B. Primitive inventory | Zonas 0.7a.1, familias y roles del builder, SessionType/IntensityClass, patrones de plantilla, capability por duración/distancia, C.2B, resolución y rounding, C.4 y C.5. Las zonas existen pero no constituyen alternativas exactamente identificables dentro de la misma prescripción. |
| C. Arquitectura C.6 | Módulo puro prescription_intensity.py: contratos, catálogo conservador, identificación exacta y resolución de vecino inmediato. C.5 consume únicamente resolve_prescription_intensity_step como fuente de adyacencia. No hay registro mutable, proveedor artificial ni acceso a DB. |
| D. Prescription intensity model | PrescriptionIntensityLevel: deporte, tipo, target kind, id, índice, rol semántico, rango Decimal, unidad, fuente y versión, referencia capability con atleta/cutoff/fingerprints, bounds opcionales y versión C.6. PrescriptionIntensityLadder exige secuencia no vacía, índices consecutivos, ids/rangos únicos, identidad de prescripción y capability homogénea, y orden estricto de intensidad. |
| E. Ladder source-of-truth | La fuente productiva devuelve ausencia explícita: ningún conjunto de primitivas auditado satisface los requisitos. No se duplica la tabla de ratios ni la fórmula del builder. Un resultado numérico de C.5 solo puede tomar el rango de un nivel adyacente que entregue C.6. |
| F. Existing constants reused | No se reutilizan ratios fisiológicos para crear niveles. Se reutilizan identidades de deporte, unidad, kind, referencia y SessionType. Los números de los tests de identificación proceden del target real construido por el builder. |
| G. New constants introduced | **NONE fisiológicas**. Únicamente versión 0.8G.2C.6, estados, razones e índices estructurales para la adyacencia. |
| H. Level semantics | Orden por intensidad creciente: W crecientes, segundos por distancia decrecientes. Rol, tipo, unidad, referencia y contexto deben coincidir. No se identifica un nivel a partir de su proximidad a una zona. |
| I. Adjacent-step policy | Usa exclusivamente índice actual +1 o -1. No ordena candidatos arbitrarios, salta niveles, interpola o escoge el máximo. Antes de exponer un vecino exige bounds explícitos de prescripción y capability en ambos niveles. |
| J. Boundary policy | Si el vecino queda fuera del catálogo: BOUNDARY y MINIMUM_LEVEL/MAXIMUM_LEVEL, sin level_after. Un catálogo contractual con el único target existente tiene ambos límites y no puede producir un paso. El catálogo productivo ni siquiera publica ese singleton como ladder soportada. |

## K–R. Deportes, referencias e integración

| Apartado | Resultado |
|---|---|
| K. Running | RUN_PACE, seconds_per_km, threshold_pace. Menor pace representa mayor intensidad. Todos los SessionType de carrera carecen actualmente de ladder productiva. |
| L. Cycling | POWER, watts, FTP. Mayor potencia representa mayor intensidad. Sin inferir ni modificar FTP. La discrepancia [190,210] del builder frente a zona [180,210) con FTP 200 permanece explícita; no se aproxima. |
| M. Swimming | SWIM_PACE, seconds_per_100m, CSS. Sin inferencia de CSS ni niveles técnicos. SWIM_TECHNIQUE no tiene ladder de intensidad. C.5 conserva el guard de ambigüedad cuando hay distintos targets work principales/residuales. |
| N. Strength | UNSUPPORTED / STRENGTH_UNSUPPORTED en C.6; C.5 conserva NOT_APPLICABLE. No hay ladder de fuerza. |
| O. Capability interaction | La referencia incluye atleta, cutoff, fingerprint de contexto y fingerprint de performance/adaptive capability. Un cambio de referencia invalida el catálogo anterior; no se comparte el rango entre atletas. Planning sigue calculando los targets con sus fórmulas existentes. C.6 no modifica capability ni interpreta confidence. |
| P. Current-level resolution | identify_current_level compara ambos extremos y unidad exactamente. Diferencias de 0.001 en un input de prueba se rechazan: CURRENT_LEVEL_NOT_IDENTIFIED / EXACT_TARGET_MISMATCH. Unidad incompatible devuelve guard explícito. |
| Q. C.6→C.5 integration | NumericAdaptationResolution incorpora level_resolution opcional, con versión y diagnóstico C.6. NO_SUPPORTED_LADDER conserva NO_ORDERED_TARGET_LEVELS de C.5; mismatch/boundary tienen razones C.5 explícitas y NO_SAFE_STEP. ADJACENT_LEVEL reserva la ruta RESOLVED y copia exactamente el rango vecino; el catálogo actual nunca devuelve ese estado. |
| R. C.5→C.4 behavior | Sin reescritura de C.4. Conserva normalización, confidence/conflicts, exact current-range match y aplicación. Se añade transporte opcional de metadata y validación de que la transición pertenece al contexto base antes de incorporarla a Planning. Sin paso no se crea PlanningAdaptationInput. |

## S–Y. Trazabilidad y aislamiento

| Apartado | Resultado |
|---|---|
| S. Audit metadata | PrescriptionLevelTransition transporta versión, ladder id, ids/índices before/after, fuentes y versiones, fingerprint capability y contexto base. Se integra en PlanningAdaptationItem y metadata del target. La decisión de workout expone versión/ladder/before/after solo cuando existe transición. C.5 conserva el diagnóstico completo de C.6 en memoria. Sin actividades/laps completos. |
| T. Fingerprint | Metadata ausente no modifica hashes legacy C.4/C.5: prescription_level_transition=None se excluye de la representación canónica. Metadata presente se serializa canónicamente junto al resultado numérico. No se ha fabricado un APPLIED para probar un fingerprint efectivo: esa ruta permanece sin caso productivo mientras no exista una ladder real. |
| U. Determinism | Modelos frozen, tuplas ordenadas, Decimal, igualdad exacta, índices consecutivos y fingerprints canónicos. Sin random, timestamps de ejecución ni dependencia del orden de DB. No se alteró ROUND_HALF_UP del builder/C.2B. |
| V. Multiathlete | Ladder y referencia deben tener el mismo atleta/cutoff/contexto. El resolver rechaza otro atleta explícitamente, así como contexto, cutoff, versión o capability obsoletos. Se conserva el guard multiatleta C.3→C.5. |
| W. Query count/performance | C.6=0 queries; C.5=0; C.4=0. Las pruebas de generación C.5 instrumentadas con listener SQL pasan ahora incluyendo C.6. La validación real cuenta también construcción de catálogos dentro del tramo sin queries. C.1 mantiene ≤3, con 1 por atleta en la DB real vacía de sesiones. |
| X. Acceptance | Implementación sin cambios. Prueba específica bloquea C.6 y acceptance materializa correctamente el artifact almacenado. Regresiones legacy y C.4/C.5 conservadas. |
| Y. Active-plan isolation | No se modifican planes, sesiones, workouts o previews existentes. La aplicación de generación y las pruebas de aislamiento preexistentes pasan con la nueva cadena. No se añadieron escrituras a C.6 ni generación automática de previews. |

## Z. Archivos creados/modificados

Nuevos:

- backend/app/domains/planning/prescription_intensity.py
- backend/tests/test_prescription_intensity.py
- docs/prescription-intensity-level-audit.md
- docs/prescription-intensity-level-report.md

Modificados:

- backend/app/domains/planning/contracts.py — contrato de transición y canonicalización compatible.
- backend/app/domains/planning/models.py — metadata opcional en target adaptado.
- backend/app/domains/planning/numeric_adaptation.py — C.6 como fuente única de paso y diagnóstico.
- backend/app/domains/planning/planning_adaptation.py — transporte y guard de contexto base.
- backend/app/domains/planning/workout_builder.py — metadata opcional en decisiones.
- backend/scripts/validate_numeric_adaptation_readonly.py — métricas C.6 en auditoría real.

NumericRange continúa importable desde numeric_adaptation; su implementación se
comparte ahora con PrescriptionTargetRange de C.6, con la misma validación y
serialización de extremos positivos/finitos y unidad. No hay migración de datos.

## AA–AK. Tests y comprobaciones

La corrección del usuario sustituye los casos APPLIED obligatorios del prompt
original: no se construyeron ladders sintéticas ni niveles artificiales para
obtener resultados exitosos. Las pruebas de contrato representan el único nivel
observado de una prescripción real del builder, prueban exact match, mismatch,
duplicados inválidos y límites; no constituyen una escalera productiva alternativa.

Cobertura explícita del AJ corregido:

| Caso | Evidencia |
|---|---|
| NO_SUPPORTED_LADDER | Todos los SessionType productivos y composición C.6→C.5→C.4. |
| CURRENT_LEVEL_NOT_IDENTIFIED | Target distinto del único target observado; igualdad exacta y propagación a NO_SAFE_STEP/SKIPPED_NO_SAFE_STEP. |
| Boundary | El único target observado no tiene vecino inferior ni superior; el diagnóstico se conserva hasta el preview sin cambios. |
| Unsupported session type | RUN_UNKNOWN y SWIM_TECHNIQUE, sin catálogo habilitado. |
| Zero evidence | Cadena de generación C.5/C.6 y equivalencia íntegra de preview. |
| Solape de zona | Test explícito con outputs productivos: BIKE_THRESHOLD [190,210] frente a zona Umbral [180,210). C.6 no identifica nivel y C.5 no propone rango. |
| Determinismo | Repetición de resolución y round-trip canónico; conflictos independientes del orden. |
| Fingerprint no-action | Artifact idéntico para no ladder, mismatch y boundary; metadata ausente conserva hashes anteriores. |
| Acceptance | C.6 bloqueado por el test; acceptance solo materializa el artifact almacenado. |
| Multiathlete | Referencia/ladder de otro atleta rechazada; capability/contexto obsoletos también rechazados. |

Los casos mismatch y boundary prueban los contratos y la propagación de un
diagnóstico sin candidato; no registran ningún proveedor productivo ni fabrican
una ladder con alternativas. **RESOLVED/APPLIED siguen condicionados a una
futura política explícita de niveles productivos.**

| Apartado | Resultado |
|---|---|
| AA. Tests focales C.6 | 66 passed dentro de la ejecución focal combinada. Todos los tipos existentes, ausencia de ladder, referencia inválida, unidades/bounds, duplicados, índices, identidad exacta y límites, serialización, contexto obsoleto, multiatleta, transporte de ausencia y acceptance. |
| AB. C.5 regressions | 75 passed; combinación C.6+C.5: **141 passed**. |
| AC. Full adaptation chain | **210 passed**: C.1, C.2, C.3, C.6, C.5 y C.4. Se conservan cadenas RUN progresión/regresión, BIKE progresión, SWIM regresión y cero evidencia, verificando fallback y equivalencia del preview. Los guards previos pueden bloquear antes de C.6. |
| AD. Adaptive targets/capability | Pasan test_adaptive_targets, test_athlete_capability y test_workout_builder en la suite combinada de 126 tests. Sin cambios de sus fórmulas. |
| AE. Preview/fingerprint/acceptance | Pasan artifact, application, API y context contracts, junto con el grupo anterior: **126 passed**, un aviso Starlette/httpx. Cobertura adicional de ausencia de metadata y no recomputación en C.6. |
| AF. Planning completo | **464 passed**, un aviso Starlette/httpx, 27.96 s. Incluye planning*, training_planning*, execution*, numeric_adaptation, prescription_intensity, adaptive_targets, athlete_capability, workout_builder, season_structure, weekly_budget y session_planning. |
| AG. Backend completo | **1469 passed**, 8 avisos, 160.59 s. Sin fallos. Avisos de Starlette/httpx, serialización Pydantic en catálogo y match vacío en un test pytest de catálogo. |
| AH. compileall | `-m compileall -q app scripts tests`, exit 0. |
| AI. Auditor multiatleta | 28 comprobaciones, 0 incidencias. Ejecutado dentro de la transacción READ ONLY de validación real. |
| AJ. Alembic | current y heads coinciden: 0026_session_activity_links (head). |
| AK. Git status/diff | git diff --check limpio; índice sin cambios. HEAD conservado. Seis archivos tracked modificados y cuatro archivos nuevos del trabajo. Sin staging, commit o push. |

Tests ejecutados con `.venv/Scripts/python.exe -m pytest`, `-q` y
`-p no:cacheprovider`. Suites completas con `TC_AUTH_MODE=development` solo en
el proceso, sin modificar `.env`, y temporales nuevos dentro del proyecto. La
ejecución fuera del sandbox reutiliza la solución a los permisos de pytest ya
comprobada en C.5. No se eliminaron temporales existentes.

## AL. Validación real READ ONLY

Comando:

```powershell
.venv/Scripts/python.exe scripts/validate_numeric_adaptation_readonly.py --cutoff 2026-09-14
```

`SET TRANSACTION READ ONLY`, comprobación `transaction_read_only=on` y rollback
en finally. Ventana C.1 de 84 días: [2026-06-22, 2026-09-14).

| Atleta (prefijo UUID) | C.1 sesiones | C.2 señales agrupadas | C.3 propuestas | Intentos catálogo C.6 | Ladders | Niveles actuales/adyacentes | C.5 resultados | C.4 APPLIED |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2b3fe99c | 0 | 0 | 0 | 0 | 0 | 0 / 0 | 0 | 0 |
| 3d74bef7 | 0 | 0 | 0 | 0 | 0 | 0 / 0 | 0 | 0 |
| 542a8eeb | 0 | 0 | 0 | 8 | 0 | 0 / 0 | 0 | 0 |

Cada atleta conserva la señal global C.2 INSUFFICIENT_EVIDENCE y requiere una
consulta C.1. Los dos primeros no tienen objetivos futuros: no se fabricó un
contexto. Para el tercero se construyó Planning en memoria, sin guardar preview;
las ocho combinaciones de catálogo devolvieron NO_SUPPORTED_LADDER. Esos ocho
intentos no son ocho ladders ni ocho adaptaciones.

Totales reales: 3 atletas, 0 sesiones, 0 propuestas direccionales, 0 ladders,
0 niveles identificados, 0 vecinos, 0 resoluciones C.5, 0 conflictos y 0 APPLIED.
No hay before/after adaptados ni ejemplos reales RUN/BIKE/SWIM. No se crearon
fixtures, actividades, laps o planes en la DB real.

## AM. Exclusiones y cierre

Confirmado: sin constantes fisiológicas arbitrarias nuevas; sin cambios de FTP,
CSS o threshold persistido; sin adaptación de strength; sin cambios de volumen,
frecuencia, repeticiones o recovery; sin scheduler changes; sin modificación
automática de planes activos; sin aceptación automática; sin frontend, botones
o endpoints nuevos; sin tablas, columnas ni migraciones; sin staging, commit
o push. **No se inició C.7.**

backups/, informe/, temporales previos y frontend/tsconfig.app.tsbuildinfo
permanecen fuera del cambio entregado.
