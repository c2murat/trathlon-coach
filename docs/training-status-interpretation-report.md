# 0.8G.2D.1 — Informe A–AO

Validación actualizada: 16 de septiembre de 2026, tras el ajuste final solicitado. Implementación descriptiva, sin prescripción automática. Revisada visualmente con Edge headless sobre frontend y endpoints reales, a 1440 y 480 px. **D.1 permanece pendiente de nueva revisión del usuario; no se cierra Git.**

## A. Auditoría inicial

Branch `sprint-0.8a-authentication`. HEAD inicial, tracking y remoto publicado comprobados: `3508844f7d16555b270920f63300d619309d657d`. El estado inicial solo contenía las carpetas ajenas `backups/` e `informe/`. Se revisaron dominio, aplicación, persistencia, endpoints, cliente, página, gráfico, formatters, autenticación, selección de atleta y tests. Detalles en [auditoría](training-status-interpretation-audit.md).

## B. Semántica actual Fitness/Fatigue/Form

El modelo existente actualiza cada indicador mediante `anterior + (carga_diaria-anterior) × (1-exp(-1/τ))`: τ=42 días para fitness y τ=7 para fatiga. Forma es fitness menos fatiga del mismo día. El cálculo conserva precisión interna y publica dos decimales; warmup dura 84 días. D.1 consume los valores persistidos, incluida la forma, sin recalcular ninguna de estas fórmulas ni rellenar días ausentes.

## C. Arquitectura D.1

Filas de Training Status → observaciones inmutables → `TrainingStatusInterpreter` → `TrainingStatusOverviewResponse` → presentación española. `TrainingStatusOverviewAssembler` reutiliza las lecturas existentes. El dominio no depende de DB, HTTP, frontend, Planning ni reloj del sistema.

## D. Domain models

`TrainingStatusObservation` identifica atleta, fecha, valores, warmup, timezone y versiones de origen. `TrainingStatusInterpretation` incluye atleta, cutoff, versión, fecha real de datos, valores actuales, estado de forma/global y claves de presentación. Añade `short_term` y `broader_context` (`TrendWindow`), con días, fecha inicial, deltas y tendencias; `recent` (`RecentStatus`) contiene movimientos de fitness/fatiga, sus giros, delta de forma y recovery turn. Los campos previos de tendencia conservan la semántica de siete días. Modelos anidados congelados, serializables, sin campos extra ni números no finitos; enums y reason codes ordenados.

## E. Versionado

Constante central `TRAINING_STATUS_INTERPRETATION_VERSION = "0.8G.2D.1"`. No cambia las versiones existentes de carga, fuerza ni Training Status.

## F. Trend windows

`short_term`: último estado en o antes del cutoff frente a exactamente siete días antes, con ocho observaciones diarias consecutivas. `broader_context`: comparación frente a 21 días antes, con 22 observaciones consecutivas. Si faltan datos para 21 días se informa de ello y se conserva la interpretación válida de siete días. Antigüedad máxima de un día; dos días o más producen interpretación insuficiente con `STALE_STATUS` en todos los horizontes. Sin weighting, interpolación ni imputación. El intervalo del gráfico no recorta la evidencia de interpretación.

`recent`: últimos tres días, cuatro observaciones, sobre una semana completa. Se considera estable únicamente si el rango máximo-mínimo es ≤1. Se considera subida/bajada sostenida si el delta es >1/<−1 y todos los movimientos diarios siguen esa dirección, permitiendo mesetas. El resto es `MIXED`. Hay giro cuando el cambio de los cuatro días anteriores (día −7 a día −3) supera la banda estable en sentido opuesto. `RECENT_RECOVERY_TURN` exige además mejora de la forma persistida >1 punto en esos tres días. Se compara forma almacenada, no se recalcula fitness−fatiga.

## G. Fitness trend semantics

En 7d y 21d: delta >1 `RISING`; delta en [−1,+1] `STABLE`; delta <−1 `FALLING`. Cada horizonte exige su historia completa. El giro reciente es independiente: fitness puede estar por encima de hace tres semanas y estable o descendiendo en los últimos tres días. Una disminución dentro de la banda estable no se presenta como pérdida.

## H. Fatigue trend semantics

