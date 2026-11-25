# TriCoach AI - Bloque 4B.4

Version publicable: identidad y fechas de capturas omitidas; originales y evidencias detalladas se conservan solo localmente, fuera de Git. Los enlaces a informe/ designan evidencia local no distribuida.

Implementado exclusivamente en shadow mediante auditoria reproducible y ampliacion de pruebas de reconciliacion. **No hay justificacion suficiente para seleccionar tiempos de ejecucion nuevos con el contexto actual.** Se conserva integramente la politica 4B.3, su version y el motor temporal 4B.1/4B.2. No se rellena el snapshot para mejorar artificialmente la cobertura.

## Estado revisado y archivos

Se revisaron las entregas 4B.1, 4B.2 y 4B.3, su matriz, contratos, estimador, compilador de inputs, politica, Strength Intent, builder, catalogo, perfiles deportivos, pruebas y capturas. Se congelo el estado del workspace, diff y hashes antes de editar: [baseline](../informe/block4b4-baseline/manifest.json), [status](../informe/block4b4-baseline/status.txt), [diff previo completo](../informe/block4b4-baseline/diff.txt). Los cambios anteriores no forman parte de este bloque y permanecen intactos.

Archivos nuevos de implementacion:

- `backend/scripts/audit_strength_temporal_completion.py`: replay de los cinco escenarios, comparacion contra 4B.3, clasificacion diferenciada de faltantes, agrupaciones y matriz con procedencia. Version del auditor `strength-temporal-completion-audit-4b4-v1`.
- `backend/tests/test_strength_temporal_completion.py`: 22 casos nuevos sobre fronteras de reconciliacion, inputs explicitos, extremos desconocidos, unilateralidad/solapamientos y clasificacion.
- `docs/block4b4-delivery.md` y `docs/block4b4-shadow-matrix.md`.
- Evidencias `informe/block4b4-*`, incluidos 5 artefactos, 5 reportes temporales, matriz detallada y validaciones.

Ningun archivo de aplicacion, dominio, schema, API, frontend, BD o migracion se modifica en este bloque. No hay otro estimador ni otro modelo de inputs. El auditor consume los contratos existentes; nunca alimenta el planificador.

## Auditoria de las 468 evaluaciones

Las 468 salidas siguen siendo partial, cero complete y cero unavailable. Solo contienen GENERAL_STRENGTH con estructura plana. Fases: BASE 398, BUILD 40, MAINTENANCE 10, SPECIFIC 10 y TAPER 10. RECOVERY esta soportada por el builder, pero no aparece en estas capturas. Todos los objetivos capturados son triathlon; los otros cinco objetivos soportados se comprueban mediante fixtures, no mediante extrapolacion de estas capturas.

Conocido: 4127 ocurrencias de descansos entre series bilaterales, derivadas de 2071 nodos elegibles. Son 4112 pausas de 90 s y 15 de 60 s, exclusivamente los valores ya prescritos en el workout. Los subtotales conocidos son 60, 120, 540, 720 o 900 s. Estos subtotales no son estimaciones de sesiones completas.

| Carencia | Requisitos desconocidos | Naturaleza | Resolucion necesaria |
|---|---:|---|---|
| Ejecucion | 2768 | Falta de prescripcion deportiva y de evidencia independiente | Tempo completo o tiempo por serie de una prescripcion concreta con fuente |
| Alcance unilateral | 697 execution_scope + 697 rest_occurrences | Falta de informacion de catalogo y ambiguedad estructural | Reps totales/por lado, numero de lados, secuencia y ubicacion de pausas |
| Entre ejercicios | 2300 | Falta de prescripcion y evidencia sobre transiciones | Hueco completo o composicion explicita sin solapamientos |
| Extremos | 468 calentamientos + 468 vueltas a la calma | Falta de prescripcion/evidencia, no ausencia demostrada | Nodos especificos independientes o declaracion de extremo/ausencia con procedencia |
| Estructuras no representables | 0 observadas en capturas | Limitacion tecnica potencial, separada de datos ausentes | Concurrencia no soportada y repeats sin orden siguen fail closed; no se anaden al total |

