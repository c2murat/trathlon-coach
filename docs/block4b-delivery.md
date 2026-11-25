# Bloque 4B: Structured Strength Intent en shadow

Version publicable: identidad y fechas de capturas omitidas; originales y evidencias detalladas se conservan solo localmente, fuera de Git. Los enlaces a informe/ designan evidencia local no distribuida.

No se activa ninguna duracion nueva de fuerza. La informacion actual no permite estimarla de forma independiente y fiable: faltan tiempos de ejecucion y semantica temporal de descansos/transiciones. La salida estructurada de duracion y su varianza son UNKNOWN/null, con confidence=UNAVAILABLE. Los minutos seleccionados siguen siendo legacy.

Se implementa StrengthSessionIntent como diagnostico interno, fuera de artefactos, identidad, persistencia y aceptacion. La aplicacion publica `strength_shadow_report` solo en memoria, despues del ultimo pase de adaptacion numerica, y lo limpia al iniciar otra generacion. Funciona tanto con NULL como con frecuencia explicita + motor de resistencia4A. No cambia el intent de resistencia ni compensa su volumen.

## Modelo real auditado

| Contrato / fuente | Datos presentes | Limites reales |
|---|---|---|
| models.WorkoutNode | Nodo step/repeat, phase, duration, target, instrucciones, titulo; movimiento, sets, reps opcionales, descanso, unilateralidad; orden mediante lista steps | No tempo de repeticion, tiempo independiente por set, alcance del descanso, transiciones, grupos musculares por ejercicio ni tiempo por lado |
| models.WorkoutDuration | Time seconds, distance con estimated_seconds, open | En fuerza, seconds procede del total asignado por la prescripcion; no demuestra tiempo independiente de ejecucion |
| models.WorkoutTarget | RPE absoluto min/max para ejercicios de fuerza | No kilos, porcentaje1RM ni regla de incremento de resistencia externa en este builder |
| StructuredWorkoutDefinition | sport strength, titulo/proposito y arbol de nodos ordenados, schema_version1 | Sin modelo independiente llamado StrengthPrescription ni protocolo temporal completo |
| workout_labels.STRENGTH_VARIANTS | Dos variantes existentes de seis ejercicios, patrones y unilateralidad | Se reutilizan; no se anaden ejercicios ni se inventa un catalogo muscular |
| SessionPrescription / SessionIntent | GENERAL_STRENGTH, fase, fecha, prioridad, duracion objetivo y procedencia legacy | No hay dos roles fisiologicos A/B ni progresion individual por sesion1/2 |
| PlanningPreferences / TrainingWindowSnapshot | Frecuencia de fuerza; volumen, conteo e historico por deporte | No tempo, series/reps completadas o tiempos entre ejercicios en la ventana agregada |
| ManualStrengthSession / ManualStrengthLoadInput | Fecha, zona horaria, duration_minutes, body_regions, perceived_exertion y notas; modelo persistido manual | BodyRegion son regiones declaradas de una sesion real, no una asignacion automatica a los ejercicios del plan |
| ManualStrengthTrainingLoad / prescribed_load | Carga por duracion/RPE, calidad, metodo y warnings | Carga no es una fuente de duracion ni valida la estimacion estructural; no se invierte su formula |

WorkoutNode valida sets1..10, reps1..100 y rest_seconds0..600. Son limites de schema, no una regla de progresion que deba empujar ejercicios hacia esos extremos. Para phase=strength exige titulo, patron, sets y descanso; reps, target y unilateralidad pueden faltar segun el contrato. El intent observa esos campos opcionales sin inventarlos.

No se localizan contratos de tempo, tiempos por repeticion/set, transiciones o estimacion independiente en las rutas de planificacion, fuerza manual y modelos persistidos auditados. Los defaults globales de warmup/cooldown existen en WorkoutBuilderConfig, pero la rama de fuerza NO llama a las plantillas de resistencia que los utilizan. No se trasladan esos defaults a fuerza.

## Contenido existente, sin nuevas selecciones

La variante0 contiene: Sentadilla goblet; Peso muerto rumano; Zancada inversa; Elevacion de gemelo; Remo con banda o mancuerna; Dead bug.

La variante1 contiene: Sentadilla bulgara; Bisagra de cadera a una pierna; Flexion o press con mancuerna; Elevacion de soleo con rodilla flexionada; Remo con banda; Press Pallof con banda. Los nombres originales con tildes, patrones, unilateralidad y orden se conservan exactamente en los JSON/artefactos.