Misma banda estable. Delta ≥10: `RISING_FAST`; >1 y <10: `RISING`; <−1: `FALLING`. En 7d se presenta como aumento rápido durante esa semana; en 21d como aumento claro respecto a hace tres semanas, sin confundirlo con una velocidad diaria. Una bajada reciente sostenida y un giro tienen prioridad narrativa sobre el balance semanal, que se conserva explícitamente en la miniinterpretación.

## I. Form semantics

Forma ≤−20: `HIGHLY_LOADED`; (−20,−5): `LOADED`; [−5,+5]: `BALANCED`; (+5,+20): `FRESH`; ≥20: `VERY_FRESH`. Sigue siendo una fotografía actual. El estado `LOADED` puede contextualizarse con recuperación parcial de frescura solo cuando hay giro descendente de fatiga y mejora de forma persistida. Sin evidencia reciente suficiente no se clasifica el estado actual. No cambia su fórmula ni se diagnostica a partir de valores negativos.

## J. Overall-state semantics

Precedencia determinista: evidencia insuficiente → carga relativa muy alta → carga → ambos indicadores descendiendo → recuperación de frescura con fitness estable/creciente → frescura → fitness creciente → equilibrio relativo. `REDUCED_LOAD` no decide entre recuperación planificada y desentrenamiento. `RECOVERING` no afirma recuperación clínica completa.

## K. Thresholds y origen

No existían bandas descriptivas de Training Status reutilizables. El límite de Planning para su presupuesto tiene otra finalidad y no se importa. Constantes centralizadas: estabilidad ±1 punto, magnitud de fatiga +10, forma ±5/±20, horizontes 7/21 días, tramo reciente 3 días y vigencia un día. Se reutiliza la banda de un punto para estabilidad reciente, dirección previa y mejora de forma. Son decisiones de presentación, no límites fisiológicos ni reglas de entrenamiento. Tests de límites exactos, valores contiguos y oscilaciones.

## L. Reason codes

Conserva razones de tendencias, forma, relaciones, insuficiencia, caducidad y warmup. Añade `FATIGUE_ELEVATED_OVER_21D`, `FITNESS_HIGHER_OVER_21D`, `FATIGUE_RECENTLY_FALLING`, `FITNESS_RECENTLY_STABLE`, `RECENT_RECOVERY_TURN` e `INSUFFICIENT_BROADER_CONTEXT`. No se muestran enums técnicos al usuario. La dirección y los giros de ambos indicadores también tienen metadata tipada propia.

## M. API changes

Nuevo GET `/training-status/overview` bajo la familia existente. Devuelve `series`, `latest` e `interpretation`. `end_date` es el `as_of_date` explícito. Valida timezone, versiones, orden del intervalo, fechas desde 2000, ausencia de futuro y diferencia máxima de 366 días. `Cache-Control: private, no-store`. Conserva los contratos de GET de serie, GET latest y POST de recálculo existentes. La lectura latest recibe un filtro de cutoff opcional; sus consumidores previos conservan su comportamiento.

## N. Multiathlete

Utiliza `get_current_athlete`, membresía existente y filtro por atleta en ambas consultas. La prueba cross-athlete devuelve 403 y los estados de atletas distintos no se mezclan. El dominio rechaza observaciones de otro atleta y configuraciones mezcladas. Frontend invalida el resumen al cambiar atleta/periodo, muestra loading, verifica el atleta de la respuesta e ignora respuestas tardías; mantiene la invalidación central del cliente.

## O. Determinism

Cutoff explícito, orden cronológico, Decimal, prioridades fijas y razones ordenadas. Mismos datos y cutoff producen la misma serialización, incluso con entrada desordenada. Se excluye el futuro y se rechazan fechas duplicadas. Sin random, LLM, ML ni timestamps de ejecución en el resultado.

## P. Query/performance

Antes: dos peticiones, dos SELECT de datos y dos comprobaciones de membresía, según los caminos auditados. Después: una petición, los mismos dos SELECT de datos y una comprobación de membresía. El total de tres SELECT está medido en tests y en los tres atletas reales consultados. La resolución de identidad mediante cookie puede añadir su propia consulta por petición; el harness de validación proporciona una identidad existente y no la cuenta. El intérprete añade cero consultas y no hay N+1. Ordena la serie acotada: O(n log n), memoria O(n).

## Q. Frontend integration

