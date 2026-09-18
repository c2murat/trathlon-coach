# D.2 Q — Cumplimiento de lo planificado tras sincronización

Actualización 18/09/2026: Q aceptado funcionalmente tras dos sincronizaciones
reales correctas, refresh automático, matching conservador e idempotencia.
Se importó una actividad (1.432 → 1.433); segunda sync sin nuevas actividades.
Links: 0 → 0 → 0. La creación de un vínculo real y la adherencia estructurada
real siguen pendientes de observar naturalmente; no se fabrica evidencia.
El cierre posterior de D.2 y la corrección horaria se documentan en
[athlete-daily-overview-report.md](athlete-daily-overview-report.md).
La validación de solo lectura descrita más abajo corresponde a la fase previa.

Implementado el apartado Q recibido, sobre Inicio existente. No supone el cierre
del conjunto completo D.2 ni un rediseño de Inicio. Base verificada:
`sprint-0.8a-authentication`, `7758097d647d1697e2c4609b4d6573a2f9fc8a4d`.
Validaciones realizadas el 16–17 de septiembre de 2026. Sin staging, commit ni push.

## Q1. Auditoría e integración post-sync

La [auditoría](post-sync-execution-audit.md) identifica que la importación ya
actualizaba carga, agregados y Training Status, pero no llamaba al enlazador de
sesiones. Se añade esa llamada al final de `StravaPostSyncProcessingApplication`,
antes del commit de procesamiento y del estado succeeded.

Se seleccionan sesiones del mismo atleta en las fechas locales ±1 día de las
actividades nuevas/modificadas. Se llama a `PlannedSessionActivityMatching.auto_match`
sin cambiar sus reglas, umbrales, locks ni provenance. Toda la importación por
páginas ha terminado antes de resolver candidatos, por lo que se consideran las
actividades persistidas juntas y no solo la primera que llegó.

Una excepción de matching deja el job parcialmente completado con
`post_processing_activity_matching_failed`; se conservan las actividades
importadas y puede reintentarse el procesamiento. No se anuncia éxito antes de
que ese paso haya terminado. Casos ambiguos son resultados válidos sin vínculo,
no errores ni motivos para forzar una asociación.

Una importación sin actividades afectadas conserva su comportamiento de no-op.
No se ejecutó backfill de vínculos históricos ni una sincronización real durante
esta implementación.

## Q2–Q3. Ejecución factual y ausencia de vínculo

Nuevo GET `/dashboard/execution-overview`, protegido por `get_current_athlete`,
con fecha opcional explícita y `Cache-Control: private, no-store`. Rechaza fechas
futuras, anteriores a 2000 o inválidas.

`ExecutionOverviewApplication` invoca el assembler C.1 y reutiliza directamente
`PrescribedCompletedEvidenceContext`, `SessionExecutionEvidence`,
`TargetAdherenceEvidence` y `LinkProvenance`. No cambia C.1 ni crea otro algoritmo.

| Estado C.1 | Texto visible |
| --- | --- |
| COMPLETED | Completado |
| PARTIAL | Realizado parcialmente |
| OVER_DURATION | Duración superior a la prevista |
| UNKNOWN | No hay datos suficientes para valorar el cumplimiento |
| UNMATCHED | No se ha encontrado una actividad vinculada |

La explicación de UNMATCHED indica expresamente que la ausencia de vínculo no
permite saber si la sesión se realizó. Nunca se traduce a «No cumplido».

La fecha del overview es inclusiva y se traduce al cutoff exclusivo del día
siguiente aceptado por C.1. Así un último entrenamiento vinculado de hoy puede
evaluarse mediante C.1, sin esperar a mañana. La lista de sesiones recientes
solo usa fechas anteriores a la consulta: no presenta como pasadas sesiones
todavía pendientes de hoy. Si una sesión vinculada queda fuera del histórico
C.1 de 84 días, se muestra la relación factual y se explica que no hay evaluación
disponible; no se fabrica un resultado.

## Q4. Comparación planificado/realizado

