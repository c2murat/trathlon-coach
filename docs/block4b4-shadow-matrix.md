# Bloque 4B.4 - Matriz de reconciliacion shadow

Version publicable: identidad y fechas de capturas omitidas; originales y evidencias detalladas se conservan solo localmente, fuera de Git. Los enlaces a informe/ designan evidencia local no distribuida.

468 reevaluaciones offline de capturas congeladas de noviembre de 2026. Son salidas de escenarios solapados, no 468 observaciones independientes de atletas. No se incorporan nuevos tiempos.

| Escenario | Sesiones fuerza | Antes complete/partial/unavailable | Ahora C/P/U | Reconciliacion | Bytes / fingerprint / reporte |
|---|---:|---|---|---|---|
| current-null | 92 | 0/92/0 | 0/92/0 | Inconclusa partial en todas | Identicos |
| current-target6 | 92 | 0/92/0 | 0/92/0 | Inconclusa partial en todas | Identicos |
| reference-target6 | 96 | 0/96/0 | 0/96/0 | Inconclusa partial en todas | Identicos |
| reference-race-cap | 96 | 0/96/0 | 0/96/0 | Inconclusa partial en todas | Identicos |
| double-target6 | 92 | 0/92/0 | 0/92/0 | Inconclusa partial en todas | Identicos |

## Agrupacion por rol, estructura y fase

| Tipo | Estructura | Fase | Partial |
|---|---|---|---:|
| GENERAL_STRENGTH | flat_strength | BASE | 398 |
| GENERAL_STRENGTH | flat_strength | BUILD | 40 |
| GENERAL_STRENGTH | flat_strength | MAINTENANCE | 10 |
| GENERAL_STRENGTH | flat_strength | SPECIFIC | 10 |
| GENERAL_STRENGTH | flat_strength | TAPER | 10 |

## Ejercicios sin ejecucion temporal independiente

| Ejercicio | Ocurrencias sin ejecucion | Unilateralidad pendiente |
|---|---:|---:|
| Sentadilla goblet | 239 | 0 |
| Peso muerto rumano | 239 | 0 |
| Zancada inversa | 239 | 239 |
| Elevación de gemelo | 234 | 0 |
| Remo con banda o mancuerna | 234 | 0 |
| Dead bug | 234 | 0 |
| Sentadilla búlgara | 229 | 229 |
| Bisagra de cadera a una pierna | 229 | 229 |
| Flexión o press con mancuerna | 229 | 0 |
| Elevación de sóleo con rodilla flexionada | 224 | 0 |
| Remo con banda | 224 | 0 |
| Press Pallof con banda | 214 | 0 |

## Ejemplos representativos

| Escenario / fecha | Legacy s | Subtotal conocido min-max s | Total independiente | Resultado |
|---|---:|---|---|---|
| current-null / [fecha omitida] | 2400 | 900-900 | Desconocido | INDETERMINATE_PARTIAL |
| current-null / [fecha omitida] | 2400 | 720-720 | Desconocido | INDETERMINATE_PARTIAL |
| current-null / [fecha omitida] | 2400 | 540-540 | Desconocido | INDETERMINATE_PARTIAL |
| current-null / [fecha omitida] | 2400 | 60-60 | Desconocido | INDETERMINATE_PARTIAL |
| current-null / [fecha omitida] | 2400 | 120-120 | Desconocido | INDETERMINATE_PARTIAL |
| reference-target6 / [fecha omitida] | 1440 | 900-900 | Desconocido | INDETERMINATE_PARTIAL |
| reference-target6 / [fecha omitida] | 1440 | 720-720 | Desconocido | INDETERMINATE_PARTIAL |
| reference-target6 / [fecha omitida] | 1440 | 540-540 | Desconocido | INDETERMINATE_PARTIAL |
| reference-target6 / [fecha omitida] | 1440 | 60-60 | Desconocido | INDETERMINATE_PARTIAL |
| reference-target6 / [fecha omitida] | 1440 | 120-120 | Desconocido | INDETERMINATE_PARTIAL |
| double-target6 / [fecha omitida] | 2400 | 900-900 | Desconocido | INDETERMINATE_PARTIAL |
| double-target6 / [fecha omitida] | 2400 | 720-720 | Desconocido | INDETERMINATE_PARTIAL |
| double-target6 / [fecha omitida] | 2400 | 540-540 | Desconocido | INDETERMINATE_PARTIAL |
| double-target6 / [fecha omitida] | 2400 | 60-60 | Desconocido | INDETERMINATE_PARTIAL |
| double-target6 / [fecha omitida] | 2400 | 120-120 | Desconocido | INDETERMINATE_PARTIAL |

No hay incompatibilidades demostradas con el subtotal disponible. Esto **no demuestra compatibilidad**. Los unicos segundos agregados son descansos entre series completas bilaterales. No hay intervalo completo, punto medio ni confianza estadistica.

La [matriz JSON por sesion](../informe/block4b4-session-matrix.json) incluye todos los componentes conocidos y sus fuentes/versiones, componentes desconocidos y causas no excluyentes, politica, subtotal, legacy, resultado y motivo de incompatibilidad (null cuando no se demuestra). [Validacion y contadores](../informe/block4b4-validation.json).