Orden definitivo solicitado: cabecera/selector → tarjetas de valores actuales → gráfico → resumen inmediatamente después → warmup, ayuda adicional y resto. El último ajuste modifica exclusivamente render order y su test; conserva textos, lógica, API, ventanas 21d/7d/3d y thresholds. Se conserva el gráfico, sus formatters, los periodos 4/8/12 semanas y controles existentes. Sin segunda página ni duplicación del resumen. La ruta pasa `athleteId`; overview conserva la petición única. Ningún GET dispara recálculo; el POST existente solo sigue disponible como acción explícita del usuario.

## R. Amateur-friendly copy

Mapas tipados españoles, headline, badge y resumen principal de tres frases. El resumen prioriza contexto 21d y dirección reciente; las miniinterpretaciones conservan 7d. Se cualifica la frase semanal de fatiga cuando hay giro reciente. El caso de recuperación tiene menos de 100 palabras, comprobado por test. Sin jerga CTL/ATL/TSB, promesas competitivas, diagnóstico ni órdenes. El frontend no calcula deltas, tendencias ni umbrales.

## S. Fitness presentation

Miniinterpretación de crecimiento, estabilidad o descenso del fitness estimado. La ayuda lo explica como una estimación de la forma física construida durante varias semanas. Los números siguen usando el formatter existente.

## T. Fatigue presentation

Miniinterpretación de aumento rápido, aumento, estabilidad o descenso. La ayuda explica el cansancio estimado asociado principalmente a entrenamientos recientes. No se deduce necesidad de descanso ni enfermedad.

## U. Form presentation

Miniinterpretación de frescura relativa frente a carga, con referencia explícita al modelo. La ayuda explica la relación con el fitness. No se usa forma negativa como diagnóstico.

## V. Recent-trend presentation

Primero se presenta el recovery turn, después un giro de fatiga, después un giro de fitness y, si no hay giro, la relación semanal previa. Los giros identifican explícitamente los tres días recientes; las observaciones semanales mantienen su horizonte. No se inventa observación con historia insuficiente.

## W. Disclaimer

Texto secundario: «Estos indicadores son una estimación matemática basada en tu carga de entrenamiento. Interprétalos junto con tus sensaciones, descanso y estado general». No es una alerta dominante.

## X. Loading/empty/error

Loading oculta resultados del atleta anterior. Historia ausente, incompleta o antigua muestra el estado insuficiente y su explicación; si es antigua, identifica que los valores guardados necesitan actualizarse. Errores HTTP o atleta inesperado muestran error de consulta, nunca insuficiencia. El estado vacío no dispara escrituras ni cálculo automático.

## Y. Accessibility

Región con nombre, headings jerárquicos, badge textual, tres secciones identificadas y ayuda nativa `details/summary`, accesible por teclado y con foco visible. Se reutilizan colores de texto/superficie existentes; ninguna interpretación depende del color. Tres columnas pasan a una por debajo de 700 px. Foco/semántica comprobados en DOM; legibilidad y disposición comprobadas visualmente en tema claro a 1440 y 480 px. No se afirma una auditoría formal completa de accesibilidad.

## Z. Planning isolation

Sin cambios en PlanningContext, fingerprint, preview, builder, C.1–C.8 ni sus inputs. La prueba del GET confirma que no se ejecuta SQL de escritura; otra regresión conserva la serialización completa de un artefacto de preview antes/después del GET. También se ejecutó el conjunto existente de Planning, adaptación y reassessment. No se incorpora D.1 a decisiones de entrenamiento.

## AA. Read-only guarantees

El nuevo camino solo consulta; no hace add, flush, commit ni recalculation. Las lecturas del assembler se ejecutan con `no_autoflush`. Tests monitorizan SQL y commits. Validación real: transacción PostgreSQL `READ ONLY`, comprobación de `transaction_read_only`, vigilancia de SELECT durante cada GET y rollback final. No se modificaron TrainingLoad, CompletedActivity, TrainingPlan, PlannedTrainingSession, StructuredWorkout, perfiles ni históricos reales.

## AB. Archivos creados/modificados

Modificados (6):

- `backend/app/api/v1/routes/training_status.py`
- `backend/app/api/v1/schemas/training_status.py`
- `backend/app/application/training_status.py`
- `frontend/src/app/AppShell.tsx`
- `frontend/src/features/trainingStatus/TrainingStatusPage.tsx`
- `frontend/src/services/apiClient.ts`

Creados (12):

