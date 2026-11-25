# Preparación del bloque 6 — Calendario global semanal

Documento del 25/11/2026. No implementa el bloque 6 ni modifica el comportamiento del motor. Fuente principal: [Coherent Weekly Planning Engine, sección M y apartados I/J/L](coherent-weekly-planning-engine-design.md), contrastada con las entregas de Weekly Intent, 2, 3, 4A y 4B.

## Estado de la hoja de ruta original

La numeración original es 0–8. Los nombres de las entregas posteriores no son una correspondencia uno a uno: 4A/4B desglosan trabajo de asignación/construcción, y la entrega denominada bloque 3 añadió Volume Intent sin inventar una política top-down.

| Bloque original | Estado funcional del workspace | Limitación o dependencia pendiente |
|---|---|---|
| 0. Evidencia congelada | Capturas y replays existentes, casos NULL/6, límites y horizontes | Son evidencia privada local; preparar equivalentes publicables antes de consolidar Git |
| 1. Contratos y modo sombra | WeeklyPlanningIntent, SessionIntent y trazas internos | Preservar schemas y fingerprints |
| 2. Frecuencia y composición | Target total con fuerza incluida, composición desde intents, capacidad y razones explícitas | No confundir falta de colocación con reducción de intención; consolidación Git pendiente |
| 3. Progresión explicada | Reglas actuales instrumentadas: ordinal/ancla, variantes, caps y modificadores observables | No implica nueva progresión fisiológica ni resolución de políticas ausentes |
| 4. Envelope y asignación | Volume Intent bottom-up, autoridad de resistencia 4A y cierre fuerza 4B shadow | Política top-down independiente de minutos no definida; fuerza mantiene legacy |
| 5. Construcción de contenido | Adaptador IntentWorkoutBuild y builder existentes preservan recetas antes/después de distribuir; semántica/tiempo de fuerza contrastados | No existe duración independiente activable de fuerza; no se exige inventarla para cerrar construcción legacy |
| 6. Calendario global semanal | Búsqueda acotada, compatibilidad y parte de precedencia ya implementadas | Completar semillas, poda admisible, diagnóstico de búsqueda y medición de calidad/rendimiento |
| 7. Evaluación única | Diagnósticos y reconciliaciones parciales existentes | Unificar intención frente a resultado, warnings y trade-offs; evitar obsolescencia y falsas certificaciones |
| 8. Comparación de horizonte | Goldens/replays de etapas existentes | Comparación final del conjunto tras 6/7 y decisión de activación independiente |

Este es el estado de archivos y validaciones locales, no una afirmación de que todos esos bloques estén en HEAD remoto. La consolidación Git de los prerrequisitos está pendiente según [la propuesta de commits](block4b-git-consolidation-proposal.md).

## Estado concreto del bloque 5

El alcance original era «Builder desde intent/asignación; semántica de fuerza y duración contrastada», con salida «Mismos catálogos/campos y targets soportados; cualquier cambio de duración tiene regla explícita».

`intent_workouts.py` construye desde las prescripciones de los intents, guarda cada draft por identidad y revincula únicamente la identidad legacy tras distribuir. `workout_builder.py` conserva la fecha de contenido original para que mover una sesión no cambie su variante o progresión. Las pruebas/replays comparan drafts con el builder existente. 4A aporta autoridad explícita de volumen solo para resistencia; 4B explica fuerza, calcula tiempo independiente shadow y evalúa elegibilidad sin modificar su duración.

Así, el núcleo contractual de construcción legacy está cubierto y contrastado. No existe un rediseño universal de recetas ni una política top-down completa; no se declaran implementados. Antes de iniciar 6 debe verificarse que la versión consolidada reproduce esas equivalencias. La deuda de datos temporales de fuerza se conserva separada y no se intenta resolver cambiando el calendario.

## Alcance original del bloque 6

«Precedencia nueva, semillas, poda, score desglosado y estados de búsqueda». Criterio de salida original: **«Mismas sesiones antes/después; dobles solo si ayudan; rendimiento y fronteras medidos»**.

Su objetivo es colocar las sesiones ya prescritas sin cambiar conteos, recetas, intensidad, duración, carga ni intención. Las restricciones hard existentes filtran candidatos; preferencias explícitas, costes blandos de dominio y heurísticas se ordenan de forma explicable con desempate determinista. No se inventan brick workouts ni una excepción para dos sesiones clave.

## Funciones ya disponibles para reutilizar

