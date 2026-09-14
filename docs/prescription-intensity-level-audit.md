# C.6 — auditoría previa y decisión conservadora confirmada

## Estado inicial, anterior a la implementación

- Rama: `sprint-0.8a-authentication`.
- HEAD local, origin y remoto comprobado con `git ls-remote`:
  `d992da05c06a5172074727649475d4689b2a33ea`.
- Código tracked limpio; únicamente `backups/` e `informe/` sin seguimiento,
  ambos excluidos del trabajo.
- En el momento de esta auditoría no se había modificado arquitectura, código
  productivo, tests ni datos.

## Inventario por deporte

| Deporte | Tipos de sesión existentes | Fuente del target normal | Alternativas para el mismo esfuerzo y contexto |
|---|---|---|---|
| RUN | EASY, LONG, TEMPO, THRESHOLD, INTERVAL, RECOVERY | Ratios `run_pace_*` de WorkoutBuilderConfig por threshold pace; C.2B para intervalos elegibles | Un rango por familia/rol. LONG puede contener bloques aerobic y tempo; son bloques distintos, no alternativas para el mismo bloque. |
| BIKE | EASY, ENDURANCE, LONG, TEMPO, THRESHOLD, INTERVAL, RECOVERY | Ratios `bike_power_*` por FTP; C.2B para intervalos elegibles | Un rango por familia/rol. LONG puede contener endurance y sweet_spot. No existe BIKE_VO2 como SessionType. |
| SWIM | TECHNIQUE, EASY, AEROBIC, THRESHOLD, INTERVAL, ENDURANCE | Ratios `swim_css_*` por CSS; C.2B para intervalos y bloques threshold elegibles | Principal, residual easy y ocasional threshold dentro de AEROBIC son bloques con funciones distintas. No son niveles intercambiables. |
| Strength | GENERAL_STRENGTH | RPE y plantilla de fuerza | Fuera de alcance; no convertir sets/reps/RPE en escalones. |

## Primitivas revisadas

1. `workout_builder.py`: `_target`, `_resolved_target`, `_target_for_step`,
   `_time_endurance_steps`, `_quality_catalog_steps`, `_swim_steps`,
   `_strength_steps`, `_progression_level`, configuración y normalización.
   Los patrones de tres estados alteran duración, distancia, repeticiones o
   recovery; C.6 prohíbe cambiar estas dimensiones.
2. `session_planning.py`: SessionType, SessionPurpose e IntensityClass.
   EASY/MODERATE/HARD clasifican sesiones; las secuencias de calidad cambian
   SessionType, no niveles dentro de un SessionType fijo.
3. `adaptive_targets.py` (0.8G.2B): interpolación por dimensión de esfuerzo,
   soporte de repeticiones y blends por fase/confianza/recencia/repetición.
   Para un contexto fijo produce un único rango. Modificar artificialmente
   esos inputs para obtener varios rangos cambiaría el contexto de la sesión.
   El rango de referencia y el adaptado son etapas del cálculo, sin una regla
   existente que los declare alternativas de intensidad seleccionables.
4. `capability/models.py` y `capability/analysis.py`: capacidades por duración
   y distancia, clasificaciones de intensidad, distribución y buckets de
   recencia. No hay escalera de candidatos para una duración/distancia fija.
5. `performance_profile/zones.py` (0.7a.1): sí existen zonas ordenadas con
   nombres, unidades, referencia y límites. Sus métodos son FTP_PERCENT,
   THRESHOLD_PACE_PERCENT y CSS_PERCENT. Ordenan categorías de entrenamiento
   distintas, sin un mapping de varios niveles para cada SessionType.
   No se utilizan como catálogo de targets del workout builder actual.
6. `planning/models.py`: WorkoutTarget admite zonas y rangos resueltos,
   metadata capability y C.4; no almacena una identidad de nivel de prescripción.
7. `planning/contracts.py`, `numeric_adaptation.py`, `planning_adaptation.py`,
   `planning_preview.py`: C.5 consume drafts base, C.4 exige coincidencia exacta,
   y acceptance materializa el artifact sin ejecutar generación.

## Constantes existentes y por qué no bastan

Los ratios actuales del builder permanecen como source of truth; no se propone
copiarlos a una tabla C.6. Las zonas FTP usan cortes 0/.55/.75/.9/1.05/1.2/1.5;
las zonas de pace usan divisores 1.15/1.07/1/.93/.86. Son constantes existentes,
pero reutilizarlas para otra función necesita semántica compatible.

Ejemplos de discrepancia, calculados con las políticas actuales:

| Referencia | Target THRESHOLD del builder | Zona Umbral de performance_profile |
|---|---|---|
| RUN 250 s/km | [243, 258] s/km | [233.64, 250) s/km |
| BIKE FTP 200 W | [190, 210] W | [180, 210) W |
| SWIM CSS 110 s/100m | [107, 113] s/100m | [102.80, 110) s/100m |

El builder aplica Decimal/ROUND_HALF_UP a unidades enteras. Las zonas usan
`round(..., 2)` y límites semiabiertos con última zona abierta. Ni las fronteras
ni la semántica de intervalo son equivalentes. Identificar una zona por
proximidad violaría el exact match exigido en C.6-S.

No se han introducido constantes nuevas. Cambiar la precisión, tomar extremos,
subdividir rangos o convertir confidence/blend en niveles no proporciona la
semántica que falta.

## Incompatibilidad de requisitos

- C.6-C/D/K: derivar niveles de semántica preexistente, no asumir que rangos
  diferentes son niveles adyacentes y no crear porcentajes intermedios.
- C.6-G/I/J/S: mismo SessionType, misma semántica y contexto de capability,
  source of truth compartida con Planning y coincidencia exacta.
- C.6-AJ: demostrar obligatoriamente al menos una progresión
  INCREASE_TARGET → adjacent → RESOLVED → APPLIED.

La auditoría no identifica ninguna combinación productiva que cumpla
simultáneamente estas condiciones. `NO_SUPPORTED_LADDER` es el resultado
autorizado para la semántica actual, pero no satisface el caso APPLIED obligatorio.
Un ladder construido manualmente en tests podría probar un algoritmo de
adyacencia; no demostraría que exista una progresión derivada de primitivas
productivas. No debe presentarse como tal.

## Trabajo concreto viable y decisión necesaria

Sin añadir semántica fisiológica se pueden implementar modelos inmutables de
level/ladder, validación de scope/unidades/orden, identificación exacta,
adyacencia estricta y su integración C.5, conservando NO_SUPPORTED_LADDER para
las combinaciones actuales. Esto deja pendiente el criterio de APPLIED real.

Para cumplir ese criterio falta una política explícita que declare cuáles son
los niveles alternativos de al menos un SessionType, cómo se selecciona el nivel
base y cuáles son sus bounds. La política debe poder ser utilizada tanto por
Planning como por C.6. Reutilizar números de otra función por sí solo no la define.

El usuario confirmó posteriormente implementar C.6 de forma conservadora:
modelos, identificación exacta, adyacencia, integración y auditoría, manteniendo
NO_SUPPORTED_LADDER y NO_SAFE_STEP cuando no hay una ladder real. Prohibió
fabricar ladders o niveles para conseguir un caso APPLIED. Esta corrección
prevalece sobre el criterio AJ original y elimina el bloqueo de implementación.

El catálogo productivo no publica ladders. Los tests de identificación usan
una representación contractual del único target real generado por el builder;
no construyen alternativas numéricas ni una progresión artificial. Los extremos
de ese catálogo de un solo elemento carecen de vecino en ambas direcciones.

No se ha iniciado C.7; sin staging, commit ni push.
