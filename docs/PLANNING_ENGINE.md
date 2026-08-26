# Motor de planificación — auditoría y contratos de 0.8F.1

Estado auditado sobre `c030d7b`. Este documento describe capacidades reales y una
arquitectura futura; no implementa generación, periodización ni persistencia.

## Implementación 0.8F.2

0.8F.2 materializa exclusivamente el input puro del futuro motor:

```text
PlanningRequest -> PlanningContextAssembler -> PlanningContext + fingerprint
```

Los contratos inmutables viven en `app/domains/planning/contracts.py` y el
ensamblador SQLAlchemy, fuera del dominio puro, en
`app/application/planning_context.py`. No existe todavía `PlanningEngine`,
`PlanningResult`, generación de semanas/sesiones, API pública ni persistencia del
contexto o de preferencias.

Decisiones efectivas:

- `PlanningRequest` exige atleta, `planning_date`, timezone IANA, goals únicos en
  orden UUID canónico, fechas, preferencias y versiones de algoritmo/configuración.
  El enum estabiliza `INITIAL_PLAN|REPLAN_FROM_DATE`, pero el assembler sólo ejecuta
  `INITIAL_PLAN` en esta fase.
- Las preferencias separan restricciones cuantificables (slots, minutos y máximos)
  de preferencias de colocación (descanso, días largos y fuerza semanal). Se reciben
  en el request y no tienen defaults deportivos ocultos ni tabla.
- Los goals se ordenan por fecha, prioridad A/B/C y UUID; sus segmentos por posición
  y UUID. Un request inicial no inventa `primary|supporting`, por lo que `role` queda
  nullable hasta que una relación o selección explícita lo aporte.
- El perfil y las referencias se resuelven **as-of `planning_date`**: una versión
  cuya fecha local efectiva coincide con `planning_date` ya es configuración
  conocida y puede utilizarse; sólo se excluyen versiones de fechas posteriores.
  El snapshot conserva valores efectivos, IDs, vigencia, fuente, calidad y versiones;
  los ausentes permanecen `None`.
- El cutoff factual es el final del día local anterior a `planning_date`. La consulta
  usa el intervalo UTC equivalente `[planning_date-90, planning_date)` y deriva en
  memoria ventanas inclusivas de 7, 28, 42 y 90 días. No usa actividades del propio
  día de planificación ni posteriores.
- Por tanto hay dos fronteras deliberadamente distintas: `OBSERVATION_AS_OF =
  planning_date - 1 local day` para entrenamiento/carga/fuerza/status y
  `PERFORMANCE_AS_OF = planning_date` para perfil/referencias. El entrenamiento del
  día aún no pertenece al histórico cerrado, mientras que una referencia ya efectiva
  ese día sí es información disponible para generar.
- Una consulta obtiene hasta 90 días de `CompletedActivity` con su carga versionada;
  otra obtiene fuerza manual y su carga. No se leen laps ni streams. Los agregados
  diarios suministran total, resistencia/fuerza, cobertura y calidad sin recalcular
  TrainingLoad. Las ventanas mantienen breakdown estable de running, cycling,
  swimming y strength, incluyendo missing load y sesiones largas factuales.
- TrainingStatus se selecciona con `local_date <= cutoff` y combinación exacta de
  timezone/versiones. Nunca se usa simplemente el último status global.
- Ausencia de perfil, historial, carga o status no bloquea el contexto; produce
  `None`, contadores y warnings técnicos deterministas. Mismatch de atleta, goal
  inexistente/inactivo, timezone incoherente o rango inválido sí es estructural.
- El fingerprint es SHA-256 de JSON UTF-8 canónico: claves ordenadas, separadores
  compactos, UUID string, fechas/horas ISO-8601, datetimes con zona, Decimal textual,
  enums por valor y `None` explícito. Excluye timestamps de lectura y otros datos de
  ejecución. Consultas y colecciones se ordenan con desempates estables.

`PLANNING_CONTEXT_SCHEMA_VERSION = 1` versiona el contrato, separado de las
versiones solicitadas del futuro algoritmo y su configuración. El resultado de
0.8F.2 es un objeto de ejecución: no se escribe en la base de datos.

## A. Estado actual del dominio planning