Se muestran deporte, tipo/título traducido, fecha planificada sin inventar hora,
duración, distancia disponible y workout estructurado. Para las actividades
vinculadas: nombre y enlace a detalle, fecha y hora persistidas con su timezone,
deporte, duración, distancia y pulso/potencia medios si existen.

Los totales realizados provienen de C.1, incluida su agregación de múltiples
actividades compatibles y deduplicación. También se conservan y presentan las
actividades individuales. Una incompatibilidad de deporte se señala como
limitación, sin sustituir el resultado del dominio por otro algoritmo.

## Q5. Objetivos estructurados

Se reutiliza `WorkoutDetail` para visualizar los targets planificados. La
presentación utiliza exclusivamente la fracción de aciertos, repeticiones
comparadas/planificadas y confianza ya calculadas por C.1:

- Todas las repeticiones comparadas y fracción exactamente 1: «Objetivos comprobados cumplidos».
- Algún acierto con cobertura o aciertos incompletos: «Objetivos parcialmente cumplidos».
- Fracción cero con evidencia utilizable: objetivos comprobados fuera del rango.
- Sin comparación o confianza baja/insuficiente: no hay datos suficientes para comprobar intervalos.

Se muestra «Repeticiones comparadas: X de Y», usando los enteros existentes.
No se transforma una fracción redondeada en un número supuesto de bloques dentro
del rango. Las métricas medias globales son información descriptiva; nunca
reconstruyen intervalos. No existe un score único de cumplimiento.

## Q6. Inicio

Nuevo bloque compacto «Último entrenamiento» y «Sesiones recientes», después
del resumen analítico existente. El último entrenamiento muestra la actividad
más reciente y sus sesiones relacionadas. Si no hay vínculo, lo dice sin juzgar
el entrenamiento. La lista contiene como máximo cinco sesiones pasadas, con
estado visible y comparación desplegable. Se conservan loading, error separado
de UNMATCHED, estados vacíos, enlaces, headings y controles nativos de teclado.

## Q7. Calendario

Auditado y diferido, conforme a la opción permitida por Q7. La vista anual usa
otro contrato sin evidencia y abarca fechas fuera del histórico C.1. Incorporar
badges a todo el año necesita un contrato por rango y validaciones propias.
No se añaden requests por cada celda ni etiquetas calculadas en frontend.

## Q8. Actualización después de sincronizar

Inicio escucha el evento existente `tricoach:activity-sync-completed`, emitido
por `ActivitySyncButton` tras succeeded, y vuelve a consultar el overview.
Se pasa el atleta activo al botón y al bloque. Se ignoran eventos de otros
atletas, se invalida el contenido al cambiar de atleta y se descartan respuestas
tardías mediante una generación de petición. No se pide recalcular manualmente.

El GET solo lee datos; no guarda copias del estado ni crea vínculos. La única
nueva escritura funcional es el vínculo automático del servicio existente,
dentro de la transacción autorizada de procesamiento post-sync.

## Q9. Vínculos manuales y aislamiento

Los vínculos manuales válidos se mantienen, incluidos ID, fecha, fuente y versión.
Una actualización posterior de la actividad o una nueva candidata no los
reemplaza. Se conservan relaciones N:M. Sesión, actividad, contexto y DTO se
filtran por atleta; un intento de vincular una actividad ajena sigue rechazado.
Provenance se conserva en la evidencia del API, sin ocupar la UI principal.

## Q10. Tests y validaciones

Pruebas nuevas backend: **14**. Cubren importación compatible → vínculo automático
→ C.1 COMPLETED → overview; PARTIAL; OVER_DURATION; UNKNOWN; UNMATCHED;
workout con laps y sin laps (aunque exista media global); múltiples actividades;
vínculo manual conservado tras nueva sincronización; candidatos/sesiones ambiguos;
aislamiento; fechas de consulta; lectura sin SQL de escritura; ausencia de score;
error de matching y recuperación mediante retry. El último entrenamiento de hoy
se evalúa con C.1 sin añadir sesiones pendientes de hoy a la lista pasada.

