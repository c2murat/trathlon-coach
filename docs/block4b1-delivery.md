# TriCoach AI - Bloque 4B.1: estimador temporal independiente de fuerza

Version publicable. Los enlaces a informe/ remiten a evidencia privada local no distribuida. Las frases sobre ausencia de commits/push describen la entrega original; el estado Git actual figura en integral-consolidation-status.md.

Implementado exclusivamente en shadow. Ninguna salida alimenta SessionIntent, WorkoutBuilder, WeeklyDistribution, carga, capacidad o aceptacion. No se cambia la duracion legacy ni se generan datos temporales para conseguir cobertura completa.

Con las capturas existentes, todas las sesiones de fuerza devuelven coverage=unavailable, duration_seconds=null y validation_state=not_evaluated. El subtotal conocido es0 segundos porque no hay componentes temporales utilizables; ese cero NO es una duracion estimada de la sesion.

## Archivos de implementacion

- Nuevo: backend/app/domains/planning/strength_timing.py - contratos internos, binding, estimador y reporte observacional.
- Modificado: backend/app/application/planning_preview.py - import, propiedad efimera strength_timing_shadow_report, limpieza al comenzar generate y llamada final sin snapshots.
- Nuevo: backend/tests/test_strength_timing.py - 39 casos especificos.
- Nuevo: backend/scripts/audit_strength_timing.py - replay offline y comparacion completa de bytes/fingerprints.
- Informe y evidencias: docs/block4b1-delivery.md e informe/block4b1-*.

No se modifican schemas publicos, tablas, modelos de workout, contratos de API, contenido fingerprinted ni configuracion del planificador. Los cambios previos del workspace se conservan.

## Contratos temporales internos

Todos son FrozenModel, extra=forbid, con colecciones tuple.

| Contrato | Campos / validaciones |
|---|---|
| SecondsInterval | minimum/maximum: enteros estrictos no negativos, minimum<=maximum; unit literal seconds. Rechaza bool, floats, strings numericos, rangos invertidos y otras unidades |
| TimingProvenance | source: explicit_prescription / measured_segment / reviewed_timing_policy; source_id y version obligatorios, no vacios. No acepta allocated_seconds, RPE o historical_duration como fuentes |
| TimingComponent | unknown: sin intervalo/procedencia; specified: intervalo + procedencia; not_prescribed: procedencia obligatoria y sin intervalo. La ausencia no se deduce de un campo vacio |
| ExerciseTiming | node_path; execution_per_set con scope work_only_excluding_rest_and_setup; sets_scope; side_count explicito cuando corresponda; grupos de pausas |
| PauseTiming | after_sets no vacio, indices positivos, sin duplicados ni solapamiento entre grupos; scope between_execution_sets_only. Cada ocurrencia referencia un hueco concreto |
| TransitionTiming | Rutas adyacentes after_node_path/before_node_path; scope whole_gap_including_final_rest_and_setup; timing conocido, ausente o desconocido |
| StrengthTimingSnapshot | schema_version1 privada; policy_version; athlete_id; context_fingerprint; workout_fingerprint; definition_fingerprint; ejercicios, transiciones, warmup/cooldown y scope de extremos |
| StrengthTimingEstimate | coverage; duration_seconds min/max o null; known_subtotal_seconds; componentes conocidos con ocurrencias/procedencia; ausentes; diagnostics; validation_state independiente |

El snapshot NO se incrusta en StructuredWorkoutDefinition schema1. Tiene su propia identidad timing_snapshot_fingerprint y referencia al workout original. El hash adicional de la definicion detecta cambios en el arbol incluso si un objeto mutable conserva un fingerprint antiguo. Se usan esas huellas solo para binding: no participan en la aritmetica temporal.

Las rutas son tuplas de indices del arbol inmutable. En esta primera version solo se aceptan nodos planos steps[i] con phase=strength. Cada referencia debe existir. Las transiciones deben unir ejercicios consecutivos, sin saltos ni duplicados. El estimador vuelve a validar el snapshot al entrar, tambien si se creo usando model_copy.

