# TriCoach AI - Bloque 4B.3: Strength Temporal Prescription and Shadow Evaluation

Version publicable. Los enlaces a informe/ remiten a evidencia privada local no distribuida. Las frases sobre ausencia de commits/push describen la entrega original; el estado Git actual figura en integral-consolidation-status.md.

Politica interna implementada y evaluada SOLO EN SHADOW. No se activa duracion estructurada, no se alteran workouts, carga, presupuesto, volumen, fechas ni dobles. La politica no incorpora tiempos por repeticion, tempos, holds o transiciones sin respaldo.

Resultado de las capturas:468 salidas de fuerza pasan de unavailable a partial al disponer de descansos inter-series prescritos con alcance explicito. No hay ninguna sesion complete. Los subtotales no se presentan como duracion de sesion ni como prueba de que cabe en legacy/disponibilidad.

## Auditoria inicial

Se revisaron los informes4B.1/4B.2, strength_timing.py, strength_timing_inputs.py, strength_intent.py, WorkoutBuilder, WorkoutNode, SessionType, SeasonPhase, catalogo y configuraciones. Antes de editar se congelaron fuentes, hashes y status. Se conservaron todos los cambios pendientes.

| Tipo o estructura | Soporte real |
|---|---|
| Fuerza general | Unico rol de sesion GENERAL_STRENGTH; proposito GENERAL_STRENGTH y prioridad support |
| Fuerza maxima | No hay rol ni politica especifica implementada |
| Resistencia muscular | No hay clasificacion propia; no se etiqueta como tal por tener3x10 |
| Fuerza explosiva | No hay prescripcion de velocidad/potencia o rol especifico |
| Core | Patrones CORE_ANTI_EXTENSION y CORE_ANTI_ROTATION en el catalogo; no otro tipo de sesion |
| Estabilidad | Patrones unilaterales y core, sin politica temporal independiente denominada estabilidad |
| Movilidad | No hay sesion ni ejercicios de movilidad especificos en el catalogo actual |
| Isometricos | Entrada temporal explicita de4B.2; no se identifica automaticamente por el nombre ni se asigna hold al catalogo |
| Circuitos / superseries | Arbol publico repeat y declaraciones privadas secuenciales4B.2; el builder general actual no genera estos bloques |

El modelo enumera patrones de movimiento y el catalogo contiene dos variantes de seis ejercicios. No se amplian catalogo, roles ni tipos de objetivo. CORE_LATERAL aparece en los contratos/etiquetas, pero no se introduce un ejercicio nuevo para activarlo.

Fuentes verificables del diseno actual:

- [SessionType y metadata de fuerza](../backend/app/domains/planning/session_planning.py): GENERAL_STRENGTH y clasificacion support/moderate.
- [Builder de fuerza](../backend/app/domains/planning/workout_builder.py): _strength_steps y perfiles por fase.
- [Catalogo](../backend/app/domains/planning/workout_labels.py): STRENGTH_VARIANTS y patrones.
- [Contratos publicos](../backend/app/domains/planning/models.py): sets, reps, rest_seconds y unilateralidad.

El builder prescribe90 segundos de descanso en el perfil general/SPECIFIC y60 en RECOVERY/TAPER. Esos valores ya existen y son independientes del total legacy. Lo que faltaba era el alcance temporal. Los tiempos de ejecucion de nodos siguen siendo reparto del presupuesto legacy y NO son elegibles como fuente.

## Politica introducida y justificacion

Version: `0.8G.2E.1-strength-temporal-prescription-4b3`.

La politica prescribe este protocolo para diagnostico:

> En GENERAL_STRENGTH, para ejercicios de patrones ya presentes en el catalogo, explicitamente bilaterales y con mas de una serie, usar el rest_seconds de la prescripcion existente exclusivamente entre series completas, nunca despues de la ultima.

Es una DECISION PRESCRIPTIVA NUEVA DE ALCANCE, no una afirmacion de que ese fuera el alcance historico observado. Su respaldo numerico es el propio diseno de fuerza existente: series repetidas y campo rest_seconds ya prescrito. No se certifica que90/60 sean descansos optimos para el atleta ni se extrapolan a fuerza maxima, explosiva u otros tipos no implementados. No hay nuevos valores en segundos, ratios o porcentajes.

La seleccion distingue los objetivos existentes triathlon, duathlon, aquathlon, running, cycling y swimming mediante identificadores de politica trazables. No se inventan diferencias numericas entre deportes: el valor siempre procede del nodo especifico. La fase se conserva como contexto y ya esta reflejada en ese nodo por el builder; no se aplica un segundo factor de fase.