- `backend/app/application/training_status_interpretation.py`
- `backend/app/domains/training_status/interpretation.py`
- `backend/scripts/validate_training_status_interpretation_readonly.py`
- `backend/tests/test_training_status_interpretation.py`
- `backend/tests/test_training_status_overview_api.py`
- `frontend/src/features/trainingStatus/TrainingStatusSummary.tsx`
- `frontend/src/features/trainingStatus/TrainingStatusSummary.test.tsx`
- `frontend/src/features/trainingStatus/interpretationPresentation.ts`
- `frontend/src/features/trainingStatus/interpretationTypes.ts`
- `frontend/src/features/trainingStatus/trainingStatusSummary.css`
- `docs/training-status-interpretation-audit.md`
- `docs/training-status-interpretation-report.md`

## AC. Backend focal tests

75 casos de dominio y 9 de overview: **84 casos D.1**, incluidos en la ejecución focal final. La revisión añade 26 sobre la entrega inicial. Cubre fatiga alta en 21d descendiendo recientemente, subidas/bajadas coincidentes en 7/21d, fitness alto en 21d estable recientemente o descendiendo semanalmente, giros, mejora de forma, historia incompleta de 21d, límites, oscilaciones, determinismo, aislamiento y carga de 21d con gráfico estrecho sin consultas adicionales.

## AD. Training Status regressions

Conjunto explícito de interpreter/overview, Training Status dominio/aplicación/API/modelos/sync/backfill y aislamiento multiatleta: **239 passed**. Incluye `test_multi_athlete_isolation`, `test_multi_athlete_integrity_hardening` y `test_current_athlete`.

## AE. Frontend focal tests

**34 passed, 4 archivos**, reejecutados tras el ajuste definitivo de layout: doce de resumen/integración, once de página, cuatro de gráfico y siete de formatting. El test de orden verifica adyacencia valores → gráfico → resumen. También verifica texto de giro reciente, tres frases y menos de 100 palabras en el caso de recuperación, contexto insuficiente de 21d, ausencia de falsa recuperación, estados, teclado, cambio de atleta, respuestas tardías, ausencia de enums y GET sin recálculo automático.

## AF. Frontend completo/build

**336 passed, 44 archivos**, reejecutados tras el ajuste definitivo de layout. `tsc -p tsconfig.app.json --noEmit` correcto. `vite build` correcto, 107 módulos. No se ejecutó `tsc -b`, preservando `frontend/tsconfig.app.tsbuildinfo`.

## AG. Planning regressions

**406 passed**: archivos de Planning, adaptación, niveles de intensidad y capability reassessment. Ningún cambio en sus implementaciones o contratos.

## AH. Backend completo

**1644 passed, 8 warnings, 155,30 segundos**. Son 84 casos adicionales respecto a la base de 1560. Los avisos corresponden a deprecación de TestClient/httpx, serialización de fixtures de catálogo y una expresión de matching vacía en tests existentes. Se usó `TC_AUTH_MODE=development` solo en el proceso, sin editar `.env`, y un directorio temporal nuevo excluido de Git.

## AI. compileall

`python -m compileall -q app scripts tests`: correcto.

## AJ. Auditor multiatleta

Auditor existente ejecutado sobre la DB real dentro de la transacción de solo lectura: **28 comprobaciones, 0 incidencias**.

## AK. Alembic

`alembic current` y `alembic heads`: ambos `0026_session_activity_links (head)`. Sin migraciones ni upgrades.

## AL. Git hygiene

Branch y HEAD conservados. Sin staging, commit ni push. `git diff --cached` vacío. `git diff --check` correcto; comprobación adicional de whitespace en los doce archivos nuevos correcta. Estado final: seis archivos modificados y doce nuevos de D.1, además de las dos carpetas ajenas iniciales. Los avisos LF→CRLF de Git no indican errores de whitespace; la carpeta temporal antigua con acceso denegado permanece intacta.

## AM. Real-data validation

Cutoff explícito `2026-09-16`; últimos datos de los dos atletas con estado: `2026-09-15`, comparación desde `2026-09-08`. Router real de FastAPI ejecutado mediante ASGI contra PostgreSQL real, con identidad de membresía existente suministrada por el harness; no se simula la respuesta ni se escribe en DB. Cada GET devuelve 200 y usa tres SELECT.

La sesión temporal de validación visual selecciona al atleta predeterminado de desarrollo, Carlos Murat (`542a8eeb-5fca-4e21-b14e-0f6d02d0f54b`), confirmado en la página real. No se accede al perfil personal del navegador del usuario ni se afirma conocer su selección persistida. También se contrastan los otros atletas accesibles mediante el harness de solo lectura.