Las causas no son excluyentes: 6004 requisitos tienen falta de prescripcion y evidencia; 1394 tienen problemas de catalogo/semantica. No son segundos ni eventos que deban sumarse. La limitacion tecnica no explica los 468 partial actuales: los contratos ya pueden representar tiempos por rep/serie, isometricos, lados y limites; faltan entradas justificadas. Una estructura repeat requiere orden explicito; simultaneidad general sigue sin modelo de agregacion seguro.

Todos los ejercicios carecen de ejecucion independiente. La [matriz](block4b4-shadow-matrix.md) enumera sus frecuencias. Los tres con unilateralidad explicita concentran 697 nodos: Zancada inversa 239, Sentadilla bulgara 229, Bisagra a una pierna 229. Dead bug y Pallof no se interpretan como isometricos, movilidad ni protocolo por lados a partir de su nombre. La marca bilateral de catalogo tampoco demuestra empiricamente como se ejecuto una sesion.

Las capturas son entradas congeladas reutilizadas, con escenarios solapados y sin observaciones segmentadas. Los segundos de nodos provienen de `divmod(total_legacy, ejercicios)`; son asignaciones, no ejecucion. No se usan como evidencia. La duracion historica no valida la estimacion.

## Fuentes deportivas verificadas y decision prescriptiva

Consultadas el [fecha omitida]. Se verifico la publicacion primaria o su resumen bibliografico; no se atribuye informacion no accesible. No se copian tablas de tiempos al catalogo.