## Ambito de series y unilateralidad

all_sides_included significa que cada unidad temporal incluye todos los lados de una serie completa; se usa node.sets una sola vez. No se multiplica por dos al ver unilateral=true.

per_side exige side_count positivo explicito y unilateral=true en el workout. node.sets se interpreta por lado, execution_per_set corresponde a una unidad de un lado y el numero normalizado de unidades es sets*side_count. Las pausas se refieren a la secuencia normalizada explicita. No se adivina side_count, ni el orden de pausas a partir de los nombres de ejercicios.

sets_scope=unknown no permite agregar el tiempo de ejecucion aunque alguien haya suministrado segundos por serie: se informa el alcance ausente. No se permite declarar pausas contra ese alcance aun sin resolver. La procedencia debe respaldar la interpretacion del protocolo; el contrato no verifica por si solo que una declaracion humana sea correcta.

## Componentes disjuntos y doble contabilizacion

La linea temporal tiene estos ambitos sin solapamiento:

1. Warmup: prefijo completo anterior a la primera unidad de trabajo, incluida preparacion inicial.
2. Ejecucion: trabajo exclusivamente; intervalo independiente por serie/unidad normalizada.
3. Pausas entre unidades del mismo ejercicio: identificadas mediante after_sets=1..N-1.
4. Entre ejercicios: un solo intervalo para TODO el hueco, incluido descanso tras la ultima serie y preparacion/transicion al siguiente ejercicio.
5. Cooldown: cola completa posterior a la ultima unidad de trabajo, incluidos descanso/preparacion finales si existen.

No se admite una pausa after_set=N: se solaparia con el hueco siguiente o con la cola final. Tampoco se acepta un campo de ejecucion que declare incluir descansos, ni dos transiciones para la misma frontera. Los grupos de pausas deben tener ocurrencias disjuntas. Si un protocolo no puede expresarse con estos ambitos, debe mantener legacy y devolver diagnostico, no adaptar silenciosamente la semantica.

El subtotal suma cada componente conocido UNA vez. Los segundos de KnownTimingComponent ya estan agregados para sus occurrences; no deben volver a multiplicarse al consumir el reporte. Los limites inferior y superior se suman por separado, sin asumir independencia estadistica y sin obtener punto medio, desviacion estandar o intervalo probabilistico.

## Cobertura y validacion

| Estado | Significado |
|---|---|
| complete | Todos los componentes aplicables tienen intervalo independiente o ausencia explicita respaldada. duration_seconds contiene la suma min/max |
| partial | Hay componentes temporales utilizables pero faltan otros. Solo se ofrece subtotal conocido; el total permanece null |
| unavailable | No hay componentes utilizables, la estructura no esta soportada o falla el binding/contrato. El total permanece null |

Un warmup not_prescribed explicito aporta un componente conocido de cero. Esto puede producir cobertura partial con subtotal0; no se confunde con unavailable ni con una sesion de duracion0. Si N=1 no hay huecos entre series: no se inventan pausas inexistentes; la cola final sigue requiriendo declaracion.

validation_state permanece not_evaluated incluso con coverage=complete. Validar contratos o disponer de todos los campos no demuestra precision predictiva. No hay confianza estadistica, porcentaje de bloqueo, estimacion central ni calibracion automatica. Los valores completos de las pruebas son fixtures sinteticos claramente etiquetados: nunca se trasladan a defaults, catalogos o atletas reales.

Si falla la identidad, una ruta, una ocurrencia o el contrato, no sobreviven valores parciales procedentes de esa entrada invalida. Los snapshots duplicados no se resuelven eligiendo uno: se informa DUPLICATE_WORKOUT_TIMING_SNAPSHOT y se invalida el resultado afectado. Los snapshots huerfanos se diagnostican y no se aplican.

