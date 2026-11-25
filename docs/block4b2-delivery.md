# TriCoach AI - Bloque 4B.2: Independent Strength Timing Inputs

Version publicable. Los enlaces a informe/ remiten a evidencia privada local no distribuida. Las frases sobre ausencia de commits/push describen la entrega original; el estado Git actual figura en integral-consolidation-status.md.

Implementado exclusivamente en shadow. Los inputs independientes se compilan al MISMO snapshot/estimador de4B.1; no se crea otro motor de agregacion ni se cambia ningun workout. No se anaden defaults temporales ni se cargan valores sinteticos en sesiones reales.

## Auditoria inicial y fuentes

Se revisaron docs/block4b1-delivery.md, strength_timing.py, strength_intent.py, los contratos WorkoutNode/WorkoutDuration/StructuredWorkoutDefinition, el builder de fuerza, la configuracion y las pruebas existentes. Se congelo el estado previo antes de editar; se conservaron todos los cambios pendientes del workspace.

| Dato | Clasificacion | Uso permitido en4B.2 |
|---|---|---|
| Sets, reps fijas, orden, unilateralidad, repetitions de repeat | Explicitos en la prescripcion | Conteos estructurales; nunca segundos por si solos |
| rest_seconds60/90 del perfil de fuerza | Duracion explicita, alcance desconocido | Solo con SetRestInput.from_prescription y procedencia de una politica que declare entre-series y excluya descanso final |
| RPE5-7 /4-6, intensidad y nombre/patron | Explicitos no temporales | No se utilizan para deducir tiempo |
| duration.seconds de nodos de fuerza | Derivado del total legacy mediante divmod | No elegible como evidencia independiente |
| Duracion legacy/historico, presupuesto semanal/carga, disponibilidad | Fuentes del motor vigente | No elegibles como evidencia temporal |
| Defaults de warmup/cooldown del builder | Parametros configurables de otras ramas | No se aplican automaticamente a fuerza; la rama strength no los usa |
| Tiempo por repeticion, tempo, hold/per-set | No disponibles en el builder actual | Nuevos contratos internos para datos explicitos o parametros prescriptivos versionados; por defecto UNKNOWN |
| Tiempo derivado de reps y tiempo independiente por rep | Derivado determinista de inputs explicitos | Intervalo reps_min*time_min .. reps_max*time_max; sin promedio |
| Transiciones/preparacion y descanso entre lados/rondas | No tienen alcance suficiente en los datos actuales | Inputs explicitos con propietario y relacion temporal declarados |
| Tiempo medido segmentado | No cargado por este bloque | Se admite procedencia measured_segment sin convertirlo en validacion estadistica del total |

No se encuentran tempos ni tiempos independientes que permitan asignar valores automaticamente a las capturas actuales. Un dato configurable no se presenta como una observacion del atleta. No se interpretan notas libres ni nombres de ejercicios.

## Arquitectura y archivos

Nuevo `backend/app/domains/planning/strength_timing_inputs.py`:

- StrengthTimingInputs agrupa una referencia/snapshot4B.1 y entradas por ruta de nodo.
- compile_strength_timing_inputs valida, normaliza unidades/alcances y devuelve TimingInputCompilation: input inmutable original, snapshot compilado y diagnosticos.
- estimate_strength_timing_inputs reutiliza estimate_strength_timing para calcular subtotal/total.
- build_strength_timing_inputs_shadow permite observar inputs de varios workouts dentro del artefacto, sin modificarlo.

Modificado `backend/app/domains/planning/strength_timing.py`:

- Extiende la procedencia y componentes privados con configurable_prescription, derived_prescription, partial y not_applicable.
- Incorpora gaps internos por serie, declaraciones de repeat y referencias a nodos de extremos.
- Reutiliza el mismo acumulador de componentes disjuntos para estructuras secuenciales repetidas, incluidas anidadas.
- Conserva compatibilidad de snapshots privadosv1; el compilador genera v2 con policy_version calificada y el resultado identifica algoritmo4b2.

Nuevos: `backend/tests/test_strength_timing_inputs.py`, `backend/scripts/audit_strength_timing_inputs.py`, este informe y evidencias informe/block4b2-*.