La politica se abstiene ante rol/fase/objetivo no soportado, patron no presente en catalogo o unilateralidad no resuelta. En nodos bilaterales de una sola serie el descanso inter-series es not_applicable, no unknown. Para unilaterales se exigen las fuentes especificas de4B.2: el generico no presupone que una serie contenga ambos lados.

Se mantiene desconocido todo lo que no tiene respaldo: ejecucion por repeticion, tempo, hold, orden de lados, transiciones, preparacion, extremos y gaps entre rondas. No se utiliza presupuesto semanal, carga, disponibilidad ni legacy para fabricar datos.

## Arquitectura, integracion y ficheros

Nuevo `backend/app/domains/planning/strength_timing_policy.py`:

- StrengthPolicyScope solo contiene role, phase y objectives; no admite legacy, carga, presupuesto o disponibilidad.
- select_strength_temporal_policy elige una politica determinista por alcance deportivo soportado.
- prescribe_strength_temporal_inputs crea/combina StrengthTimingInputs de4B.2, sin mutar el workout.
- build_strength_temporal_policy_shadow evalua sesiones del artefacto y compara con legacy DESPUES de estimar.
- StrengthLegacyComparison representa conclusiones permitidas segun cobertura.

Modificado `backend/app/application/planning_preview.py`: import, propiedad efimera strength_temporal_policy_report, limpieza al iniciar generate y calculo observacional despues del artefacto final. No se devuelve en la API, no se guarda en el artefacto/BD y no participa en acceptance. Los reportes previos de4B/4B.1 siguen disponibles e intactos.

Nuevos `backend/tests/test_strength_timing_policy.py`, `backend/scripts/audit_strength_temporal_policy.py`, este informe, docs/block4b3-shadow-matrix.md y evidencias informe/block4b3-*.

Los modulos de dominio anteriores, builder, calculadores, Strength Intent, Volume Intent, distribucion, schemas publicos, frontend y contratos mantienen sus hashes exactos. No se crea persistencia, migracion, endpoint ni sistema de circuitos.

## Procedencia y precedencia

Se mantienen diferenciados:

| Clase | Representacion |
|---|---|
| Prescripcion explicita existente | WorkoutNode.rest_seconds y cantidades sets/reps de un workout vinculado por fingerprint |
| Derivacion determinista | TimingProvenance.source=derived_prescription; cantidad por ocurrencias y referencias versionadas a nodo y alcance |
| Politica temporal prescriptiva | Scope provenance configurable_prescription, con policy_id/version4b3; ParameterDecision.source_kind=temporal_prescription_policy |
| Observado/medido | measured_segment solo cuando una entrada especifica valida lo declara; no se renombra como prescripcion ni valida empiricamente el total |
| Desconocido | Componente sin fuente suficiente, motivo de abstencion y missing_components; no cero |

Precedencia:

1. Snapshot temporal especifico validamente vinculado: conserva la propiedad de su ruta. No se mezclan silenciosamente componentes en esa ruta.
2. Entrada especifica de4B.2: preserva tiempo, tempo, modalidad, gaps y descansos definidos. Un descanso especifico vence al generico.
3. Politica generica: completa solo un descanso aun sin propietario y elegible.
4. Sin respaldo: unknown.

Fuentes especificas competidoras, duplicadas, huerfanas o con binding/estructura invalidos se rechazan explicitamente; no se elige por orden ni se sustituye la fuente invalida con un default. Una fuente observada se conserva como tal en las decisiones; las operaciones sobre prescripciones/mediciones se siguen etiquetando como derivaciones, no como tiempo total observado.

El generico tampoco sobreescribe un valor especifico del workout con90/60: si el nodo prescribe45, usa45 bajo el alcance admitido. Las pruebas verifican esa ausencia de constante universal.

## Evaluacion y comparacion diagnostica

Cada StrengthTemporalEvaluation incluye fecha/fase, politica/version/contexto, decisiones por nodo, estimacion4B.1/4B.2, componentes conocidos con procedencia, ausentes, no aplicables y motivos de cobertura insuficiente. La duracion legacy se lee al final, solo para comparar.

| Cobertura | Comparacion permitida |
|---|---|
| complete | Legacy inferior, dentro o superior al intervalo. Distancia firmada a la frontera mas cercana: negativa por debajo, cero dentro, positiva por encima |
| partial y legacy<subtotal_min | Solo se demuestra que los componentes disjuntos conocidos ya exceden legacy. Se informa minimo deficit; total y distancia a un intervalo completo siguen desconocidos |
| partial con legacy>=subtotal_min | INDETERMINATE_PARTIAL. No demuestra que la sesion completa quepa, aunque el subtotal entero sea menor que legacy |
| unavailable | No hay comparacion temporal valida |
| Legacy ausente | LEGACY_UNKNOWN |

