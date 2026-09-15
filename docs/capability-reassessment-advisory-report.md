# 0.8G.2C.8 — Capability Reassessment Advisory API & UI

Implementación sobre `sprint-0.8a-authentication`, HEAD
`637ab36717cc0de9d9e0b2e29a0ca6b9d1985a35`. Auditoría iniciada el 2026-09-14;
validación final con datos reales el **2026-09-15**.

| Apartado | Resultado |
|---|---|
| A. Auditoría inicial | HEAD local, tracking y remoto coincidentes con el esperado (`git ls-remote`). Árbol inicial: solo `backups/` e `informe/` sin seguimiento. Revisados C.7, assembler/tests, familia performance-profile, referencias granulares, permisos, AppShell/AthleteContext, edición, cliente HTTP y formatos/estilos existentes. |
| B. API architecture | `GET /athlete/performance-profile/reassessment`, dentro del router existente. Invoca directamente `CapabilityReassessmentAssembler`; C.7 sigue siendo la autoridad. No endpoint de mutación nuevo. |
| C. API contract | `CapabilityReassessmentResponse`: atleta, cutoff, inicio de ventana, versión de API C.8 y algoritmo C.7, candidates y summary. Cada elemento incluye kind/status/confidence/reference/evidence/reasons. No supporting IDs, IDs de perfil, trazas C.2 ni payload de workouts. |
| D. Cutoff | Parámetro opcional `as_of_date`, validado como fecha; rango 2000-01-01 hasta el día actual del atleta. Valor por defecto desde `utc_now()` y zona horaria del atleta. C.7 recibe fecha explícita y mantiene exclusión del cutoff y futuro. Fechas inválidas/futuras: 422. |
| E. Permissions | Lectura mediante `READ_ATHLETE_DATA`: owner, athlete, editor, coach y viewer según matriz existente. CTA mediante `CREATE_PERFORMANCE_PROFILE`: mismos roles salvo viewer. POST de versiones conserva su autorización original. No roles ni permisos nuevos. |
| F. Multiathlete isolation | Selección por header central `X-TriCoach-Athlete-Id`, membership activa y athlete scope existente. La UI valida el athlete ID recibido, oculta de inmediato el estado de otro atleta e ignora respuestas tardías. AppShell conserva su remount por atleta; el cliente conserva cancelación/generaciones. |
| G. Status presentation | Revisión recomendada / Sin revisión necesaria / Aún no hay evidencia suficiente / Evidencia no concluyente / Referencia no disponible. Badges textuales neutrales; insuficiencia no se muestra como error ni en rojo. |
| H. Reason-code presentation | Mapper español para todos los reasons actuales C.7; fallback legible sin mostrar códigos desconocidos. Traducción de meaning, sin repetir thresholds ni inferencia. |
| I. Confidence presentation | Alta, Media, Baja, Insuficiente, identificadas expresamente como confianza en la recomendación de revisión. No score de fitness. |
| J. FTP presentation | Valor actual en W, con `formatReferenceValue` existente. Sin FTP propuesto. |
| K. Running threshold presentation | Ritmo actual en min/km, formateador existente; p. ej. 250 s/km → 4:10 min/km. |
| L. CSS presentation | Ritmo actual en min/100 m; p. ej. 110 s/100 m → 1:50 min/100 m. |
| M. Reference metadata | Vigente desde, origen y calidad cuando disponibles. Labels existentes; calidad null se presenta como no especificada y no se inventa. |
| N. Evidence metrics | Comparaciones estructuradas evaluables, recientes, anteriores y contradictorias, tal como vienen de C.7. Sin score, porcentajes calculados ni ponderación frontend. |
| O. CTA behavior | Revisar referencia abre el editor manual ya existente, con foco en el editor. No guarda ni propone valores. Ausente sin permiso. Tras un guardado manual autorizado se vuelve a solicitar el advisory, respetando su cutoff. |
| P. Frontend integration | Sección Revisión de referencias en Perfil de rendimiento, hasta tres tarjetas responsivas. Sin nueva navegación. Usa cliente, formatos y estilos del producto. |
| Q. Loading/empty/error states | Loading independiente; respuesta vacía válida; referencias ausentes y evidencia insuficiente no son errores. Mensajes diferenciados para 401/403/404/red/5xx y reintento. Sin stack traces ni datos antiguos de otro atleta. |
| R. Accessibility | Jerarquía h2/h3, sección nombrada, dl/dt/dd, badges con texto, loading role=status, errores role=alert, botones nativos con nombre específico. Test de Enter que abre el editor y verifica foco. Estilos de foco existentes y grid adaptable. |
| S. Read-only guarantees | Endpoint sin escrituras, flush, commit ni creación de versiones. Tests interceptan SQL y fallan ante cualquier instrucción distinta de SELECT o commit. Validación real usa `SET TRANSACTION READ ONLY`, comprueba `SHOW transaction_read_only` y termina con rollback. |
| T. Planning isolation | Regresión compara artifact completo antes y después de consultar C.8. No cambios en PlanningContext, generación/acceptance ni fingerprints. |
| U. C.6 isolation | No consumo ni presentación de ladders, NO_SUPPORTED_LADDER o NO_SAFE_STEP. C.1–C.7 permanecen sin modificaciones. |
| V. Query count/performance | C.7 conserva presupuesto: C.1 ≤3 + 1 consulta conjunta perfil/provenance. Con autorización de membership: 3 SELECT sin sesiones, 5 con sesiones enlazadas, probado con 1 y 7 sesiones. Autenticación por cookie añade su SELECT existente. No N+1 ni relectura adicional de laps/streams. `Cache-Control: private, no-store`; sin caché persistente nueva. |
| W. Archivos | Lista exacta debajo. Cuatro archivos preexistentes modificados; el resto son nuevos. |
| X. Backend focal tests | 20 tests API C.8 pasan: estados, serialización, metadata, permisos, membership revocada, aislamiento, cutoff, timezone, consulta constante y read-only. |
| Y. Frontend focal tests | 17 tests pasan: cinco estados, unidades, reasons, confidence, CTA, teclado/foco, cambio de atleta y respuestas tardías, empty, mismatch, errores y cliente HTTP central. |
| Z. C.7 regressions | 71 tests C.7 pasan dentro de la ejecución conjunta C.7+C.8 inicial (87 tests) y regresiones ampliadas. C.7 no se modifica. |
| AA. Multiathlete regressions | Incluidas en conjunto de 740 tests: matriz de permisos y suites multiatleta existentes. Además tests C.8 de dos atletas autorizados con FTP distintos, cross-athlete rechazado y membership revocada. |
| AB. Performance profile regressions | Suites performance references, zones y permisos incluidas en los 740 tests correctos; no se modifica el flujo de persistencia existente. |
| AC. Planning regressions | Suites Planning, preview, acceptance, ejecución, numeric adaptation, prescription intensity, capability, adaptive targets y workout builder incluidas en los 740 tests correctos. |
| AD. Frontend completo/build | 324 tests en 43 archivos pasan. TypeScript `tsc -p tsconfig.app.json --noEmit` correcto y build Vite correcto (104 módulos). Se evita `tsc -b` para no tocar el tsbuildinfo excluido. |
| AE. Backend completo | 1560 tests pasan, 8 warnings preexistentes, 179.27 s. `TC_AUTH_MODE=development` solo en el proceso y temporales aislados; `.env` intacto. |
| AF. compileall | `python -m compileall -q app scripts tests` correcto. |
| AG. Auditor multiatleta | 28 comprobaciones, 0 incidencias dentro de la validación real READ ONLY. |
| AH. Alembic | `current` y `heads`: `0026_session_activity_links (head)`. Sin migraciones. |
| AI. Git status/diff | Rama y HEAD preservados; `git diff --check` correcto. Sin staging/commit/push. Los archivos nuevos sin seguimiento no aparecen en el diff stat ordinario. |
| AJ. Validación real | Tres atletas, HTTP 200 para los tres, 0 sesiones y 0 candidatos. Seis referencias ausentes; tres presentes con evidencia insuficiente. Detalle y alcance abajo. |
| AK. Exclusiones | Confirmadas al final. |

