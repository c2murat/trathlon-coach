# D.3 — Auditoría previa

Base: `6d7fd66` (D.2 aceptado). Working tree inicial: solo backups/ e informe/,
sin cambios de aplicación. Sin staging, commit ni push.

- `CalendarPage`: Lista consulta año; Mes consulta cuadrícula de 42 días;
  Año consulta año. Carga objetivos y sesiones en paralelo; protege respuestas
  con generación y cambia scope por atleta. No escucha todavía el evento sync.
- `calendarItems`: unifica objetivos/sesiones, con color por deporte; el
  `status` de planificación no constituye evidencia de ejecución.
- `MonthlyCalendar`: hasta tres sesiones visibles por día, selección con
  detalle básico de título/subtítulo. `AnnualCalendar`: dos indicadores por
  día y navegación a Lista. No hay detalle de ejecución en ninguna vista.
- API de sesiones: `training-plans/sessions`, rango validado y permiso
  READ_TRAINING_PLANNING; `AthleteContext` y cliente central propagan
  X-TriCoach-Athlete-Id y la autorización por membresía.
- `PlannedTrainingSession` conserva fecha civil, timezone, título/tipo,
  duración, distancia y estado de planificación. `StructuredWorkout` aporta
  el objetivo estructurado. No se debe alterar ninguno al mostrar badges.
- `CompletedActivity` y `PlannedSessionActivityLink`: N:M; enlaces manuales
  y automáticos con confianza/provenance. Se excluyen actividades eliminadas
  y ajenas al atleta. `ActivityLap` es la fuente estructurada ya usada por C.1.
- C.1 `PrescribedCompletedEvidenceAssembler`: tres SELECT batch (plan/workout,
  enlaces/actividades, laps). Construye `SessionExecutionEvidence` usando
  `build_session_execution_evidence`; resume en `PrescribedCompletedEvidenceContext`.
  Ventana predeterminada 84 días, cutoff exclusivo. No cubre un año completo.
- `TargetAdherenceEvidence`: fracción redondeada y repeticiones comparadas,
  no un contador exacto de bloques acertados. No se inferirá ese contador.
- D.2 `ExecutionSessionView`, `ActivityFacts` y `activity_facts` son reutilizables.
  Q mantiene su ventana y contrato. Los textos y presentación de targets
  pueden extraerse a un módulo común, conservando los textos largos de Q y
  añadiendo variantes compactas para calendario.
- Tiempo: D.2 usa la zona del perfil y un instante backend. Calendario usa
  fechas civiles y el reloj del navegador para su navegación inicial. El
  nuevo batch entregará as_of_date y timezone del perfil para decidir pasado,
  hoy y futuro; no se usará UTC ni el navegador para clasificar ejecución.

Decisión: endpoint batch read-only por rango visible, máximo 366 días,
con contexto local único. Extraer lectura de rango en el assembler existente,
reutilizando las consultas y el constructor factual de C.1. Su método habitual
conservará exactamente los 84 días y el contexto que consumen D.2/adaptación.
El batch calendar recorta el rango a session_date < as_of_date y devuelve
vistas de sesión reutilizables. Cero migraciones y cero estado persistido nuevo.