El dominio está en `backend/app/db/models/planning.py`, sus objetos puros en
`backend/app/domains/planning/models.py`, y la frontera de escritura interna en
`backend/app/application/planning.py`. La migración `0022_training_planning_base.py`
creó la base y `0023_competition_goal_catalog.py` amplió los objetivos.

| Entidad / tabla | Contenido real | Relaciones y ciclo de vida |
|---|---|---|
| `CompetitionGoal` / `competition_goals` | UUID, timestamps, athlete, nombre, fecha/hora/timezone, categoría, formato, prioridad A/B/C, distancias legacy, tiempo objetivo, notas, estado, creador, ubicación y procedencia | athlete `CASCADE`, creador `RESTRICT`; segmentos `delete-orphan`; índices athlete-fecha, creador y unicidad de fuente |
| `CompetitionGoalSegment` / `competition_goal_segments` | UUID, posición, deporte, distancia, etiqueta y desnivel | goal `CASCADE`; posición única por goal; sin timestamps |
| `TrainingPlan` / `training_plans` | UUID, timestamps, athlete, título, fechas, estado, origen, creador/rol y `algorithm_version` | athlete `CASCADE`, creador `SET NULL`; sin relaciones ORM declaradas |
| `TrainingPlanGoal` / `training_plan_goals` | plan, goal y relación `primary|supporting` | PK compuesta; plan `CASCADE`, goal `RESTRICT`; sin timestamps ni orden |
| `PlannedTrainingSession` / `planned_training_sessions` | UUID, timestamps, athlete, plan opcional, fecha/hora/timezone, deporte, texto, duración/distancia, estado, origen, creador/rol y versión | athlete `CASCADE`, plan/creador `SET NULL`; sesión standalone permitida |
| `StructuredWorkout` / `structured_workouts` | UUID, timestamps, session única, `schema_version=1`, definición JSON validada | session `CASCADE`, relación 1:1 |

Constraints reales: plan `draft|active|completed|archived`; sesión
`planned|completed|skipped|cancelled`; origen `human|ai`; rol nullable
`owner|athlete|coach`; objetivo `active|completed|cancelled`, prioridad A/B/C y
seis categorías. Fechas y cantidades tienen checks básicos. El deporte de
`PlannedTrainingSession` no tiene check DB equivalente al enum de actividades.
Los campos JSON/JSONB del conjunto son `CompetitionGoal.source_snapshot` y
`StructuredWorkout.definition`.

Existe `TrainingPlanningApplication` para crear planes/sesiones, asociar goals y
adjuntar workouts, con controles cross-athlete y atribución AI. No hay rutas API
para planes o sesiones. Los tests cubren la base, aislamiento, workout y migración,
no un motor. `docs/training-planning-architecture.md` declara expresamente que es
una fundación.

## B. TrainingPlan

**Existe:** un contenedor athlete-scoped con intervalo, estados, procedencia,
autoría y versión de algoritmo. Es suficiente como cabecera de una primera
temporada aceptada.

**Falta para el ciclo completo:** timezone/intención de calendario del plan,
configuración e input fingerprint/snapshot, versión de configuración, revisión o
`supersedes`, estado de preview/aceptación/publicación, y auditoría de decisiones.
Por ello no es suficiente por sí solo para preview, reproducibilidad y
replanificación, aunque no necesita cambiar para calcular un resultado puro.

## C. TrainingPlanGoal

Sí permite un plan con varios `CompetitionGoal`. `relationship` distingue un
principal de supporting, pero no impone un único principal, orden ni semántica
de A/B/C. La aplicación permite añadir asociaciones; no ofrece quitar/cambiar y
la PK evita duplicados. El borrado físico del goal queda bloqueado por `RESTRICT`;
la API de goals usa cancelación lógica, por lo que las asociaciones sobreviven.
Es una base válida para temporada multiobjetivo, pero necesita invariantes de
aplicación (un principal como máximo), orden/rol de carrera y manejo de conflictos
si estos no se derivan de fecha/prioridad.

## D. PlannedTrainingSession

**Existe:** sesión dentro o fuera de plan, fecha local, hora opcional, timezone,
deporte, descripción, duración/distancia, estado, procedencia, autor y versión.
Puede representar `strength` como texto y enlazar un workout 1:1.

**Gaps reales:** no hay `locked`, protección manual, `manually_edited`, revisión,
clave determinista, supersesión, razón de cambio, vínculo con
`CompletedActivity`, tipo de sesión, ventana horaria ni constraint DB de deporte.
`origin` y `algorithm_version` dan procedencia mínima, no historial suficiente.
Es apta para la primera persistencia lineal, no para replanificar con seguridad.