## Ausencia de inferencias prohibidas

La aritmetica solo utiliza series declaradas, alcance explicito, side_count cuando esta declarado y los intervalos independientes proporcionados. Nunca utiliza:

- allocated_seconds ni duration.seconds del workout como tiempo de trabajo;
- RPE o un porcentaje asociado;
- presupuesto de minutos o de carga;
- duracion o media historica;
- rest_seconds del workout para inventar ocurrencias/tiempos no suministrados;
- defaults de calentamiento de resistencia.

El binding incluye toda la definicion, tambien sus segundos legacy, para detectar snapshots obsoletos. Esto no hace que esos segundos entren en el calculo. La prueba40 vs24 utiliza dos workouts con identidades distintas y los MISMOS datos temporales, vinculados expresamente a cada uno: la estimacion min/max es identica. Reutilizar el snapshot del workout40 sin actualizar su referencia al workout24 se rechaza como binding incorrecto.

## Estructuras no soportadas

- repeat, incluidos anidamientos: UNSUPPORTED_REPEAT_STRUCTURE; no se aplana el arbol para calcular pausas.
- Nodos planos con fases distintas de strength: UNSUPPORTED_FLAT_NODE_PHASE. Warmup/cooldown temporales se suministran como secciones del protocolo externo, sin anadir nodos al workout vigente.
- Estimacion de sesiones concurrentes, superseries o descansos solapados: no se modelan con esta suma disjunta.
- Mas de10000 unidades de ejecucion normalizadas: TIMING_OCCURRENCE_LIMIT_EXCEEDED, limite computacional que evita expansion descontrolada. No es un cap fisiologico ni una restriccion del planificador.

Ningun diagnostico bloquea la aceptacion actual ni cambia el fallback. El estimador no tiene ninguna salida de prescripcion ni llamada hacia el planificador.

## Integracion y comportamiento actual

PlanningPreviewApplication calcula strength_timing_shadow_report despues del ultimo pase de adaptacion numerica y despues de construir el artefacto, igual que los diagnosticos de4B. Se limpia al iniciar otra generacion. No se incluye en el JSON persistido, API, fingerprint o acceptance.

La aplicacion NO obtiene ni construye snapshots temporales a partir del historico. Invoca el reporte sin snapshots; todas las sesiones actuales resultan unavailable. La funcion interna permite suministrar snapshots explicitos para diagnostico, pruebas y futura captura autorizada, siempre sin escribir en la base de datos.

Resistencia, frecuencia, presupuestos y formulas de carga, fechas, preferencias, capacidad y perfiles de fuerza permanecen intactos. En las capturas de referencia siguen24 min; en las capturas del23/11/2026 siguen40 min. No se compensa ninguna discrepancia modificando resistencia.

## Pruebas e identidad

39 casos especificos cubren:

- rangos completos, subtotal parcial, unknown frente a cero y ausencia explicita;
- errores de unidades, negativos, rangos invertidos, bool/floats, procedencia ausente y fuentes prohibidas;
- independencia40/24, binding obsoleto y ausencia de uso de tiempos asignados;
- pausas duplicadas/solapadas, ultima serie, fronteras no adyacentes y rutas incorrectas;
- unilateralidad, alcance desconocido, numero de lados explicito y conflictos con el workout;
- repeat, fases BASE/BUILD/RECOVERY/TAPER/COMPETITION/SPECIFIC y limite de ocurrencias;
- determinismo/canonicalizacion, duplicados ambiguos, inmutabilidad y aislamiento multiatleta;
- ausencia de mutacion de artefactos/fingerprints, una doble swim+strength efectiva y capacidad;
- aplicacion NULL/explicita, reporte unavailable sin datos y limpieza despues de error.

La auditoria offline compara bytes completos y fingerprints contra el codigo congelado antes de4B.1. Incluye5 escenarios:

| Escenario | Fuerzas observadas | Cobertura actual | Dias con dobles | Identidad antes/despues |
|---|---:|---|---:|---|
| current-null | 92 | unavailable92 | 0 | Bytes y fingerprint identicos |
| current-target6 | 92 | unavailable92 | 3 | Bytes y fingerprint identicos |
| reference-target6 | 96 | unavailable96 | 3 | Bytes y fingerprint identicos |
| reference-race-cap | 96 | unavailable96 | 2 | Bytes y fingerprint identicos |
| double-target6 | 92 | unavailable92 | 49 | Bytes y fingerprint identicos |

current/reference son las capturas existentes de4A (23/11 y09/11/2026). double-target6 es una COPIA en memoria de current-target6 sin disponibilidad jueves, para ejercitar dobles: no es una preferencia guardada. Se comprueban minutos por slot y max_daily_sessions. Los horizontes contienen BASE, BUILD, MAINTENANCE, SPECIFIC y TAPER; RECOVERY/COMPETITION se prueban ademas con fixtures observacionales de fases.

La auditoria no lee la BD ni llama a generate/accept reales. Usa ambas pasadas de adaptacion numerica cuando corresponde. Todos los modulos de dominio previos y el contrato frontend se comparan por SHA256 y no cambian. Los unicos cambios de produccion son el modulo nuevo y su llamada efimera desde la aplicacion.

## Reproduccion y evidencias

Desde la raiz:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/audit_strength_timing.py
$env:TC_AUTH_MODE='development'; $env:TC_ENVIRONMENT='development'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_strength_timing.py -q -p no:cacheprovider
backend/.venv/Scripts/python.exe -m compileall -q backend/app backend/scripts/audit_strength_timing.py
git status --short
git diff --check
```

Suite completa desde backend: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp=.tmp_block4b1_verified`, con el mismo entorno de desarrollo de tests y sin editar .env. Usa fixtures y bases de prueba, no datos reales. Frontend no se modifica y no se repiten sus pruebas/build.

[Baseline congelada](../informe/block4b1-baseline/manifest.json), [comparacion de identidad y cobertura](../informe/block4b1-validation.json), [checks finales](../informe/block4b1-final-checks.json), [regresion backend](../informe/block4b1-backend.log), [status](../informe/block4b1-git-status.txt), [diff-check](../informe/block4b1-diff-check.txt).

## Limitaciones y siguiente paso

La procedencia declarada no verifica por si sola que una medicion sea correcta, que sus limites cubran la variacion real o que un autor no haya copiado tiempos legacy bajo otra etiqueta. El estimador valida estructura, identidades, unidades y ambitos; no certifica verdad empirica. Los rangos completos son sumas conservadoras condicionadas a los datos suministrados, no intervalos de confianza.

El siguiente paso es recoger y revisar snapshots independientes ligados a ejercicios concretos, delimitar trabajo/pausas/transiciones y extremos del protocolo, y acordar una validacion predictiva con medidas segmentadas independientes. Sus criterios deben definirse antes de evaluar precision; no se derivan de duraciones historicas totales. Hasta entonces, validation_state=not_evaluated y shadow exclusivamente.

Una futura activacion de duraciones requerira una decision separada y volver a comprobar las dobles/capacidad. No se implementa ni se anticipa esa activacion aqui. Sin cambios de datos reales, planes aceptados, staging, commit ni push.

Validacion final: regresion backend completa1926 aprobados /8 warnings. Suite especifica final39 aprobados (incluida comprobacion de orden irrelevante en snapshots duplicados ambiguos). La suite dirigida inicial fuerza4B + volumen4A + estimador paso71 casos; los39 nuevos ya forman parte del total backend y no se suman como pruebas distintas. Compileall y git diff --check correctos. No se modificaron schemas publicos y no se repitieron pruebas frontend/build. Los datos numericos independientes usados para casos complete/partial existen solo en fixtures de tests; ninguna captura real fue completada artificialmente.