## Alcance de la validación real

Se ejecutó el **router real de la aplicación por HTTP ASGI mediante TestClient**,
el assembler C.7 real y la DB real, con cutoff **2026-09-15**. Para evitar crear
sesiones de login o modificar la DB, el harness suministra identidades de
usuarios obtenidas de memberships activas existentes. La selección de atleta,
autorización, consulta y serialización no se sustituyen. Esto no equivale a una
prueba de login por navegador; la autenticación de sesión/CSRF conserva su
implementación y regresiones existentes.

| Atleta | HTTP | Candidates de revisión | FTP / threshold / CSS presentes | Estados de las tres capabilities | Confidence | SELECT |
|---|---|---|---|---|---|---|
| 2b3fe99c-95a1-4351-b8ce-06bcb8833c0e | 200 | 0 | No / No / No | REFERENCE_UNAVAILABLE | INSUFFICIENT | 3 |
| 3d74bef7-c14e-48fa-9517-8d530c142659 | 200 | 0 | No / No / No | REFERENCE_UNAVAILABLE | INSUFFICIENT | 3 |
| 542a8eeb-5fca-4e21-b14e-0f6d02d0f54b | 200 | 0 | Sí / Sí / Sí | INSUFFICIENT_EVIDENCE | INSUFFICIENT | 3 |

`transaction_read_only = on`; únicamente SELECT en las peticiones; rollback
final confirmado. No se crearon fixtures en la DB real.

La comprobación visual en navegador integrado no pudo realizarse: el backend
`iab` no está disponible. Se comprobó su disponibilidad siguiendo la skill de
navegador y su procedimiento de diagnóstico. La presentación, estados,
aislamiento y teclado se validaron mediante tests React/jsdom; no se afirma
una inspección visual en navegador que no se haya realizado.

## Archivos

Modificados:

- `backend/app/api/v1/routes/performance_profiles.py`
- `frontend/src/services/apiClient.ts`
- `frontend/src/app/AppShell.tsx`
- `frontend/src/features/profile/PerformanceProfilePage.tsx`

Nuevos:

- `backend/app/api/v1/schemas/capability_reassessment.py`
- `backend/scripts/validate_reassessment_api_readonly.py`
- `backend/tests/test_capability_reassessment_api.py`
- `frontend/src/features/profile/reassessmentTypes.ts`
- `frontend/src/features/profile/reassessmentPresentation.ts`
- `frontend/src/features/profile/CapabilityReassessmentSection.tsx`
- `frontend/src/features/profile/CapabilityReassessmentSection.test.tsx`
- `frontend/src/features/profile/capabilityReassessment.css`
- `docs/capability-reassessment-advisory-report.md`

## Exclusiones confirmadas

Sin cambios de FTP, threshold pace ni CSS; sin capability estimada; sin nueva
profile version creada por C.8; sin cambios de Planning, fingerprints, workouts,
volumen, frecuencia ni scheduler; sin edición automática de planes ni adaptación
automática; sin migraciones ni DB writes del advisory. El CTA solamente abre la
edición manual existente. Las escrituras de los tests se limitan a sus fixtures
SQLite. No se modifican `backups/`, `informe/`, los temporales preexistentes ni
`frontend/tsconfig.app.tsbuildinfo`. Sin staging, commit ni push. No se inició C.9.