El shadow extrae el snapshot realmente construido. No genera otro workout ni vuelve a escoger ejercicios. Captura incluso el tiempo asignado a cada nodo, pero lo etiqueta `LEGACY_TOTAL_DIVIDED_AMONG_EXERCISES_NOT_EXECUTION_TIME`.

## Origen exacto de 40 minutos

Ejemplo sintetico equivalente del metodo: 7560 segundos en 3 sesiones dan 42 minutos; el cap de configuracion 40 mantiene el resultado en 40. Este ejemplo no representa observaciones de un atleta.

Los40 se fijan ANTES del builder. `_strength_steps` recibe total2400 segundos y ejecuta divmod(total,exercise_count). En BASE distribuye400 segundos entre cada uno de seis ejercicios. En SPECIFIC reparte480 entre cinco; en TAPER800 entre tres. No deriva esos tiempos de sets/reps/rest/RPE. Tampoco permite concluir, a partir de esos nodos, que tres ejercicios necesitan800 segundos cada uno: son presupuestos asignados, no observaciones o estimaciones independientes.

En la referencia del09/11/2026, 4 actividades /5760 segundos producen media24, dentro de floor20/default40. Sigue24 en todas las observaciones de esa captura. No se han mezclado capturas para atribuir40 vs24 a un cambio de engine.

Los40 son explicables como fallback historico acotado. La prescripcion estructurada actual NO permite validar si40 es una estimacion temporal apropiada. No se afirma que la estructura los justifique.

## StrengthSessionIntent interno

El modelo nuevo es inmutable y guarda:

- athlete_id, week_start, scheduled_date, content_anchor_date, occurrence, role y phase;
- estructura observada: ejercicios ordenados, patron, sets, reps, descanso, unilateralidad, target_rpe, multiplicador de repeat y tiempo legacy asignado;
- exercise_count, nominal_sets y nominal_repetitions (estos totales no multiplican por lados sin una semantica explicitada);
- previous_structure de la misma ocurrencia en la semana inmediatamente anterior, progression_source, progression_level y reason;
- proposed_structure y final_structure como la MISMA salida observada de la regla existente: no son una nueva prescripcion shadow;
- cap/floor de progresion estructural desconocidos, con motivo NO_STRENGTH_PROGRESSION_CAP_FLOOR_POLICY; limites de schema separados en provenance;
- warmup/cooldown, estimated_working_seconds, estimated_rest_seconds y estimated_transition_seconds opcionales, actualmente desconocidos;
- structured_estimated_duration_minutes, variance_minutes y confidence;
- legacy_duration_minutes, selected_duration_minutes, legacy_duration_basis, strength_duration_source, fallback_reason, missing_data y provenance.

En todos los casos actuales la estimacion/varianza son null; selected_duration=legacy_duration y strength_duration_source=legacy_historical. Si no hay historico usable, legacy_duration_basis distingue CONFIG_DEFAULT_WITHOUT_USABLE_HISTORY. No se simula que ese default sea una observacion historica.

StrengthWeekShadow conserva strength_minutes_target del WeeklyPlanningIntent de4A, placed_strength_minutes y numero de intents de fuerza no colocados. structured_strength_minutes_target permanece null. Con NULL sin estructura autoritativa semanal, la fuente se etiqueta NULL_LEGACY_PLACED_OBSERVATION: no se finge que una observacion final sea una nueva autoridad de volumen. El componente de fuerza ya consta en desired_composition[].volume_minutes_target y en los SessionIntent del WeeklyPlanningIntent de4A; WeeklyVolumeIntent expone strength_minutes_target. No se anade un campo serializado nuevo a ese contrato: el sidecar lo referencia. El target original de fuerza y los targets de resistencia no se modifican.

## Que se puede calcular con rigor

Se pueden calcular deterministicamente: numero/orden de ejercicios, sets y reps nominales, descansos individuales declarados, RPE indicado, variante del catalogo existente, nivel de rotacion, igualdad/diferencias entre estructuras, tiempo legacy asignado a nodos y varianza cuando exista una estimacion independiente (hoy no existe).

No se puede calcular el tiempo de ejecucion desde reps sin tempo, ni desde sets sin una regla por set/hold. Tampoco puede sumarse descanso con rigor: rest_seconds no especifica entre que sets, si incluye el ultimo, si el descanso ya esta dentro del tiempo del nodo o si cambia por lado. Transiciones y calentamiento/vuelta a la calma son desconocidos, no cero.

Sumar los tiempos actuales de nodos para llamar al resultado structured_estimated_duration seria circular. Por eso el campo es null aunque workout_duration_seconds mida2400 segundos correctamente. Confidence UNAVAILABLE describe la estimacion de duracion; el contenido es un snapshot exacto del workout, no una lista de ejercicios adivinada.

