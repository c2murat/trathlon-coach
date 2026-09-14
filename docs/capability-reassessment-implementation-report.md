# 0.8G.2C.7 — Informe de implementación

Fecha de ejecución: **2026-09-14**. C.7 es una recomendación de volver a medir;
no propone un valor nuevo ni una dirección de cambio fisiológico.

| Apartado | Resultado |
|---|---|
| A. Auditoría inicial | Rama `sprint-0.8a-authentication`; HEAD local, tracking y remoto `d3ad388d62b1256383199ebbbfd1d7fc494cbbfa`. Árbol inicial: únicamente `backups/` e `informe/` sin seguimiento. Auditoría técnica en `capability-reassessment-audit.md`. |
| B. Inventario | Perfil versionado con FTP, threshold pace y CSS; fecha efectiva, origen, ID y versión. Referencias individuales con calidad, zonas derivadas y capability context existentes. La calidad individual no se atribuye al valor del perfil sin identidad de procedencia. |
| C. Arquitectura | Dominio puro independiente y assembler on-demand. Consume C.1, valida C.2 suministrado y reutiliza su interpretación sobre el subconjunto anclado. No incorpora C.3 ni modifica C.1–C.6. |
| D. Modelos | `CapabilityReassessmentContext`, `CapabilityReassessmentCandidate`, `CurrentCapabilityReference`, `ReassessmentEvidenceCounts`, `ReassessmentSummary`, `ReassessmentReferences` y `CapabilityTargetSnapshot`: modelos congelados, serializables y sin nuevo valor propuesto. Versión `0.8G.2C.7`. |
| E. Kinds | `CYCLING_FTP`, `RUNNING_THRESHOLD_PACE`, `SWIMMING_CSS`. |
| F. Estados | `INSUFFICIENT_EVIDENCE`: base insuficiente o bloqueada; `NO_REASSESSMENT_NEEDED`: evidencia suficiente sin señal repetida de revisión; `REASSESSMENT_CANDIDATE`: justifica volver a medir; `INCONSISTENT_EVIDENCE`: contradicción, overshoot o señal adversa; `REFERENCE_UNAVAILABLE`: referencia ausente, inválida o todavía no efectiva. |
| G. Mínimos | ≥3 comparaciones estructuradas HIGH/MEDIUM independientes, ≥2 recientes, fracción direccional C.2 ≥0.67; UNKNOWN y UNMATCHED no mayoritarios; sin parciales recientes. Una actividad reutilizada no demuestra repetición. Duración y métricas globales no sustituyen comparaciones estructuradas. |
| H. Ventana | Ventana factual `[cutoff−84 días, cutoff)`; recientes edad 1–27 dado que cutoff se excluye; background 28–83. La frontera factual de edad 84 no aporta a ninguna banda. Sin ponderación oculta. |
| I. Mapping | BIKE_TEMPO/THRESHOLD/INTERVAL → FTP; RUN_TEMPO/THRESHOLD/INTERVAL → threshold_pace; SWIM_THRESHOLD/INTERVAL → CSS. Además se exige snapshot explícito del primer work repetido comparado por C.1, mismos límites, unidad, repeticiones, sesión, fecha y referencia actual. No basta el nombre del tipo. |
| J. Cycling | Comparaciones de work laps por encima del target FTP pueden recomendar reevaluación; overshoot extremo sigue bloqueado por C.2. No se usa potencia media, normalizada ni máxima para estimar FTP. |
| K. Running | Comparaciones estructuradas más rápidas pueden apoyar revisión; menos s/km significa más rápido. No se infiere threshold desde ritmo global. |
| L. Swimming | Work laps comparables anclados a CSS; menos s/100 m significa más rápido. No se usa velocidad global, técnica o stroke rate. |
| M. Strength | Excluido; no hay kind ni inferencia de 1RM, carga, reps, RIR o RPE. |
| N. Antigüedad | Se informa `effective_from` y edad en días. No genera candidatura ni incrementa confianza por sí sola; no se inventa umbral de caducidad del perfil. |
| O. Referencia ausente | `REFERENCE_UNAVAILABLE`; sin fallback inferido desde actividades ni sustitución por otra referencia individual. |
| P. Confianza | HIGH requiere ≥5 comparaciones, ≥3 recientes, ≥4 HIGH tanto en sesión como en target y como máximo una MEDIUM; MEDIUM para candidatura que supera mínimos; LOW para contradicción; INSUFFICIENT cuando no hay base para recomendar revisión. Nunca expresa un valor fisiológico probable. |
| Q. Reasons | Enums ordenados: repetición above/faster, suficiencia reciente, referencia ausente, parciales, overshoot, contradicción, insuficiencia estructurada/reciente, target no anclado, mayorías UNKNOWN/UNMATCHED, falta de actividades independientes y ausencia de señal repetida. Se conservan también reasons de C.2. |
| R. C.6 | Independencia probada: NO_SUPPORTED_LADDER coexiste con C.7 insuficiente o candidato sin cambiar la ladder. C.6 sigue sin ladder productiva segura; C.7 no la crea. |
| S. Fingerprints | Regresión compara serialización completa del contexto y artifact de preview antes/después, incluidos workouts/fingerprints. Acceptance se ejecuta con C.7 sustituido por una función que falla si se invoca. |
| T. Determinismo | Orden estable de IDs, tipos y reasons; entradas invertidas producen JSON idéntico; round-trip validado; sin random ni reloj implícito. C.2 ajeno o desactualizado y IDs duplicados se rechazan. |
| U. Multiathlete | Coincidencia obligatoria entre request, C.1, C.2, referencia/capability y snapshots. Mismatch explícito; consulta de perfiles y sesiones filtrada por atleta. Pruebas con referencias distintas entre atletas. |
| V. Consultas | C.1 ≤3; C.2 0; C.7 0 con referencias/capability y snapshots suministrados. Carga autónoma: una consulta adicional conjunta de último perfil y provenance de workouts. Tests: 4 totales con 1 y 8 sesiones enlazadas; 2 totales sin sesiones. Sin N+1, relectura de laps ni streams. `no_autoflush` protege cambios pendientes del caller. |
| W. Protocolos | No se encontraron protocolos productivos FTP/threshold/CSS ni assessment workouts. No se inventaron identificadores ni sesiones de test. |
| X. Archivos | Seis archivos nuevos, enumerados debajo. Ningún archivo preexistente modificado. |
| Y. Focales | 71 tests C.7 pasan. Fixtures sintéticos solo en tests. Cubren candidatos, rechazos, anclaje exacto, direcciones, antigüedad, confianza, aislamiento, ventanas, determinismo y presupuesto SQL. |
| Z. C.1+C.2+C.7 | 100 tests pasan, incluidos seis escenarios con construcción real de evidencia C.1 desde laps sintéticos: tres deportes candidatos, inconsistencia, referencia ausente y cero evidencia. |
| AA. Regresiones | 241 tests pasan: C.1, C.2, C.3, C.6, C.5, C.4, athlete capability y adaptive targets. |
| AB. Planning completo | 535 tests pasan; 1 warning preexistente de Starlette/httpx. |
| AC. Backend completo | 1540 tests pasan, 8 warnings preexistentes, 165.21 s. `TC_AUTH_MODE=development` solo en el proceso; `.env` intacto. |
| AD. compileall | `python -m compileall -q app scripts tests` correcto. |
| AE. Auditor | 28 comprobaciones multiatleta; 0 incidencias, dentro de transacción real READ ONLY con rollback. |
| AF. Alembic | `current` y `heads`: `0026_session_activity_links (head)`. Sin migraciones. |
| AG. Git | Rama/HEAD intactos. `git diff --check` limpio; comprobación adicional de whitespace sobre archivos nuevos. Al ser todos nuevos sin staging, `git diff --stat` ordinario no los incluye. Ningún staging, commit ni push. |
| AH. Validación real | READ ONLY confirmado con `SHOW transaction_read_only`, cutoff 2026-09-14, inicio 2026-06-22, rollback. 3 atletas, 0 sesiones, 0 comparaciones ancladas y 0 candidatos; detalle debajo. |
| AI. Exclusiones | Confirmadas al final de este documento. |