## E. StructuredWorkout v1

La definición Pydantic contiene `schema_version=1`, deporte
`running|cycling|swimming|strength|multisport` y una lista no vacía de nodos:

- `step`: fase `warmup|work|recovery|cooldown`, duración y target opcional;
- duración exactamente por tiempo (`seconds`), distancia (`meters`) o abierta;
- target por potencia, FC, ritmo, ritmo de natación, cadencia, RPE o ninguno;
- target en zona 1..10, rango absoluto o porcentaje de referencia FTP, FC umbral,
  ritmo umbral o CSS; rango mínimo/máximo obligatorio cuando corresponde;
- `repeat`: 2..100 repeticiones y pasos anidados, también repeats;
- instrucciones libres. El ORM rechaza JSON que no valide y fija versión 1.

Puede expresar inicialmente carrera fácil/larga/tempo/intervalos, bici Z2 e
intervalos, natación aeróbica y series. Natación técnica sólo se describe en
`instructions`: faltan stroke, drill, material y descanso específico. Fuerza es
demasiado genérica para una rutina: faltan ejercicio, series/repeticiones, carga y
descanso semánticos. Multisport no puede asignar un deporte a cada paso, por lo
que un brick no queda bien tipado. Tampoco están definidas unidades de los rangos
absolutos, escala/límites porcentuales, sistema/versionado de zonas, etiquetas de
paso o equipamiento. Así, v1 basta para la primera biblioteca de resistencia con
esas exclusiones, no para fuerza rica, técnica acuática rica o multisport real.

## F. CompetitionGoal

Ofrece fecha, hora opcional y timezone; categoría/formato; A/B/C; segmentos
ordenados de swim/bike/run con distancia, etiqueta y desnivel; distancias legacy;
tiempo objetivo; ciudad/región/país; notas; estado y procedencia (provider,
external id, URL, fecha y snapshot). La procedencia puede faltar en goals manuales.
No hay perfil de recorrido detallado, inscripción ni restricciones deportivas.
A/B/C es hoy exclusivamente metadata validada: ningún servicio le da semántica
operacional.

## G. Performance Profile

`AthletePerformanceProfileVersion` aporta FC reposo/máxima, peso, FTP, FC umbral
de bici/carrera, ritmo umbral de carrera, CSS y piscina 25/50; incluye
`effective_from`, origen, nota y `algorithm_version`, pero no calidad explícita.
`PerformanceProfileRepository.effective(athlete_id, at)` obtiene la versión más
reciente con `effective_from <= at` (conviene añadir `id` como desempate estable).

El dominio granular `AthletePerformanceReference` sí incorpora deporte, métrica,
unidad, origen, calidad, medición, método y vigencia. `effective_reference` y
`best_effective_reference` permiten resolverla en fecha; `performance_zones`
deriva zonas versionadas. El contexto debe congelar las referencias elegidas y
sus IDs/versiones, sin consultar “latest” durante el cálculo.

## H. Historial

`CompletedActivity` contiene athlete, deporte, UTC `start_at` más timezone,
elapsed/moving time, distancia/desnivel, FC, potencia, velocidad, cadencia, RPE,
carga sRPE, flags indoor/manual/commute, fuente y datos de sincronización. Laps,
streams, métricas y evidencia están relacionados; no son necesarios para el
resumen inicial. La fuerza manual vive aparte.

No existe un único servicio de snapshot 7/28/42/90. Se pueden reutilizar consultas
athlete-scoped por rango sobre actividades, `ActivityTrainingLoad` y agregados
diarios/semanales. El futuro ensamblador de contexto debe hacer una consulta
acotada a 90 días y derivar determinísticamente las cuatro ventanas: duración,
distancia y frecuencia por deporte, sesiones más largas, distribución y cobertura.
No debe leer streams/laps salvo una regla futura explícita.

## I. TrainingLoad

`ActivityTrainingLoad` guarda carga nullable por actividad y versión, método,
unidad, cobertura, calidad, motivo, duración, intensidad/referencia, métricas fuente,
warnings y cálculo. Hay agregados diarios y semanales athlete-scoped que incluyen
carga total, resistencia/fuerza, recuentos, duración, cobertura/calidad, warnings,
IDs fuente, timezone y versiones. La semana es ISO, lunes-domingo.