No se modifica PlanningPreviewApplication, Strength Intent, Volume Intent, carga, WeeklyDistribution, WorkoutBuilder, schemas publicos, API, frontend, modelos persistidos ni migraciones. La aplicacion continua observando sin inputs independientes; no hay importador a BD, endpoint ni activacion de nuevos minutos.

## Contratos implementados y procedencia

Se reutilizan SecondsInterval, TimingComponent, TimingProvenance, ExerciseTiming, PauseTiming, TransitionTiming y StrengthTimingSnapshot. Los nuevos contratos son inputs prescriptivos, no otra representacion del total temporal.

| Contrato | Semantica y validacion |
|---|---|
| ExerciseExecutionInput | Modo unknown/repetitions/timed/isometric, ruta, fuente temporal unica, alcance y orden de lados. No deduce modo del nombre. Alcances conocidos requieren scope_provenance |
| RepetitionRange | Enteros positivos estrictos min<=max, unidad repetitions y procedencia. Solo complementa reps desconocidas; no contradice reps fijas del workout |
| TempoInput | Cuatro fases explicitas: excentrica, pausa inicial, concentrica, pausa final. Unidad seconds_per_full_repetition. Cada fase conserva known/unknown y procedencia. No se parsean tempos libres ni X como un numero |
| SetRestInput | Tiempo explicito o lectura de rest_seconds con politica de alcance; ambas fuentes no pueden competir. Entre series completas, sin descanso final |
| GapTimingInput | Hueco completo o desglose rest/transition/preparation. Exige relacion disjoint o included_in_rest con procedencia; unknown no permite asumir suma |
| BoundaryTimingInput | Rutas de unidades consecutivas; hueco entre ejercicios/bloques, incluidos material y estaciones |
| RepeatTimingInput | Reutiliza RepeatTiming del snapshot. Declara secuencia y rol descriptivo circuit/superset/sequence; rondas proceden del repeat existente |
| EdgeTimingInput | Vincula datos independientes al nodo warmup/cooldown existente, sin leer su tiempo asignado como evidencia |
| TimingProvenance ampliado | Distingue explicito, medido, politica revisada, configurable y derivado. Derived requiere operacion y referencias a inputs con version; se conservan las referencias de fuentes originales |

Todas las colecciones son inmutables. Se rechazan rutas duplicadas, fuentes de ejecucion incompatibles, rango invertido, unidades ambiguas, enteros falsos/bools, conflictos de reps, binding ajeno y procedencia ausente. El snapshot ya poblado no se sobrescribe silenciosamente: un input para una ruta/fuente ya ocupada se rechaza.

El compilador no inventa procedencia si faltan fuentes. Los valores de escenarios sinteticos existen solo en tests. La configuracion temporal puede representarse con source=configurable_prescription y source_id/version, pero este bloque no incorpora una tabla de valores por defecto ni asigna parametros a atletas.

## Repeticiones, tiempos e isometricos

Para un ejercicio por reps, el conteo puede proceder de WorkoutNode.reps o de RepetitionRange explicitamente prescrita cuando reps no existe. Un tiempo independiente por repeticion, o la suma de fases de un tempo explicito, permite derivar el intervalo por serie. Las fases desconocidas se mantienen ausentes; sus partes conocidas pueden aportar subtotal, nunca un total completo.

Timed e isometric usan un intervalo independiente por serie. No se identifica un isometrico por el titulo, patron, RPE o segundos asignados. Los alcances temporales deben indicar si el tiempo incluye todos los lados o una unidad de un lado. Las partes de ejecucion excluyen descanso y preparacion.

Los segundos son enteros y sus intervalos no negativos; trabajo completo debe ser positivo. Los ceros explicitos se admiten en pausas/transiciones/fases, con procedencia, y no equivalen a desconocido. No se obtiene un tiempo universal por repeticion.

## Unilateralidad y orden

Reps totales + counted_cycle usa el numero total de ciclos declarados una vez. No admite side_count para multiplicar esos reps. Reps por lado requiere side_count explicito:

- Successive + single_side: suma las unidades de cada lado.
- Simultaneous + simultaneous_cycle: el tiempo suministrado ya cubre el ciclo simultaneo; no vuelve a multiplicarse por lados.
- Semantica desconocida: componente de ejecucion desconocido.

Para ejecucion sucesiva tambien debe declararse side_sequence:

- within_each_set: cada serie completa agrupa sus lados. Se separan trabajo, huecos internos de cambio de lado y descansos entre series completas. El snapshot compilado marca all_sides_included para evitar que el core multiplique los lados otra vez.
- all_sets_per_side: se hacen las series de un lado y despues las del siguiente. Se reutiliza per_side de4B.1 y se generan ocurrencias disjuntas para descansos dentro de cada lado y gaps entre lados.
- unknown: se preserva el trabajo conocido cuando es seguro, pero pausas/orden permanecen desconocidos; no hay total completo.

Cuando reps son totales y no hay un numero de grupos de lado conocido, las ocurrencias del gap interno deben declararse explicitamente. No se deducen de unilateral=true. Un solo grupo declarado no tiene cambio de lado: not_applicable queda distinguido de unknown y de una duracion cero prescrita.

## Descansos, transiciones y extremos

Un descanso de10 segundos entre3 series produce DOS ocurrencias, no tres. La ultima pausa pertenece al hueco de la siguiente unidad o a la cola de la sesion. No se extrapola un descanso posterior que no este prescrito.

GapTimingInput representa cambios de ejercicio/material, preparacion de estaciones, cambios de lado y otros huecos explicitos:

- whole aporta una unica fuente para todo el hueco; no admite otro desglose competitivo.
- disjoint suma solo las partes declaradas disjuntas. Si falta alguna, conserva subtotal partial.
- included_in_rest usa el contenedor rest UNA vez; no suma otra vez transition/preparation. Se detectan componentes que exceden un contenedor completo conocido. Un subtotal partial no se confunde con un limite superior del contenedor entero.
- unknown no decide si partes se solapan y no fabrica un total para ese hueco.

Para warmup/cooldown se inspecciona la existencia de nodos. Se admite una fuente global para el prefijo/cola O una fuente vinculada al nodo correspondiente, no ambas conocidas. Los nodos deben estar en los extremos y ser unicos para esta version. Una ausencia declarada no puede negar un nodo existente. Nunca se toma su duration.seconds automaticamente: ese campo no aporta por si solo procedencia temporal independiente.

## Circuitos y superseries

Se usa exclusivamente WorkoutNode.kind=repeat, su lista steps y repetitions existentes. No se modifica el schema publico ni se genera un nuevo circuito.

Cuando RepeatTiming declara sequential con procedencia:

- Se repiten los componentes internos y las transiciones de cada ronda.
- El gap entre rondas ocurre R-1 veces, nunca despues de la ultima.
- Se soportan anidamientos con multiplicadores trazables y ocurrencias acotadas.
- Un limite computacional de10000 unidades/32 niveles evita expansion descontrolada; no es una regla fisiologica ni un cap del planificador.

Simultaneous en BLOQUES/circuitos no esta suficientemente especificado por el schema actual (no hay sincronizacion, barreras o fin de conjunto). Se devuelve UNSUPPORTED_SIMULTANEOUS_BLOCK y no se suma como secuencial ni se inventa max(tiempos). Esto es distinto del ciclo simultaneo POR LADOS explicitamente temporizado de una misma unidad de ejecucion.

Un bloque sin orden temporal conocido genera AMBIGUOUS_REPEAT_ORDER. Se conservan componentes seguros fuera de ese bloque y el resultado es partial o unavailable. Los inputs internos ignorados por semantica ambigua siguen disponibles en la compilacion, pero no se contabilizan como tiempo disjunto conocido.

## Ejemplos sinteticos de calculo

Estos numeros son fixtures de tests, NO parametros reales ni defaults. Los extremos de sesion estan explicitamente no prescritos cuando el ejemplo no los incluye.