| Atleta | Fitness | Fatiga | Forma | Delta fitness / fatiga | Tendencias | Estado |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `542a8eeb-5fca-4e21-b14e-0f6d02d0f54b` (predeterminado) | 36,39 | 53,39 | −17,00 | +5,77 / +15,63 | RISING / RISING_FAST | LOADED |
| `3d74bef7-c14e-48fa-9517-8d530c142659` | 28,35 | 42,32 | −13,97 | +4,95 / +29,10 | RISING / RISING_FAST | LOADED |
| `2b3fe99c-95a1-4351-b8ce-06bcb8833c0e` | sin datos | sin datos | sin datos | sin datos | INSUFFICIENT_DATA | INSUFFICIENT_DATA |

Para Carlos Murat, además del balance 7d de la tabla: delta 21d de fitness **+8,26**, fatiga **+21,93**; delta 3d de fitness **−0,13** (estable según el rango completo), fatiga **−11,06** (descenso sostenido), forma **+10,93**. El aumento previo de fatiga y posterior descenso cumplen `RECENT_RECOVERY_TURN`. Las ventanas empiezan el 25 de agosto (21d), 8 de septiembre (7d) y 12 de septiembre (3d), finalizando el 15 de septiembre.

Se ejecutó el mapper TypeScript real sobre la respuesta real y se comprobó el texto en la captura de la página. Para Carlos produjo:

**Estás en un periodo de carga**

> Tu fatiga estimada ha aumentado claramente respecto a hace tres semanas, aunque en los últimos tres días ha descendido. Tu aptitud física estimada sigue por encima de hace tres semanas, y en los últimos tres días se mantiene estable. La forma sigue siendo negativa: estás más cargado que fresco, aunque la bajada reciente de fatiga coincide con una recuperación de frescura.

Observación: «La fatiga ha cambiado de dirección: tras subir, lleva tres días descendiendo y la forma ha mejorado».

El otro atleta con datos presenta fatiga +15,37 a 21d y +19,67 a 3d, fitness +1,93 a 21d y +3,76 a 3d; no hay giro de recuperación. Recibe copy de aumento reciente, no el texto de Carlos. Ningún resultado está hardcodeado por atleta.

Para el atleta sin estado produjo «Todavía no hay suficientes datos para interpretar tu estado de forma» y «A medida que acumules entrenamientos, TriCoach podrá mostrar cómo evolucionan tu fitness, fatiga y frescura».

## AN. Visual validation

El navegador integrado devolvió **`Browser is not available: iab`** tras seguir la skill y su troubleshooting. Se utilizó como alternativa Edge headless instalado, con perfiles temporales independientes. Vite sirvió el frontend real en `127.0.0.1:15173`; un servidor temporal en `127.0.0.1:18001` montó los routers reales de auth, session/context y Training Status, con `READ ONLY` y rollback por petición, rechazando métodos de escritura. No se simularon respuestas ni se arrancó el inicializador OAuth del backend.

Inspección visual real realizada en desktop 1440×1800 y ancho reducido 480×2400: valores antes del gráfico, resumen inmediatamente después, contenido conservado, badge legible, tres miniinterpretaciones en columnas/una columna, sin cortes visibles de texto. Se mantienen ayuda y disclaimer. No se pulsó recalcular ni se creó sesión persistente en DB. Las capturas finales `.tmp_d1_layout_desktop.png` y `.tmp_d1_layout_narrow.png` se conservan en `backend/.tmp_pytest_d1_visual_artifacts_20260916/`, junto a los artefactos temporales de esta revisión, excluidos de Git. Servidores temporales detenidos tras la comprobación. D.1 sigue abierto a nueva revisión del usuario.

## AO. Exclusiones

Sin cambios de fórmulas, carga diaria/semanal, histórico, PlanningContext, fingerprint, preview generation, workout builder, adaptación C.1–C.8, capacidades/performance profile, DB schema o migraciones. Sin wellness, sueño, HRV, resting HR, dolor, enfermedad, RPE ni nutrición como inputs. Sin LLM, ML, prescripción, diagnóstico o recálculo automático. `backups/`, `informe/`, temporales y `frontend/tsconfig.app.tsbuildinfo` quedan fuera de la entrega. No se inicia otra fase. Sin staging, commit ni push.