No se calcula punto medio, confianza estadistica, umbral porcentual o ajuste automatico. validation_state permanece not_evaluated. Los intervalos completos pueden tener extremos iguales por una prescripcion exacta; eso no convierte el valor en una observacion.

Ejemplos SOLO sinteticos:

- Dos series de5 reps, tiempo[2,3]s/repeticion, descanso especifico10 y extremos explicitamente ausentes: intervalo[30,40]s. Legacy20 esta por debajo,35 dentro y50 por encima; distancias-10/0/+10s.
- Sin ejecucion conocida, un descanso prescrito90s entre dos series aporta subtotal90. Legacy60 esta por debajo del minimo conocido: deficit al menos30s; el total sigue desconocido.
- Con ese mismo subtotal, legacy1000 NO demuestra que toda la sesion cabe; resultado INDETERMINATE_PARTIAL.
- Un tempo explicito2+0+1+0s/repeticion con2x5 y descanso10 produce40s, usando la entrada especifica, no una asignacion generica del tempo.
- Holds, tiempos por serie, unilateralidad, circuitos/superseries y transiciones siguen los inputs explicitos de4B.2. El generico no crea esos valores.

## Ausencia de circularidad

El selector recibe un contrato sin variables de presupuesto. La prescripcion usa solo el diseno del workout, cantidades/rest explicitamente prescritos y fuentes especificas independientes. Los hashes de binding incluyen la definicion completa para detectar referencias obsoletas, pero no entran en las operaciones temporales.

La prueba correspondiente modifica legacy24/40, segundos asignados a nodos, duracion/carga historicas, target_load, disponibilidad1/5000 y presupuesto semanal1/9999, manteniendo identico el diseno deportivo. La politica elegida y el subtotal/intervalo independiente permanecen iguales. La identidad de los objetos sinteticos se vuelve a vincular cuando cambian contexto/definicion; no se reutilizan snapshots obsoletos.

La comparacion con legacy puede cambiar porque es POSTERIOR. Nada de esa comparacion vuelve al selector, al snapshot, al planner o a la duracion efectiva.

## Matriz de las468 salidas

[Tabla agregada por escenario](block4b3-shadow-matrix.md), [detalle por sesion](../informe/block4b3-session-matrix.json), [contadores y hashes](../informe/block4b3-validation.json).

Son468 evaluaciones temporales de fuerza de los mismos cinco escenarios, no468 observaciones empiricas independientes ni todas las sesiones de resistencia del plan.

| Escenario | Fuerza | Antes complete/partial/unavailable | Despues | Comparaciones | Identidad |
|---|---:|---|---|---|---|
| current-null | 92 | 0/0/92 | 0/92/0 | 92 indeterminadas parciales | Bytes/FP identicos |
| current-target6 | 92 | 0/0/92 | 0/92/0 | 92 indeterminadas parciales | Bytes/FP identicos |
| reference-target6 | 96 | 0/0/96 | 0/96/0 | 96 indeterminadas parciales | Bytes/FP identicos |
| reference-race-cap | 96 | 0/0/96 | 0/96/0 | 96 indeterminadas parciales | Bytes/FP identicos |
| double-target6 | 92 | 0/0/92 | 0/92/0 | 92 indeterminadas parciales | Bytes/FP identicos |
| Total | 468 | 0/0/468 | 0/468/0 | 468 INDETERMINATE_PARTIAL | Cinco escenarios identicos |

Datos conocidos despues:

- 2071 nodos bilaterales reciben alcance de descanso entre series:2056 con90s y15 con60s, valores tomados de sus prescripciones.
- Esos nodos producen4127 componentes/ocurrencias de descanso conocidos:4112 de90s y15 de60s.
- La politica general-strength/triathlon/bilateral-inter-set-rest se aplica a las468 sesiones; su version queda registrada.
- Subtotales observados en estas capturas:60,120,540,720 o900 segundos segun fase/variante. Son solo descanso prescrito bajo el protocolo, no duracion estimada completa.

Componentes aun desconocidos:

- Ejecucion de2768 nodos.
- Alcance/ocurrencias de descanso de697 nodos unilaterales; no se presume agrupacion por lado.
- 2300 huecos entre ejercicios.
- 468 prefijos de calentamiento/preparacion y468 colas finales.

No se detectan IDs de componente duplicados dentro de una estimacion. Hay0 comparaciones completas con legacy y0 casos en que el minimo conocido exceda legacy en estas capturas. No se afirma que la sesion quepa; todas las comparaciones son indeterminadas. No se detecta una desviacion total medible porque falta ejecucion y otros componentes. Los tests sinteticos cubren las tres posiciones respecto a un intervalo y el deficit parcial.