| Fuente verificable | Parametro/alcance respaldado | Limitacion | Decision propia de TriCoach |
|---|---|---|---|
| ACSM (2009), *Progression models in resistance training for healthy adults*, Med Sci Sports Exerc 41:687-708, [PMID 19204579](https://pubmed.ncbi.nlm.nih.gov/19204579/), DOI 10.1249/MSS.0b013e3181915670 | Recomendaciones de velocidad, carga y descanso dependen del objetivo y experiencia; distingue fuerza/potencia/resistencia muscular | Adultos sanos; no especifica la ejecucion de estos workouts ni un protocolo universal multideporte | No mapear GENERAL_STRENGTH o RPE a una categoria fisiologica/tempo; conservar unknown |
| Vikmoen et al. (2016), [PLOS ONE 11:e0150799](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0150799), DOI 10.1371/journal.pone.0150799, seccion Training | Protocolo concreto con concentrica de aproximadamente 1 s y excentrica de 2-3 s en fuerza pesada de piernas; tres series y progresion 4-10RM | Mujeres entrenadas en resistencia, ejercicios/material especificos, series hasta fallo y supervision; no define todas las pausas de tempo ni traslados al catalogo actual | No importar esos numeros: faltan objetivo especifico de fuerza, carga RM y seleccion inequivoca de ese protocolo |
| Taipale et al. (2010), *Strength training in endurance runners*, Int J Sports Med 31:468-476, [PMID 20432192](https://pubmed.ncbi.nlm.nih.gov/20432192/), DOI 10.1055/s-0029-1243639 | Intervenciones distintas maximal/explosive/circuit en corredores recreativos; respalda distinguir metodos | Resumen verificado; no se infieren segundos por repeticion ni protocolo para todos los deportes | No crear roles max/explosive ni seleccionar su ejecucion por category=triathlon |

Las fuentes demuestran que existen alternativas contextuales; no determinan una seleccion para la prescripcion actual. Esta es una conclusion de aplicabilidad de TriCoach, no una recomendacion atribuida a los autores. No se introduce ningun valor temporal nuevo ni politica numerica de ejecucion. La politica de descanso sigue `0.8G.2E.1-strength-temporal-prescription-4b3`; el auditor tiene version propia sin cambiar esa politica.

## Como se representaria una prescripcion justificada

El catalogo debe seguir describiendo identidad/patron y capacidades; el snapshot de una sesion concreta debe poseer la prescripcion temporal y su fuente. El mismo ejercicio puede usar otros tempos segun objetivo. No se prescribe un tempo fijo por nombre ni se usan repeticiones, RPE o fase para fabricar segundos.

| Caso | Contrato existente | Informacion requerida antes de usarlo |
|---|---|---|
| Reps/tempo | ExerciseExecutionInput + TempoInput o seconds_per_rep | Todas las fases relevantes, alcance de ciclo/reps, fuente y version; fases desconocidas mantienen partial |
| Tiempo por serie | mode=timed + per_set | Intervalo independiente de ejecucion, excluyendo preparacion y pausa |
| Isometrico | mode=isometric + per_set | Hold y alcance de lados explicitos; nunca deducido del titulo |
| Unilateral | rep_scope/rep_time_scope/side_execution/side_sequence/side_count/side_gap | Totales frente a por lado, simultaneo frente a sucesivo y ocurrencias reales |
| Core/estabilidad | Mismos inputs por sesion | Elegir reps o hold solo con prescripcion; patron no decide duracion |
| Movilidad/ejecucion explosiva | Sin tipo de sesion propio actual | No se inventan ejercicios/roles ni segundos; intencion de velocidad no equivale a tiempo medido |

Prescripcion especifica valida precede siempre a politica general. Se conserva propiedad de rutas del snapshot; no se fusionan dos propietarios silenciosamente. Binding incorrecto, fuentes duplicadas y rangos invalidos se rechazan. Datos medidos conservan su procedencia; `validation_state=not_evaluated` no cambia por tener complete ni por pasar contratos. La procedencia textual no autentica por si sola una medicion.

## Descansos, transiciones y extremos

La politica 4B.3 usa rest_seconds solo entre series completas bilaterales: N series implican N-1 descansos, nunca N. No aplica la regla a nodos unilaterales sin alcance. No agrega descanso final: el hueco siguiente posee toda la frontera y el extremo final posee la cola.

Entre ejercicios, entre lados y entre rondas hay propietarios diferentes. Un hueco completo se cuenta una vez. Si preparacion/transicion estan incluidas en descanso, se cuenta el contenedor; si son disjuntas, se suman con procedencia de esa relacion. Relacion unknown no autoriza suma ni cero. Los bloques secuenciales explicitos conservan multiplicadores de rondas; simultaneidad u orden desconocido no se completan.

La rama de fuerza actual no emite nodos warmup/cooldown independientes. Los parametros de otras ramas del builder no se reutilizan. Si existen nodos especificos, EdgeTimingInput los vincula sin duplicarlos con el prefijo/cola global; las fuentes duplicadas se rechazan. No se contabiliza como ejecucion lo que ya pertenece al calentamiento. Ausencia not_prescribed/not_applicable requiere procedencia; un campo vacio permanece unknown.

## Reconciliacion diagnostica

Se reutiliza `compare_strength_legacy`, ya implementada en 4B.3, despues del resultado independiente. No hay ajuste automatico ni nueva duracion efectiva.

| Cobertura / condicion | Resultado | Distancia |
|---|---|---|
| Complete, legacy < min | LEGACY_BELOW_INTERVAL | legacy - min, negativa |
| Complete, min <= legacy <= max | LEGACY_WITHIN_INTERVAL | 0; solo pertenencia al intervalo temporal |
| Complete, legacy > max | LEGACY_ABOVE_INTERVAL | legacy - max, positiva |
| Partial, legacy < subtotal minimo | LEGACY_BELOW_KNOWN_MINIMUM | Shortfall positivo minimo - legacy; solo componentes disjuntos |
| Partial, legacy = subtotal minimo | INDETERMINATE_PARTIAL | Sin distancia al intervalo total |
| Partial, legacy > subtotal minimo | INDETERMINATE_PARTIAL | Sin evidencia de compatibilidad completa |
| Unavailable | UNAVAILABLE | Sin comparacion valida |

Ejemplos sinteticos nuevos: intervalo completo [30,40] s frente a legacy 29/30/40/41 produce -1/0/0/+1; subtotal parcial 90 frente a 89 demuestra deficit minimo 1, frente a 90 o 91 sigue inconcluso. Todos esos segundos son fixtures y no se aplican a atletas. No hay puntos medios, confianza estadistica ni equivalencia entre ausencia de incompatibilidad y compatibilidad.

En las capturas: 468 INDETERMINATE_PARTIAL; cero incompatibilidades demostradas y cero comparaciones contra intervalos completos. Legacy actual 2400 s y referencia 1440 s no cambia. Los ejemplos reales y las fuentes completas por componente estan en la matriz enlazada.

## Independencia, determinismo y pruebas

El selector solo recibe rol, fase y objetivos soportados. La estimacion usa unicamente datos deportivos y temporales independientes. Target duration, legacy, disponibilidad, presupuesto semanal y target load no intervienen en la aritmetica; sus hashes se usan para binding y no como segundos. Reconciliacion accede a legacy despues. Las pruebas existentes alteran esos valores y los segundos asignados conservando el diseno deportivo, vuelven a vincular el snapshot y verifican igualdad de politica/subtotal/intervalo. No se reutiliza una identidad obsoleta.

Se anaden 22 casos y se ejecutan los 103 anteriores: **125 passed, 1 warning**. Los 27 apartados obligatorios se cubren por la combinacion siguiente (no se cuentan dos veces casos antiguos):

| Apartados | Evidencia de pruebas |
|---|---|
| 1-3, 11, 22: seleccion, objetivos, procedencia/versionado/determinismo | test_strength_timing_policy: supported_objectives, goal_order, measured_source y scope; nuevos clasificadores deterministas |
| 4-7: tempo, timed/isometric, unilateral | suites inputs/policy; nuevos partial_tempo, explicit_execution y included_transition |
| 8-10: unknown, descansos/transiciones, doble cuenta | suites timing/inputs; nuevos unknown_edges e included_transition; duplicados y edge_nodes existentes |
| 12-17: complete/partial/unavailable y comparaciones completas | nuevos complete_closed_interval_limits, unavailable; pruebas previas [30,40] |
| 18-20: subtotal inferior/superior/igual a legacy | nuevos partial_boundary_never_proves_compatibility: 89/90/91 |
| 21: ausencia de circularidad | selection_and_timing_ignore_forbidden_context_variables y pruebas inputs 24/40 |
| 23: identidad workout publico | nuevo explicit_execution y wrappers existentes; hashes de todo backend/app y frontend/src |
| 24-27: bytes/fingerprint, NULL/explicitos/dobles | cinco replays completos comparados contra artefactos4B.3; app NULL/6 y double fixtures previos |

Reproduccion desde raiz: `backend\.venv\Scripts\python.exe backend/scripts/audit_strength_temporal_completion.py`; suite especifica: `python -m pytest backend/tests/test_strength_temporal_completion.py backend/tests/test_strength_timing_policy.py backend/tests/test_strength_timing_inputs.py backend/tests/test_strength_timing.py -q -p no:cacheprovider`. Regresion desde backend: `.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` con TC_AUTH_MODE/TC_ENVIRONMENT=development. No se prueba frontend porque no cambia su codigo ni contrato.

## Dictamen y requisitos de activacion futura

**No hay condiciones suficientes para activar duraciones independientes.** Cobertura completa sigue siendo cero y faltan prescripciones de ejecucion/semantica/transiciones/extremos. Aun complete seria necesario revisar justificacion y validar segmentos, pues completitud no demuestra exactitud.

Una sesion candidata necesitaria: cobertura completa con intervalos y ausencia justificada; fuente trazable y apropiada al objetivo especifico; semantica inequivoca de lados/rondas; componentes aditivos sin duplicados; validacion independiente de segmentos; politica explicita para consumir un intervalo sin inventar punto medio. Despues, una evaluacion separada de disponibilidad/dobles usando el limite pertinente y margen existente, carga, presupuesto semanal e intencion deportiva. Si falla un requisito, fallback integro a legacy con motivo. Una futura activacion necesitaria un mecanismo independiente y reversible, desactivacion inmediata y regresion de identidad cuando esta apagado. Ningun mecanismo ni decision de activacion se implementa aqui.

## Propuesta detallada 4B.5 - NO implementada

1. Acordar protocolos deportivos especificos con revision tecnica: objetivo de fuerza real, experiencia/carga y criterios de seleccion; catalogar capacidades sin fijar tempos globales. Rechazar protocolos cuya seleccion requiera contexto ausente.
2. Completar para una sesion sintetica representativa la prescripcion de ejecucion, lados, descansos, fronteras y extremos mediante los mismos inputs privados y fuentes verificables. Mantener unknown donde no haya justificacion y versionar cambios de protocolo.
3. Definir y recoger, en trabajo autorizado por separado, evidencia segmentada independiente con origen autenticable y consentimiento/alcance apropiado. Separar datos observados de parametros prescriptivos. Sin escribir atletas reales desde este bloque.
4. Validar aditividad y semantica con fixtures de intervalos completos, parciales, unilaterales, repeats y nodos de extremos; contrastar segmentos observados sin calibrar con legacy. Definir criterios de error antes de analizar resultados, sin confianza estadistica inventada.
5. Reevaluar los mismos escenarios y documentar el efecto exclusivamente shadow. Proponer despues un diseno de activacion/reversion y reconciliacion de carga/capacidad; no convertir automaticamente el exito de campos completos en permiso de activacion.

Riesgos pendientes: transferencia inapropiada de protocolos de investigacion, identificacion debil de fuentes, semantica real distinta del catalogo, incertidumbre de preparacion/material y sesgo de capturas repetidas. La clasificacion del auditor es un diagnostico de requisitos, no una validacion deportiva ni una nueva regla hard.

Sin cambios de datos reales, planes aceptados, staging, commit ni push. No se implementa 4B.5.

## Trazabilidad complementaria

[Registro de fuentes verificadas](../informe/block4b4-sources.json): la fuente PLOS se reviso en texto completo; ACSM y Taipale mediante registros/resumenes primarios indexados. El acceso directo a PubMed devolvio una pantalla intermedia, por lo que no se presenta como revision de texto completo. Las fuentes no validan automaticamente los descansos legacy de 90/60 s: esos valores se conservan como prescripcion existente y su alcance sigue siendo la decision normativa 4B.3, no una medicion ni un optimo demostrado.

## Validacion final

**2012 pruebas backend pasan, 8 warnings**, en 373.22 s. Los 22 casos nuevos estan incluidos en ese total. Suite especifica: **125 passed, 1 warning**. Compileall y git diff --check: codigo 0. Los 356 archivos protegidos de backend/app y frontend/src conservan sus hashes. Cinco artefactos, fingerprints y reportes temporales son identicos byte a byte a 4B.3.

El primer intento de pytest dentro del sandbox fallo por WinError 5 en directorios temporales, incluido cleanup de pytest. Se repitio la suite completa fuera del sandbox con fixtures de prueba, sin cambiar codigo ni datos reales; la ejecucion verificada termina con codigo 0. No hubo rechazo de aprobacion automatica.

Evidencias: [backend verificado](../informe/block4b4-backend-verified.log), [intento sandbox](../informe/block4b4-backend.log), [checks finales](../informe/block4b4-final-checks.json), [git status](../informe/block4b4-git-status.txt), [diff check](../informe/block4b4-diff-check.txt), [reporte bytes](../informe/block4b4-policy-byte-checks.json), [auditoria](../informe/block4b4-validation.json).