Sí, la carga reciente puede obtenerse determinísticamente usando la capa de
agregación/rutas `training-load/daily` y `training-load/weekly`, fijando rango,
timezone y versiones. Para construir `PlanningContext` es preferible reutilizar su
aplicación/query interna, no llamar a la propia API. Nunca mezclar versiones ni
tratar carga nullable/parcial como cero silenciosamente.

## J. TrainingStatus

`AthleteDailyTrainingStatus` persiste por fecha local y timezone: `total_load`,
`fitness`, `fatigue`, `form = fitness - fatigue`, número de día histórico,
`is_warmup`, fecha de cálculo y las tres versiones de algoritmo (load, fuerza y
status). Son equivalentes propios de estado exponencial; el código no los denomina
CTL/ATL, por lo que no deben renombrarse así.

`TrainingStatusApplication.get_latest_training_status(...)` y la ruta
`GET /training-status/latest` reciben timezone y versiones; también hay serie por
rango. El snapshot debe seleccionar como máximo `planning_date - 1` (o declarar
otra regla de cutoff), conservar fecha/versiones/warmup y representar ausencia sin
inventar valores.

## K. Fuerza

`ManualStrengthSession` registra inicio UTC, timezone, minutos, regiones corporales,
RPE y notas. `ManualStrengthTrainingLoad` guarda una carga versionada, calidad y
warnings; las agregaciones combinan carga de fuerza y resistencia. Se distingue por
su tabla y, en agregados, por `strength_load`/recuento. Una sesión planificada puede
usar sport `strength`, pero StructuredWorkout v1 sólo ofrece una receta genérica.

## L. Athlete scope / permisos

Todo input y output debe llevar un único `athlete_id`, resuelto mediante
`CurrentAthleteContext`; nunca se aceptará el alcance efectivo sólo desde el body.
Ya existen `READ_TRAINING_PLANNING` y `MANAGE_COMPETITION_GOALS`. Owner y editor
tienen ambas; athlete también; coach y viewer pueden leer planning pero no gestionar
goals. No existe capacidad para generar, aceptar, editar, bloquear o replanificar.
Antes de exponer escrituras deben añadirse capacidades específicas, con una matriz
de producto explícita: previsiblemente owner/athlete/editor generan y aceptan;
coach sólo si se autoriza; viewer nunca escribe. No se modifica en 0.8F.1.

## M. Calendario

Hoy Calendario consulta y muestra únicamente CompetitionGoals en lista/año. No hay
endpoint ni cliente frontend de TrainingPlan/PlannedTrainingSession, por lo que las
sesiones no aparecen y no existe calendario compartido. Los estados visuales son
carga, vacío, error, feedback, lista/año y lectura/edición de goals; no hay estados
de sesión. La integración futura añadirá una fuente athlete-scoped de sesiones y
una proyección común por fecha, conservando tipos/estados distintos.

## N. Disponibilidad y preferencias

La búsqueda en modelos, dominio y aplicación no encuentra persistencia ejecutable
para días/minutos disponibles, límites diarios/semanales, descanso, días largos,
preferencias deportivas, fuerza semanal, piscina, bicicleta, franjas o limitaciones.
Los documentos de visión lo mencionan, pero no constituye capacidad actual. Es el
principal GAP de input.

El contrato debe separar restricciones duras (`available_minutes`, máximo de
sesiones, recursos/franjas realmente indisponibles) de preferencias blandas
(descanso o tirada larga preferidos). Un mapa/tupla de slots por día es extensible:
permite lunes 0, martes 60, miércoles 90 y, más adelante, dos ventanas en un día,
sin columnas booleanas por weekday.

Salud: no existe un dominio de wellness clínico implementado; `READ_ATHLETE_HEALTH`
es una capability y training status contiene fatiga matemática, no síntomas. En el
primer motor no deben usarse sexo, salud inferida, rutas/streams, sueño, lesión,
dolor o enfermedad. La ausencia de datos médicos no se debe interpretar como aptitud.

## O. Replanificación

