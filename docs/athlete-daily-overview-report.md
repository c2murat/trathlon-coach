# 0.8G.2D.2 — Athlete Daily Overview

## Arquitectura

Inicio muestra Resumen de hoy, Tu estado, Hoy, Q (Último entrenamiento y
Sesiones recientes) y Próximamente. La analítica histórica existente continúa
debajo. No se añaden gráficos grandes ni se persiste el overview.

`GET /dashboard/daily-overview` usa la membresía del atleta seleccionado,
`Cache-Control: private, no-store` y un único `utc_now()` de entrada.
`ZoneInfo(athlete.timezone)` determina la fecha local compartida por D.1, Q,
sesiones y días restantes. La analítica recibe el mismo instante.

- D.1: reutiliza `TrainingStatusOverviewAssembler` e `interpretationCopy`.
  Sin nuevos umbrales, ventanas, fórmulas ni interpretación frontend.
- Q: reutiliza `ExecutionOverviewApplication` y la presentación extraída a
  `ExecutionOverviewContent`. `/dashboard/execution-overview` mantiene su
  contrato. C.1, matching, vínculos y postprocesamiento no cambian.
- Sesiones: todas las de hoy y la primera posterior. Orden por fecha,
  hora (sin hora al final) y UUID. El estado persistido se identifica como
  «Estado de planificación», separado de C.1. El modelo existente guarda el
  tipo generado en `title`, igual que C.1; los títulos humanos se conservan.
- Objetivos: primero activo estrictamente posterior a hoy; desempate por
  creación y UUID. Excluye pasados, los de hoy, completados y cancelados.
  Los días restantes se calculan en backend.
- Analítica: reutiliza `DashboardAnalyticsQuery` sin cambiar sus fórmulas.
- Frontend: una lectura sustituye las tres llamadas separadas de analítica
  y la llamada de Q en Inicio. El evento de sync refresca la composición.
  Descarta respuestas tardías o de otro atleta. Un error no equivale a vacío.

Consultas medidas en GET autorizado sobre PostgreSQL READ ONLY: **16 SELECT**
para Carlos, **14** para el segundo atleta y **12** para el atleta vacío.
Sin N+1 por sesión; la identidad por cookie puede añadir una lectura.
Las consultas de analítica existentes leen el historial; no se introduce
caché persistente ni una optimización de ese historial en esta tarea.

## Desfase horario

Ruta exacta: `CompletedActivity.start_at` →
`DashboardAnalyticsQuery.consistency().last_activity_at` → endpoint
`/dashboard/consistency` → `AthleteOverview` → `formatDate(timestamp)`.
El formatter usa UTC por defecto: por eso 15:00Z aparecía como 15:00.
Actividades pasaba `athlete_timezone`; Q pasaba la zona de la actividad.

Ahora Consistencia y Q en Inicio reciben explícitamente la zona del overview.
Se reutiliza `formatDate`/`Intl.DateTimeFormat`, sin sumar horas ni asumir CEST.
Tests: 15:00Z → 17:00 en verano y → 16:00 en invierno en Europe/Madrid;
también fecha local en cambios de día e igualdad entre las tres superficies.

## Validación real del 18/09/2026

Solo lectura, sin nueva sincronización ni cambios directos en DB:

- Carlos: `LOADED`, «Periodo de carga» / «Estás en un periodo de carga».
  Fitness **35,61**, Fatiga **43,48**, Forma **−7,87**, datos del 18/09.
- Hoy: **Bicicleta tempo**, ciclismo, **60 min**, planificada, sin distancia
  prescrita. No se inventa un valor para el campo ausente.
- Próxima sesión: **19/09**, **Fuerza general**, **40 min**.
- Objetivo: nombre guardado **«ican gancia»**, **17/10/2026**, triatlón,
  prioridad **A**, localidad guardada **«gandia»**, **29 días**.
- Última actividad: «Bicicleta por la tarde», 17/09, **17:00** local en
  Consistencia, Último entrenamiento y Actividades.
- Q: dos sesiones recientes `UNMATCHED`, con «No se ha encontrado una
  actividad vinculada», nunca «No cumplido».

## Q aceptado y evidencia pendiente

La validación previa del 18/09 ejecutó dos syncs reales desde Inicio:
1.432 → 1.433 → 1.433 actividades; 0 → 0 → 0 links; cero duplicados.
Primera sync: una importada/procesada; segunda: cero nuevas o actualizadas.
Ambas `succeeded`, postprocesamiento completo y refresh automático.
El candidato de ciclismo obtuvo 0,5162, inferior a 0,55: rechazo correcto.
Los demás atletas conservaron sus datos. No había vínculos manuales reales.

La creación efectiva de un link real, la conservación de un link manual real
durante sync y la adherencia estructurada real quedan pendientes de observar
cuando existan naturalmente. No se fabrican vínculos ni evidencia. Q cubre
esos caminos con fixtures aisladas, sin alterar datos reales.

## Pruebas y visual

Resultados finales:

| Comprobación | Resultado |
| --- | --- |
| Focal backend D.2 | 10 passed |
| Backend completo, incluido Q, Training Status, Planning y C.1 | 1.668 passed, 8 warnings |
| Frontend completo, incluidos D.2, Q y DST | 361 passed, 46 archivos |
| TypeScript noEmit | Correcto |
| Build Vite | Correcto, 111 módulos |
| compileall app/scripts | Correcto |
| Auditor multiatleta | 28 checks, 0 incidencias |
| Alembic current/heads | Ambos 0026_session_activity_links |
| git diff --check | Correcto |

La suite backend se ejecutó desde `backend`, con `TC_AUTH_MODE=development`
solo en el proceso, sin editar `.env`. Las primeras ejecuciones desde la raíz
o con autenticación de sesión provocaron fallos de fixtures (alembic.ini no
encontrado y 401); la ejecución completa corregida pasó sin cambios de código
para ocultarlos. Las ocho advertencias corresponden a dependencias/fixtures
existentes, no a fallos de validación.

Tests nuevos: composición completa/parcial, D.1 presente/ausente, sesiones
vacías/únicas/múltiples, orden, próximos elementos, exclusión de objetivos,
días restantes, fecha local/DST, igualdad de hora en tres superficies,
aislamiento, coach autorizado y atleta ajeno rechazado, solo lectura,
determinismo, Q con vínculo manual, refresh y respuestas tardías.

Visual: Edge local con perfiles temporales y routers reales bajo PostgreSQL
READ ONLY, a **1440 px** y **390 px**, sin desbordamiento horizontal. El
navegador integrado no estaba disponible. Capturas y ayudas de validación en
`backend/.tmp_pytest_d2daily_visual/`, ignorados y fuera de Git.

No se incluyen backups, informe, temporales ni tsbuildinfo. Sin staging,
commit ni push. No se modifican reglas de matching ni el umbral 0,55.