| Caso sintetico | Calculo | Resultado |
|---|---|---|
| Reps | 2 series x5 reps x[2,3] s +1 descanso10 | [30,40] s complete |
| Tempo | (2+0+1+0) s/repeticion x5 x2 +10 | [40,40] s complete |
| Por tiempo / isometrico | 2 series x[20,25] s +10 | [50,60] s complete |
| Variable, reps ausentes en workout | 2 x[4,6] reps x[2,3] s +10 | [26,46] s complete |
| Unilateral, lados dentro de cada serie | 2x5x2s x2lados +2 cambios3s +1 descanso10 | [56,56] s complete |
| Unilateral, todas las series por lado | 4 unidades x10s +2 descansos10s +1 cambio3s | [63,63] s complete |
| Unilateral simultaneo | 2 series x5 ciclos x2s +10; el ciclo ya incluye ambos lados | [30,30] s complete |
| Gap disjunto | descanso20 +transicion5 +preparacion3 | [28,28] s |
| Mismos subcomponentes incluidos en descanso | Contenedor descanso20, sin sumar otra vez5+3 | [20,20] s |
| Circuito/superset secuencial | 3 rondas x(10+4+10) +2 gaps7 | [86,86] s complete |
| Anidado | 3 rondas de2 unidades10, gap interno3 por ronda exterior y dos gaps5 | [79,79] s complete |
| Falta el gap exterior anterior | 60 trabajo +9 gaps internos; gap exterior desconocido | subtotal69, total null, partial |

No se calcula punto medio ni confianza estadistica. validation_state permanece not_evaluated, tambien con datos completos. Tiempo prescrito/configurado no se etiqueta como comportamiento medido del deportista.

## Matriz de cobertura de requisitos

| Requisito | Evidencia en pruebas |
|---|---|
| 1 Reps con tiempo | explicit_repetitions_and_no_time_source |
| 2 Reps sin tiempo | mismo caso y unknown_mode_cannot_guess |
| 3 Por tiempo | explicit_timed_or_isometric_set[timed] |
| 4 Isometrico | explicit_timed_or_isometric_set[isometric], single_side |
| 5 Por lado | unilateral_per_side_successive, successive_side_order |
| 6 Reps totales | unilateral_total_reps |
| 7 Unilateral desconocido | unknown semantics / unknown side order |
| 8 Entre series | explicit_scope_can_use_prescribed_rest |
| 9 Sin descanso final | mismo caso, circuitos y reglas4B.1 |
| 10 Entre ejercicios | gap_transition_setup_disjoint_or_included |
| 11 Transiciones | gap_transition_setup, edge_nodes |
| 12 Incluidas en descanso | included_no_double_count y container bounds |
| 13 Warmup/cooldown | explicit_edge_nodes_are_not_counted_twice |
| 14 Circuitos/superseries | existing_repeat_with_explicit_sequential_rounds[roles] |
| 15 Ambiguos | temporally_ambiguous_blocks, outside_components |
| 16 Complete | bounds de escenarios explicitos |
| 17 Partial | partial_tempo, partial_gap, nested_round_rest |
| 18 Unavailable | unknown_mode, inputs ausentes y capturas reales |
| 19 Cero/unknown/no aplicable | zero_absence_unknown, single_side sin cambio |
| 20 Rangos invalidos | invalid_inputs, invalid_units, regresiones4B.1 |
| 21 Procedencia | tempo_units_semantics_and_provenance, scope required |
| 22 Determinismo | no_circular_dependency_and_determinism y canonicalizacion4B.1 |
| 23 Independencia legacy | 40_vs24_and_target_rpe_names_do_not_supply_evidence |
| 24 Sin doble cuenta | lados, scope, gaps, edges, ultima ronda y pruebas4B.1 |

Pasan30 casos nuevos y la suite dirigida total89 (30 inputs +39 de4B.1 +20 de4B). Los tests existentes de fuerza4A/volumen/distribucion permanecen en la regresion backend completa. Los tests sinteticos no modifican entrenamientos reales.

## Identidad y comportamiento efectivo

La auditoria offline repite los cinco escenarios de4B.1 contra la baseline congelada antes de4B.2:

| Escenario | Sesiones de fuerza | Cobertura con datos existentes | Dias con doble | Bytes/fingerprint |
|---|---:|---|---:|---|
| current-null | 92 | unavailable92 | 0 | Identicos |
| current-target6 | 92 | unavailable92 | 3 | Identicos |
| reference-target6 | 96 | unavailable96 | 3 | Identicos |
| reference-race-cap | 96 | unavailable96 | 2 | Identicos |
| double-target6 | 92 | unavailable92 | 49 | Identicos |

Son las capturas existentes as-of23/11 y09/11/2026. double-target6 cambia disponibilidad jueves SOLO EN UNA COPIA de contexto para ejercitar capacidad. No se consulta ni modifica la BD real. Se comprueban minutos por slot, max_daily_sessions y dos pasadas de adaptacion numerica cuando corresponden.

Las468 salidas de fuerza siguen unavailable sin inputs independientes; no se han completado para obtener complete. Los40/24 min legacy, carga, presupuesto, targets, fechas, contenido y dobles siguen exactamente iguales, incluidos todos los bytes del artefacto. Los snapshots privados pueden tener una identidad distinta al incorporar evidencia/version nueva; esa identidad no se introduce en el fingerprint del plan.

Los hashes de todos los modulos previos excepto strength_timing.py permanecen iguales, incluidos PlanningPreviewApplication, WorkoutBuilder, Strength Intent, Volume Intent, WeeklyDistribution, modelos publicos y contrato frontend. Solo cambian componentes del subsistema temporal privado y ficheros nuevos de pruebas/auditoria/documentacion.

## Validacion y reproduccion

Desde la raiz:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/audit_strength_timing_inputs.py
$env:TC_AUTH_MODE='development'; $env:TC_ENVIRONMENT='development'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_strength_timing_inputs.py backend/tests/test_strength_timing.py backend/tests/test_strength_intent_shadow.py -q -p no:cacheprovider
backend/.venv/Scripts/python.exe -m compileall -q backend/app backend/scripts/audit_strength_timing_inputs.py
git status --short
git diff --check
```

Suite completa desde backend: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp=.tmp_block4b2_verified`, con entorno de desarrollo solo en el proceso de pruebas, sin editar .env. No cambia UI/API/contrato frontend, por lo que no se repiten TypeScript/frontend/build.

[Baseline y estado inicial](../informe/block4b2-baseline/manifest.json), [identidad/cobertura de cinco escenarios](../informe/block4b2-validation.json), [checks finales](../informe/block4b2-final-checks.json), [backend](../informe/block4b2-backend.log), [status](../informe/block4b2-git-status.txt), [diff-check](../informe/block4b2-diff-check.txt).

## Limitaciones, riesgos y propuesta4B.3

La procedencia declarada necesita una fuente confiable y revision: el tipo no certifica que los parametros describan la ejecucion real. Complete significa componentes conocidos bajo el protocolo declarado; no significa precision empirica validada. No se calibra tempo por atleta ni se ajustan datos a los minutos legacy.

La representacion inicial admite un nodo warmup inicial y uno cooldown final; ubicaciones multiples/intermedias son ambiguas y se rechazan. Bloques simultaneos sin semantica de sincronizacion permanecen parciales/desconocidos. La ampliacion no importa de forma automatica fuentes externas ni decide politicas de descansos.

Propuesta para4B.3, NO implementada: definir como capturar/revisar inputs independientes reales con identidad y versiones, validar los alcances sobre protocolos concretos y acordar evaluacion contra mediciones segmentadas. Revisar por separado la representacion de concurrencia si se necesita. No basta con asignar un tempo global ni comparar contra el presupuesto historico.

No se activa duracion estructurada ni se adelanta4B.3. No se modifican datos reales ni se aceptan planes. Sin staging, commit ni push.

Resultado final:1956 tests backend aprobados /8 warnings. Suite especifica nueva30 aprobados; dirigida con4B.1 y4B:89 aprobados. Los30 casos nuevos estan incluidos en el total, no se suman de nuevo. Compileall y git diff --check correctos. Las comparaciones byte a byte de los cinco escenarios pasan. No se repiten frontend/TypeScript/build porque no cambian UI, API ni sus contratos.