`REPLAN_FROM_DATE` necesita el plan/revisión base, cutoff local, sesiones pasadas,
completadas, bloqueadas/protegidas y editadas manualmente, además de una clave estable
y motivo/procedencia por cambio. El resultado debe preservar todo lo anterior al
cutoff, completado en cualquier fecha y protegido; sólo puede proponer reemplazos
en el conjunto mutable. Hoy faltan bloqueo, edición manual, revisiones/supersesión y
matching con actividad completada. No puede implementarse de forma segura aún.

## P. Persistencia

- **A. No necesaria todavía:** contratos puros, preview en memoria, estructura de
  temporada y cálculo del snapshot pueden construirse sobre lecturas existentes.
- **B. Preferencias:** antes de aceptar planes reales hace falta persistencia
  athlete-scoped, versionable, para reglas semanales/slots y preferencias; evitar
  columnas por weekday.
- **C. Provenance/versionado:** plan aceptado necesita input/config fingerprint,
  versiones efectivas y referencia al resultado aceptado. Los campos existentes
  `origin`/`algorithm_version` son sólo una parte.
- **D. Bloqueo/replanificación:** sesión necesita protección, edición manual,
  revision/source key, supersesión y vínculo de cumplimiento; plan necesita revisión.
- **E. Opcional:** persistir previews con caducidad, warnings/decisiones estructurados
  o revisiones completas. No es requisito del motor puro inicial.

No se propone ni crea migración en esta fase.

## Q. Contratos propuestos

Todos son objetos inmutables, con tuplas y valores canónicos métricos.

```text
PlanningRequest
  athlete_id, planning_date, timezone, goal_ids (ordered)
  start_date, horizon_end, mode: INITIAL_PLAN | REPLAN_FROM_DATE
  replan_from_date?, planning_preferences, protected_session_ids
  requested_algorithm_version, requested_config_version

PlanningGoal
  competition_goal_id, local_date, start_time?, timezone
  category, format, priority, role: PRIMARY | SUPPORTING | PREPARATORY
  ordered_segments[{sport, distance_m, elevation_gain_m?, label?}]
  target_finish_time_s?, location?, status, source_version

PlanningPreferences
  weekly_slots[{weekday, windows[{start_local?, available_minutes,
    max_sessions, allowed_sports?, resources?}]}]
  hard_max_sessions_per_day, hard_max_sessions_per_week
  preferred_rest_days, preferred_long_run_day, preferred_long_bike_day
  target_strength_sessions_per_week, sport_preferences
  effective_from?, version

AthleteTrainingSnapshot
  athlete_id, reference_date, timezone, input_cutoff
  windows[{days: 7|28|42|90, load, duration_s, distance_m_by_sport,
    session_count_by_sport, longest_sessions, coverage, source_versions}]
  training_status?, performance_reference_ids, history_start?, warnings

PlanningContext
  request, goals, effective_performance_profile/references
  training_snapshot, preferences
  existing_plan_snapshot? (required for replan)
  assembled_at_as_input, input_versions, input_fingerprint

SeasonStructure
  start_date, end_date, goal_milestones, phases (labels/bounds only initially)

PlanningWeek
  iso_year, iso_week, monday, sunday, objective, target_load?, sessions

SessionPrescription
  stable_key, local_date, start_time?, timezone, sport, purpose
  planned_duration_s?, planned_distance_m?, workout_definition?
  source_decision_ids, mutable, replaces_session_id?

PlanningWarning
  code, severity: ERROR | WARNING | INFO, blocking, message_key, context

PlanningResult
  athlete_id, mode, algorithm_version, config_version, input_fingerprint
  season_structure, weeks, warnings, decisions, generated_for_date
```

`PlanningResult` no contiene IDs persistidos nuevos. Sigue el flujo calcular →
validar → previsualizar → aceptar → transacción de persistencia. `decisions` debe
usar códigos y parámetros estructurados, no sólo prosa.

Política de insuficiencia conceptual: identidad/cero goals/fechas inválidas o
restricciones sin solución son errores bloqueantes; objetivo próximo, perfil o
historial incompletos y carga/status ausentes son warnings; sólo se permite fallback
cuando una regla deportiva futura lo declare, con código, supuesto y cobertura.
Un atleta nuevo no recibe valores fisiológicos inventados.

## R. Determinismo

Para idénticos contexto, configuración y versión, el resultado debe ser idéntico:

- `planning_date`, cutoff, timezone IANA, semana ISO y locale deben ser explícitos;
- nada de `datetime.now()` dentro del motor, random ni IDs aleatorios en el resultado;
- consultas ordenadas con desempate por ID; goals y sesiones con orden canónico;
- snapshots inmutables y fingerprint canónico de inputs;
- enteros/Decimal y reglas de redondeo declaradas, no float libre;
- algoritmo y configuración versionados por separado;
- no releer “latest” durante el cálculo ni depender de orden JSON/DB;
- decisiones con tie-breakers documentados.

La granularidad interna recomendada es día local para colocación y semana ISO como
microciclo derivado. No se persiste un tercer calendario redundante. Instantes se
guardan UTC cuando existen, preservando fecha/hora local y timezone IANA.

## S. API futura

- `GET /planning/context?planning_date=...`: diagnóstico de inputs y gaps, lectura.
- `POST /planning/previews`: recibe request/preferencias, devuelve resultado puro;
  no persiste plan/sesiones (un preview temporal sería una decisión posterior).
- `POST /planning/previews/{token}/accept`: valida fingerprint y persiste todo en
  una transacción, rechazando contexto obsoleto.
- `POST /training-plans/{id}/replan-previews`: preview desde fecha, sin mutación.
- `POST /training-plans/{id}/replan-previews/{token}/accept`: aplica una revisión.

El athlete efectivo procede del header/contexto autenticado y debe coincidir con
todos los recursos. Idempotency key en accept evita duplicados. Los contratos de
error separan validación, autorización, contexto obsoleto e inputs insuficientes.

## T. Frontend futuro

Calendario → Generar plan: (1) seleccionar goals y rol, (2) capturar restricciones
y preferencias, (3) mostrar preview con semanas/sesiones/warnings/decisiones, (4)
aceptar explícitamente. El calendario sólo refresca tras accept exitoso. Replan usa
el mismo patrón y muestra qué se preserva/cambia; nunca persiste cien sesiones al
primer clic.

## U. Roadmap

1. **0.8F.2 — contratos puros + ensamblador de contexto:** DTOs, resolución efectiva,
   snapshots 7/28/42/90, fingerprints y fixtures; sin generador ni DB nueva.
2. **0.8F.3 — preferencias y estructura multiobjetivo:** persistencia/API mínima de
   disponibilidad, selección primary/supporting y validación de conflictos; estructura
   de temporada pura.
3. **0.8F.4 — demanda semanal determinista:** presupuesto/carga por semana, política
   de insuficiencia y warnings; aún sin recetas detalladas.
4. **0.8F.5 — biblioteca y colocación de sesiones:** recetas de resistencia v1,
   restricciones/preferencias y validadores. Posponer fuerza rica/multisport si exige
   StructuredWorkout v2.
5. **0.8F.6 — preview/accept y calendario:** provenance, transacción idempotente,
   endpoints y UI.
6. **0.8F.7 — revisiones/replanificación:** protección, matching de completadas,
   supersesión y diff explicable.

El motor inicial y 0.8F.2 no dependen de OpenAI. Una IA posterior puede explicar,
conversar o sugerir, pero no es la fuente primaria del plan.

## Respuestas ejecutivas

1. Ya existen goals ricos, perfil/referencias efectivas, historial, cargas, status,
   fuerza y contenedores de persistencia.
2. Faltan disponibilidad, política/reglas, snapshot unificado, provenance completo,
   preview/accept y soporte de revisión.
3. `TrainingPlan` sirve como cabecera inicial, no como ciclo auditable completo.
4. `TrainingPlanGoal` permite multiobjetivo con gaps de invariantes/orden/rol.
5. `PlannedTrainingSession` sirve para persistencia lineal, no replan segura.
6. StructuredWorkout v1 cubre resistencia básica, con gaps reales descritos en E.
7. El perfil vigente se obtiene por `effective(..., at)` y referencias efectivas.
8. La carga reciente sale de agregados diarios/semanales fijando versiones/timezone.
9. TrainingStatus sale de latest/serie por fecha, timezone y versiones.
10. El historial se resume con una lectura de 90 días y ventanas derivadas.
11. Falta por completo la disponibilidad/preferencia ejecutable.
12. No para contratos/preview puro; sí después para preferencias y provenance/replan.
13. Replan necesita revisión, protección, edición, matching y supersesión.
14. Se reutilizan modelos, aplicaciones de perfil/carga/status y timezone sin tocar DB.
15. El contrato puro es `PlanningRequest + PlanningContext -> PlanningResult`.