Pruebas nuevas frontend: **14**. Estados españoles sin enums, comparación,
fecha sin hora ficticia, targets con/sin evidencia, refresh mediante evento,
evento de otro atleta ignorado, cambios de atleta y respuestas tardías, error
distinto de UNMATCHED, cliente GET scoped y flujo completo del botón de sync en
Dashboard que refresca de UNMATCHED a COMPLETED.

| Validación | Resultado |
| --- | --- |
| Backend focal: overview, post-sync, C.1, matching, API de vínculos, importación y multiathlete | 64 passed |
| Planning/adaptación/ejecución/reassessment | 389 passed |
| Backend completo | 1658 passed, 8 warnings existentes |
| Frontend completo final | 350 passed, 45 archivos |
| TypeScript sin emitir | Correcto |
| Vite build final | Correcto, 109 módulos |
| compileall app/scripts/tests | Correcto |
| Auditor multiatleta real | 28 comprobaciones, 0 incidencias |
| Alembic current/heads | 0026_session_activity_links, mismo head |
| git diff --check | Correcto |

Las advertencias backend pertenecen a TestClient/httpx, serialización de fixtures
de catálogo y una expresión de matching vacía en tests existentes. Se usó
`TC_AUTH_MODE=development` solo en procesos de prueba, sin editar `.env`.

## Validación real y visual

El script `backend/scripts/validate_execution_overview_readonly.py` ejecutó el
GET real para tres atletas, mediante identidad de membresía existente y
transacción PostgreSQL READ ONLY con rollback. Cutoff final: **2026-09-17**.

- Atleta `2b3fe99c-95a1-4351-b8ce-06bcb8833c0e`: sin actividad ni sesiones recientes; 3 SELECT.
- Atleta `3d74bef7-c14e-48fa-9517-8d530c142659`: última actividad sin sesión vinculada; 5 SELECT.
- Carlos Murat, `542a8eeb-5fca-4e21-b14e-0f6d02d0f54b`: última actividad `bc7bee00-5e8c-4bdd-a34f-2124bec3fe33`, sin sesión vinculada; una sesión pasada, `b21dc8e6-8b89-474c-9ca6-4e1651c3ac0d`, devuelve UNMATCHED; 7 SELECT.

No hay un caso real COMPLETED vinculado que demostrar con esos datos; el caso
de éxito post-sync se demuestra mediante importación en una DB de prueba. No se
fabricaron vínculos ni se alteraron datos reales para conseguirlo. El overview
utiliza hasta ocho consultas por lectura autorizada con datos completos, no N+1;
la autenticación por cookie puede añadir su consulta de identidad.

El navegador integrado no estaba disponible. Se utilizó Edge headless con
perfiles temporales y frontend real a **1440 px y 480 px**, conectado a routers
reales bajo transacciones READ ONLY. La sesión temporal seleccionó a Carlos
Murat; no se accedió al perfil personal del navegador. Se revisaron el último
entrenamiento, estado sin vínculo, lista compacta y adaptación a ancho reducido.
No se pulsó sync ni se hicieron peticiones de escritura. Capturas y servidor
temporal quedan en `backend/.tmp_pytest_d2q_visual_20260916/`, fuera de Git.

## Archivos y exclusiones

Modificados: router dashboard; procesador post-sync; DashboardPage; AppShell;
apiClient. Nuevos: application `execution_overview.py`; script de validación;
dos módulos de tests backend; componente, tipos, CSS y tests frontend de overview;
auditoría e informe Q.

Sin cambios en C.1, sus thresholds, las fórmulas de Training Status, D.1, reglas
de matching, esquema DB, migraciones, workout builder o reglas de adaptación.
No se modifica automáticamente el plan ni el status persistido de la sesión.
Los nuevos vínculos son hechos que C.1 puede consumir normalmente; no se cambia
la semántica de fingerprints de Planning. Sin score nuevo, diagnóstico ni
prescripción. `backups/`, `informe/`, temporales y tsbuildinfo quedan fuera.
Sin staging, commit ni push.