Las capturas son las previamente congeladas as-of23/11 y09/11/2026; no se han consultado datos nuevos ni modificado preferencias reales. double-target6 es una copia con jueves no disponible, no un cambio persistido. Se vuelven a comprobar max_daily_sessions y minutos por slot; se conservan los0/3/3/2/49 dias con dobles de los cinco escenarios.

## Pruebas

34 casos nuevos cubren los28 apartados solicitados, apoyados por los69 casos especificos anteriores:

- Selector determinista, seis objetivos deportivos existentes y politica no aplicable.
- Tempo, tiempo por serie/isometrico y unilateralidad explicitos; no inferidos por nombres.
- Descansos especificos, valor especifico de nodo y ausencia de defaults universales.
- Circuitos/superseries secuenciales y transiciones de fuentes4B.2.
- Precedencia, medicion frente a prescripcion, procedencia/version, error en fuentes invalidas, duplicadas y huerfanas.
- Cobertura complete/partial/unavailable y componentes no aplicables.
- Legacy inferior/dentro/superior y alcance limitado de comparaciones parciales.
- Ausencia de circularidad para todas las variables prohibidas.
- Una doble real swim+strength con capacidad y bytes intactos.
- Artefacto/workout/fingerprint intactos, rutas NULL/explicita, reporte efimero y limpieza tras error.

La suite dirigida de politica +4B.1+4B.2 pasa103 casos. La regresion completa incluye planificacion, fuerza, volume intent, distribucion, carga, previews y C.1 existentes. No se modifica UI/API y no se repiten tests/build frontend.

## Archivos y reproduccion

Nuevos: strength_timing_policy.py, test_strength_timing_policy.py, audit_strength_temporal_policy.py, docs/block4b3-delivery.md y docs/block4b3-shadow-matrix.md. Modificado: PlanningPreviewApplication para el sidecar efimero. No se modifican los motores4B.1/4B.2.

Desde la raiz:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/audit_strength_temporal_policy.py
$env:TC_AUTH_MODE='development'; $env:TC_ENVIRONMENT='development'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_strength_timing_policy.py backend/tests/test_strength_timing.py backend/tests/test_strength_timing_inputs.py -q -p no:cacheprovider
backend/.venv/Scripts/python.exe -m compileall -q backend/app backend/scripts/audit_strength_temporal_policy.py
git status --short
git diff --check
```

Suite backend completa desde backend: `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp=.tmp_block4b3_verified`, con entorno de desarrollo solo en el proceso de pruebas; no se edita .env.

[Baseline/status inicial](../informe/block4b3-baseline/manifest.json), [validacion de escenarios](../informe/block4b3-validation.json), [checks finales](../informe/block4b3-final-checks.json), [backend](../informe/block4b3-backend.log), [git status](../informe/block4b3-git-status.txt), [git diff --check](../informe/block4b3-diff-check.txt).

## Limitaciones, riesgos y propuesta4B.4

La interpretacion entre-series es una prescripcion temporal versionada para el alcance admitido, no una medicion del comportamiento real ni una validacion de que el campo unilateral del catalogo describa toda la ejecucion. Los parametros especificos requieren fuentes confiables; las etiquetas de procedencia no autentican por si solas una medicion.

El catalogo actual no dispone de respaldo para nuevos tempos, tiempos por rep, holds o tiempos de preparacion. No se han introducido para aumentar cobertura. No hay politica de fuerza maxima, explosiva o movilidad. Tampoco se obtiene evidencia empirica a partir del presupuesto o de la duracion historica.

Los snapshots especificos reservan la propiedad de su ruta; no se hace una fusion implicita que pueda duplicar pausas. Los bloques simultaneos o los alcances por lados sin semantica suficiente siguen sin total completo. Partial no es una estimacion de la sesion completa y no permite concluir ajuste a disponibilidad.

Propuesta4B.4, NO implementada: revisar el protocolo prescriptivo con fuentes deportivas de alcance especifico, capturar entradas/segmentos independientes con identidad verificable y acordar criterios de validacion antes de evaluar precision. Incorporar solo parametros justificados; mantener la comparacion diagnostica separada. Una eventual activacion de duraciones requerira otra decision y revalidacion de capacidad/dobles, nunca una consecuencia automatica de esta matriz.

Sin nuevas duraciones efectivas, cambios de datos reales, planes aceptados, staging, commit ni push. No se adelanta4B.4.

## Validacion final

Regresion backend: **1990 passed, 8 warnings** (367.44 s). Suite dirigida: **103 passed**, incluidos **34 casos nuevos**. Compileall y git diff --check finalizan con codigo 0. Los 27 archivos protegidos mantienen sus hashes originales; los cinco escenarios mantienen identidad byte a byte de artefactos y fingerprints. El diff de la integracion efimera se conserva en [block4b3-application.diff](../informe/block4b3-application.diff).
