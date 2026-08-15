# Arquitectura de planificación de entrenamiento

## Alcance 0.8E.7

Esta fase crea la base canónica de planificación y la primera UX de objetivos. No genera planes con IA, no integra Garmin y no vincula todavía sesiones planificadas con actividades realizadas.

## Modelo

- `CompetitionGoal`: competición athlete-scoped, multiobjetivo, prioridad A/B/C, modalidad, formato y distancias canónicas. `DELETE` cancela lógicamente el objetivo; evita romper futuras asociaciones.
- `TrainingPlan`: contenedor athlete-scoped con fechas, estado y origen `human|ai`.
- `TrainingPlanGoal`: asociación explícita many-to-many `primary|supporting`. La capa de aplicación rechaza asociaciones entre atletas distintos.
- `PlannedTrainingSession`: intención futura distinta de `CompletedActivity`; admite `training_plan_id=null`.
- `StructuredWorkout`: relación uno-a-uno opcional con una sesión, `schema_version=1` y `definition` JSONB validado al escribir y leer.

La autoría combina `origin`, `created_by_user_id`, `created_via_role` y, para IA futura, `algorithm_version`. IA no es un `User`: `origin=ai` implica creator nulo.

## Workout neutral

El schema v1 admite pasos `warmup|work|recovery|cooldown`, duraciones `time|distance|open`, targets `power|heart_rate|pace|swim_pace|cadence|rpe|none`, modos `zone|absolute_range|percent_reference|none` y referencias FTP, FC umbral, ritmo umbral y CSS. Los bloques `repeat` conservan repeticiones anidadas sin expandirlas.

No contiene campos Garmin. El flujo futuro será:

```text
StructuredWorkout -> GarminWorkoutAdapter -> Garmin
StructuredWorkout -> OtherProviderAdapter -> otro dispositivo
```

Esto describe una frontera de adaptadores, no compatibilidad disponible.

## Autorización

`read_training_planning` permite a Athlete/Owner/Coach asignado leer el contexto seleccionado. `manage_competition_goals` permite a Athlete/Owner (y editor compatible) crear, editar y cancelar. Las capabilities se resuelven por membership activa; revocar Coach elimina inmediatamente el acceso.

## Flujo futuro

```text
goal -> generación de plan -> sesiones planificadas -> adaptador de dispositivo
     -> actividad completada -> comparación -> replanificación adaptativa
```

Un motor futuro podrá consumir objetivos, perfil deportivo y de rendimiento, carga, estado de forma, historial y disponibilidad; producirá `TrainingPlan`, `PlannedTrainingSession` y `StructuredWorkout`. No forma parte de 0.8E.7.