## Limitación explícita de integración

C.1 no conserva la referencia del target original. Por eso no es seguro tratar
un rango o un session type como prueba suficiente del anclaje. La carga
autónoma de C.7 recupera ese snapshot junto al perfil en una consulta. Un caller
que proporciona capability y C.1 debe proporcionar también snapshots ya
disponibles para obtener candidaturas; si faltan, C.7 permanece conservador y
no añade consultas. Los targets adaptados y las sesiones anteriores a la fecha
efectiva de la referencia actual también se excluyen. No hay tolerancias,
interpolación, búsqueda de zonas próximas ni reconstrucción numérica.

## Validación real por atleta

| Atleta | FTP / threshold / CSS disponibles | Sesiones evaluables / comparaciones ancladas / candidatos | Estado de las tres capabilities | Confianza |
|---|---|---|---|---|
| `2b3fe99c-95a1-4351-b8ce-06bcb8833c0e` | No / No / No | 0 / 0 / 0 | REFERENCE_UNAVAILABLE | INSUFFICIENT |
| `3d74bef7-c14e-48fa-9517-8d530c142659` | No / No / No | 0 / 0 / 0 | REFERENCE_UNAVAILABLE | INSUFFICIENT |
| `542a8eeb-5fca-4e21-b14e-0f6d02d0f54b` | Sí / Sí / Sí | 0 / 0 / 0 | INSUFFICIENT_EVIDENCE | INSUFFICIENT |

Para todas las capabilities: `RECENT_EVIDENCE_INSUFFICIENT` y
`STRUCTURED_EVIDENCE_INSUFFICIENT`. Para las seis referencias ausentes se añade
`REFERENCE_MISSING`. Todos los conteos recent/background/contradicting/unknown/
unmatched son cero. Por atleta: C.1 = 1 SELECT, C.2 = 0, C.7 = 1 SELECT.
No se fabricaron datos reales para producir candidaturas.

## Archivos nuevos

- `backend/app/domains/capability/reassessment.py`
- `backend/app/application/capability_reassessment.py`
- `backend/scripts/validate_capability_reassessment_readonly.py`
- `backend/tests/test_capability_reassessment.py`
- `docs/capability-reassessment-audit.md`
- `docs/capability-reassessment-implementation-report.md`

## Exclusiones confirmadas

Sin cambios de FTP, threshold pace ni CSS; sin capability nueva calculada;
sin nueva profile version; sin adaptación de strength; sin cambios de Planning,
fingerprints, workouts, volumen, frecuencia ni scheduler; sin edición automática
de planes; sin frontend, endpoints nuevos, migraciones ni DB writes de C.7.
Las escrituras de fixtures y acceptance ocurren únicamente en bases SQLite de
test. `backups/`, `informe/`, temporales de pytest y
`frontend/tsconfig.app.tsbuildinfo` quedan fuera del cambio. Sin staging,
commit ni push. No se inició C.8.