## Progresion y fases reales

`_progression_level`: semanas transcurridas desde planning_date modulo3; RECOVERY y TAPER fuerzan nivel0. `_strength_steps`: variante por semanas transcurridas modulo2. La distribucion conserva original_date como ancla de contenido para que un movimiento de fecha no cambie ejercicios/progresion; se reutiliza esa misma ancla en el shadow.

| Fase | Ejercicios | Series | Reps | Descanso | RPE | Fuente |
|---|---:|---:|---|---:|---|---|
| BASE | 6 | 3 | 10 si nivel0; 8 en niveles1/2 | 90 s | config5-7 | Perfil default existente |
| BUILD | 6 | 3 | 10/8/8 | 90 s | config5-7 | Mismo default; no intensificacion BUILD independiente |
| RECOVERY | 4 | 2 | 10 | 60 s | 4-6 | Perfil explicito existente |
| SPECIFIC | 5 | 3 | 8 | 90 s | config5-7 | Perfil explicito existente |
| TAPER | 3 | 2 | 6 | 60 s | 4-6 | Perfil explicito existente |
| COMPETITION/RACE | 6 | 3 | Segun nivel modulo3 | 90 s | config5-7 | NO hay perfil exclusivo de fuerza RACE; cae en default si se genera una sesion con esa fase |

La semana de carrera de atleta de referencia esta dominada por TAPER y aplica el perfil TAPER a la fuerza que se genera. No se inventa otra sesion RACE. Las reglas de calendario existentes pueden impedir fuerza en dias previos al evento; se conservan. El horizonte termina en carrera, por lo que no aparecen semanas RECOVERY posteriores: se prueba el perfil con fixtures, no se fabrican filas.

Esta es rotacion de variantes/repeticiones y periodizacion existente, no una progresion monotona demostrada de sobrecarga. No hay incremento automatico de sets, RPE, kilos o minutos en BASE/BUILD; tampoco una respuesta individual a ejecucion de fuerza para esas variables. La duracion historica permanece constante aunque cambien los perfiles.

## Dos sesiones semanales

En la captura actual target6/max12: 47 semanas, 92 sesiones de fuerza observadas; 45 semanas tienen dos y las dos estructuras son identicas en las45. Las otras dos semanas TAPER tienen una sesion. En la referencia:49 semanas,96 sesiones;47/47 semanas con pareja identica. Las primeras12 semanas de cada tabla tienen dos sesiones. Igual estructura/contenido no significa igual identidad: las fechas y fingerprints individuales de las dos sesiones son distintos. Si faltan ambas estructuras, su igualdad se informa como desconocida, no como dos copias verificadas.

S1/S2 son ocurrencias ordenadas en el calendario, no nuevos roles A/B. Ambos usan GENERAL_STRENGTH y comparten la misma regla semanal por fase/nivel/variante. El dominio soporta alternancia ENTRE semanas, no una asignacion A/B dentro de una semana. No hay soporte actual que decida progresiones fisiologicas independientes para S1/S2; separarlas requeriria otro diseno, no un cambio de etiquetas.

[Tabla actual completa, con las primeras12 semanas](block4b-current-target6-horizon.md) y [referencia24 min](block4b-reference-target6-horizon.md). Las tablas muestran los ejercicios de cada sesion, duracion legacy, estimacion UNKNOWN, fase, RPE, sets/reps, descansos, fuente de progresion, confianza y fallback. Los JSON enlazados incluyen previous/proposed/final y toda la procedencia.

## Dobles y capacidad

No se cambia compatibilidad ni scoring. Swim+strength sigue permitido; fuerza+largo conserva su coste de preferencia y no se convierte en una nueva prohibicion. Se mantienen max_daily_sessions y minutos por slot.

Como la duracion estructurada es desconocida y sigue en shadow, la capacidad usa la duracion REAL vigente de la prescripcion/workout:40 o24 segun captura. El shadow no introduce un numero hipotetico en distribucion. Hay una prueba con una doble efectiva swim+strength y un dia no disponible, que verifica la capacidad, compatibilidad y equivalencia de contenido antes/despues de observar fuerza.

Cuando exista una estimacion fiable y se autorice su activacion, debera alimentar el SessionIntent antes de _place y de construir/distribuir workouts, siguiendo la ruta de duracion de4A. Entonces sera necesario revalidar todas las dobles con ese nuevo valor. Esa activacion no forma parte de4B.

## Ampliacion minima necesaria, SIN implementar ni migrar ahora

Para obtener una estimacion independiente se necesitan snapshots versionados de:

1. Una fuente de tiempo de trabajo por ejercicio/set: tempo por repeticion, tiempo por set o duracion explicita de hold; modo y procedencia que distingan tiempo independiente de presupuesto legacy dividido.
2. Alcance de reps y tiempos unilaterales (total o por lado), sin duplicar automaticamente.
3. Rest scope: entre sets, despues del ultimo, entre ejercicios y si esta incluido en el tiempo de trabajo/nodo.
4. Transiciones entre ejercicios, mediante duracion explicita o una politica revisada/versionada; sin default numerico nuevo aqui.
5. Warmup/cooldown de fuerza como bloques explicitos o estado no prescrito, con duracion/fuente; UNKNOWN debe seguir distinto de cero.
6. Version de la politica temporal, confianza, datos utilizados, operaciones y resultado anterior/final para auditar cambios y evitar contar dos veces descansos.

Los campos existentes (orden, ejercicio/titulo/patron, sets/reps, descanso, unilateralidad, RPE) ya se guardan en el JSON de StructuredWorkout. La ampliacion temporal deberia conservarse junto a ese snapshot con version de schema/politica, no deducirse de la duracion asignada ni de notas libres. Una tabla nueva de ejercicios o grupos musculares no es requisito para estimar tiempo; el actual body_regions manual no puede reutilizarse como mapa automatico por ejercicio sin soporte adicional.

Mientras se define y valida eso, pueden seguir legacy: duracion historica/default, perfiles de fase, seleccion de ejercicios, repeticiones, descansos, RPE, capacidad, carga y frecuencia. No se ajusta resistencia para compensar una duracion desconocida de fuerza.

## Pruebas y equivalencia

20 casos nuevos: bytes/identidad de artefactos y workouts, determinismo con estimacion desconocida, fallback por estructura/reps/historico ausentes, perfiles BASE/BUILD/RECOVERY/TAPER/COMPETITION/SPECIFIC del builder real, dos sesiones identicas, rotacion/procedencia, ancla de distribucion, capacidad de una doble real, ausencia de precision inventada, inmutabilidad, aislamiento/rechazo de atleta/contexto ajeno y publicacion/limpieza efimera de la aplicacion con NULL y explicito.

La suite dirigida de fuerza + volumen4A/3 pasa. La auditoria ejecuta workers separados contra fuentes4A congeladas y actuales, sobre las MISMAS capturas, incluyendo ambas pasadas de adaptacion numerica si corresponde. Los bytes completos y fingerprints son identicos en cuatro escenarios: actualNULL, actualtarget6, referenciatarget6 y referencia con max_weekly6. Todos los modulos de dominio preexistentes mantienen su SHA256; solo se anade strength_intent.py y una llamada observacional en la aplicacion.

Ficheros nuevos: backend/app/domains/planning/strength_intent.py; backend/tests/test_strength_intent_shadow.py; backend/scripts/audit_structured_strength.py. Modificado: backend/app/application/planning_preview.py para el sidecar efimero. No hay cambios de UI, contrato API, schema persistido, workouts, metadatos de artefacto ni aceptacion.

Reproducir desde la raiz:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/audit_structured_strength.py
$env:TC_AUTH_MODE='development'; $env:TC_ENVIRONMENT='development'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_strength_intent_shadow.py -q -p no:cacheprovider
backend/.venv/Scripts/python.exe -m compileall -q backend/app backend/scripts/audit_structured_strength.py
git status --short
git diff --check
```

El replay es completamente offline: usa los input de4A, con captura actual as-of23/11/2026 y referencia09/11/2026. No consulta ni modifica la BD real. Los tests de aplicacion usan SQLite en memoria; no se invoca generate/accept en base real.

[Manifest baseline y status inicial](../informe/block4b-baseline/manifest.json), [validacion/fingerprints](../informe/block4b-validation.json), [checks finales](../informe/block4b-final-checks.json), [suite backend](../informe/block4b-backend.log), [git status --short](../informe/block4b-git-status.txt), [git diff --check](../informe/block4b-diff-check.txt).

Los cambios previos del repositorio se conservan. Sin activacion de duracion estructurada, cambios de datos reales, aceptacion de planes, staging, commit ni push.

Validacion final: suite backend completa1887 aprobados /8 warnings. Suite especifica final20 aprobados, incluyendo los ultimos ajustes de fallback para estructuras ausentes (igualdad desconocida y source de contenido no disponible). Suite dirigida fuerza + volumen de3/4A:46 aprobados. Los20 casos especificos estan incluidos en el total backend, no se suman como pruebas distintas. Compileall y git diff --check correctos. Frontend/TypeScript/build no se repiten: no hay cambios de UI ni del contrato API en4B.