- `weekly_distribution.distribute_week`: optimización solo de fechas, semilla original factible, candidatos por disponibilidad, orden de menor dominio, capacidad/minutos y comprobaciones incrementales. Límite determinista de 12000 nodos.
- Score con términos de días preferidos libres, largos preferidos, fuerza adyacente, descanso de dominio, conflictos de claves, pares, dispersión y concentración. Hay precedencia específica para target explícito; no se parte de cero ni se presupone que coincide íntegramente con el diseño propuesto.
- `session_compatibility`: combinaciones y capacidad diaria existentes. La suma de sesiones debe caber, sin interpretar target como número de días.
- `weekly_intent` e `intent_workouts`: identidades, composición, prescripciones fijas y ancla del contenido.
- Planificador y configuración existentes: días fijos/competición, exclusiones precompetición, largos y restricciones de frontera. Deben auditarse conjuntamente antes de atribuir cobertura completa al distribuidor aislado.
- Tests de distribución, dobles, estructura/frecuencia y replays de horizonte. Datos privados solo localmente; fixtures sintéticos para nuevas pruebas compartibles.

## Pendiente y dependencias

No basta con incrementar el límite de búsqueda. Hay que medir los casos donde se agota, distinguir testigo factible de optimalidad y distinguir ausencia de testigo de inviabilidad demostrada. El `status_observer` actual informa factibilidad, no constituye por sí mismo el conjunto de estados de búsqueda propuesto.

Queda por contrastar formalmente la precedencia completa de preferencias frente a costes blandos, exponer el desglose/causas, añadir semillas completas útiles y podas con límite inferior admisible, romper simetrías solo entre sesiones intercambiables y evaluar continuidad entre semanas. La poda no puede eliminar una mejora de un nivel anterior del score. Un timeout operativo no debe decidir silenciosamente un calendario por velocidad de máquina.

Dependencias: construcción lossless del bloque 5, intención/frecuencia del 2, compatibilidad y capacidad existentes, minutos ya prescritos y reglas de fases/fronteras. El bloque 6 no depende de activar tiempo independiente de fuerza ni de inventar un envelope top-down. Debe preservar el modo NULL y la exclusividad de competición. La evaluación unificada y decisiones de activación global siguen siendo 7/8.

## Subdivisión propuesta del trabajo dentro de 6

Los siguientes son cortes revisables del mismo bloque original, sin introducir numeración nueva de producto:

| Corte | Trabajo propuesto | Evidencia de salida |
|---|---|---|
| Diagnóstico y contratos | Congelar entradas/salidas; contrastar precondiciones de 5; medir nodos, testigos y límites; definir score/estados sin cambiar recetas | Reproducción determinista y coste inicial por semana/fase; distinguir hechos de hipótesis |
| Semillas y poda | Añadir semillas completas y factibles; cachés/candidatos estables; poda de capacidad y límites admisibles | Misma factibilidad; comparación exhaustiva solo en fixtures pequeños; mejora de coste o calidad medible |
| Precedencia y explicación | Implementar el orden aprobado de preferencias/dominio/heurística, desglose y desempate | Casos que expliquen por qué una doble o un día libre gana; sin premios ilimitados por apilar |
| Fronteras y horizonte | Revisar semanas contiguas, fijos/competición y fases; reparación acotada solo si se justifica | Ningún conflicto residual oculto; cambios de fechas explicados y contenido idéntico |
| Cierre | Golden completo y comparación de rendimiento/calidad frente a baseline | Invariantes originales satisfechas, límites explícitos y entrega revisable antes de continuar a 7 |

## Criterios de aceptación y utilidad para el deportista

- Las mismas identidades y exactamente las mismas sesiones/recetas antes y después; target=6 incluye fuerza y no exige seis días ocupados.
- Disponibilidad, límites globales y por slot, competición y restricciones hard existentes siempre respetados. Máximo una clave por día según la regla actual.
- Dobles compatibles solo cuando mejoran una semana válida; suma de minutos y margen existente dentro de capacidad. Conservar sesiones individuales.
- Días preferidos libres y largos preferidos priorizados según la precedencia aprobada; fuerza y separación razonable como costes de dominio existentes, sin prohibiciones nuevas inadvertidas.
- Estados de búsqueda veraces: factible no probado óptimo frente a límite sin testigo. No etiquetar este último como inviabilidad demostrada.
- Determinismo por inputs/IDs y presupuesto de nodos; score desglosado y razones verificables.
- Rendimiento y fronteras medidos en horizonte completo, no solo en una semana favorable; casos NULL/explícitos, fases, semanas parciales, carrera, límites y dobles.
- No modificar fuerza legacy, carga, Volume Intent ni recetas para resolver un problema de fechas. Evaluación de discrepancias honesta; no aceptar planes reales durante auditorías.

La mejora de mayor utilidad inmediata es preservar descanso y largos, evitar concentración innecesaria y explicar conflictos de capacidad/frecuencia con calendarios mejores y búsqueda acotada. Después corresponden 7 y 8, sin adelantar su implementación aquí.
