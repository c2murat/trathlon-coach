# Bloque4B.3 - matriz diagnostica de468 salidas

Version publicable. Los enlaces a informe/ remiten a evidencia privada local no distribuida. Las frases sobre ausencia de commits/push describen la entrega original; el estado Git actual figura en integral-consolidation-status.md.

Capturas reutilizadas:23/11 y09/11/2026; evaluacion offline sin cambios de datos reales.

| Escenario | Salidas fuerza | Antes C/P/U | Despues C/P/U | Comparacion valida | Dobles | Doble cuenta | Bytes/FP |
|---|---:|---|---|---|---:|---:|---|
| current-null | 92 | 0/0/92 | 0/92/0 | {'INDETERMINATE_PARTIAL': 92} | 0 | 0 | Identicos |
| current-target6 | 92 | 0/0/92 | 0/92/0 | {'INDETERMINATE_PARTIAL': 92} | 3 | 0 | Identicos |
| reference-target6 | 96 | 0/0/96 | 0/96/0 | {'INDETERMINATE_PARTIAL': 96} | 3 | 0 | Identicos |
| reference-race-cap | 96 | 0/0/96 | 0/96/0 | {'INDETERMINATE_PARTIAL': 96} | 2 | 0 | Identicos |
| double-target6 | 92 | 0/0/92 | 0/92/0 | {'INDETERMINATE_PARTIAL': 92} | 49 | 0 | Identicos |

C/P/U = complete/partial/unavailable. Partial no demuestra que la sesion completa quepa en legacy o disponibilidad.

Subtotales conocidos: descansos entre series bilaterales. Ejecucion, alcance unilateral, transiciones y extremos no se rellenan.

[JSON por sesion](../informe/block4b3-session-matrix.json), [contadores de componentes, politicas, motivos y parametros](../informe/block4b3-validation.json).
