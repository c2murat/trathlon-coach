# 0.8G.2D.3 - Informe final de calendario y ejecucion

Validacion final ejecutada el 24/09/2026. Implementacion terminada; no se
anadieron funcionalidades nuevas durante este cierre. Sin staging, commit ni
push. `backups/`, `informe/` y temporales permanecen fuera de la entrega.

## Alcance

D.3 anade un batch read-only para mostrar evidencia C.1 en Calendario. El
endpoint `GET /dashboard/calendar-execution` acepta el rango visible, reutiliza
`PrescribedCompletedEvidenceAssembler.assemble_range`, recorta a fechas pasadas
segun la timezone del atleta y devuelve `ExecutionSessionView` reutilizable.

El frontend consulta el batch junto con objetivos y sesiones, muestra badges y
detalle en Lista, Mes y Ano, ignora evidencia de otro atleta, no pinta sesiones
de hoy/futuras como ejecutadas y refresca despues de
`tricoach:activity-sync-completed`.

## Validaciones completas

| Validacion | Resultado |
| --- | --- |
| Frontend completo | 47 archivos, 375 tests passed |
| Frontend build | `tsc -b && vite build` OK, 114 modulos transformados |
| Backend completo | 1683 passed, 8 warnings |
| Backend completo, corrida con `.env` session | No valida como cierre: 1531 passed, 152 failed, 8 warnings |
| Backend completo, primera corrida sandbox | No valida como cierre: 128 failed, 1474 passed, 81 errors por permisos de temporales |
| `compileall app tests` | OK |
| `alembic current` | `0026_session_activity_links (head)` |
| `alembic heads` | `0026_session_activity_links (head)` |
| Auditor multiatleta | `issue_count: 0` |
| Auditor Strava multiatleta | `issue_count: 0`, 3 atletas, 2 cuentas Strava activas |
| `git diff --check` | OK |

Auditoria de autenticacion: `backend/.env` contiene `TC_AUTH_MODE=session`, no
habia override en el proceso de shell y `get_settings()` cargaba
`auth_mode=session`. Esa fue la causa de los 152 fallos iniciales: el primer
fallo representativo era
`tests/test_activity_reads.py::test_activities_are_newest_first_with_total_and_safe_fields`,
con `401 Unauthorized` donde el test esperaba `200`. La suite completa se
repitio con `$env:TC_AUTH_MODE='development'` solo para el proceso pytest, sin
modificar `.env` ni la configuracion del servidor real; los 152 fallos
desaparecieron.

## Regresiones dirigidas

| Area | Resultado |
| --- | --- |
| D.3 calendario backend | `test_calendar_execution.py`: 15 passed |
| C.1 evidencia | `test_execution_evidence.py`: 13 passed |
| D.2/Q overview | `test_execution_overview.py`: 8 passed |
| Post-sync | `test_post_sync_execution.py`: 6 passed fuera del sandbox |
| Matching planificado-actividad | `test_planned_session_activity_matching.py`: 10 passed |
| Planning/adaptacion/lifecycle/session/workout | incluido en corrida dirigida, 256 passed antes de post-sync; post-sync validado aparte |
| Fechas locales, cambio de dia y DST | 7 tests especificos de calendario passed |
| Frontend calendario DOM | `CalendarExecution`, `CalendarPage.month`, `AnnualCalendar`: 25 passed |

La corrida dirigida inicial con `post_sync_execution` dentro del sandbox dio 6
errores por `PermissionError` en temporales de pytest. Reejecutada fuera del
sandbox, la suite post-sync paso completa.

## N+1 y consultas batch

Medicion directa sobre datos reales de Carlos Murat, con SQLAlchemy event
listener y sin escrituras:

| Vista/rango | Fechas | Sesiones evaluadas | SELECTs |
| --- | --- | ---: | ---: |
| Lista | 2026-01-01 a 2026-12-31 | 8 | 2 |
| Mes | 2026-08-31 a 2026-10-11 | 8 | 2 |
| Ano | 2026-01-01 a 2026-12-31 | 8 | 2 |

El test sintetico `test_endpoint_permissions_readonly_range_and_constant_queries`
cubre 101 sesiones y mantiene el presupuesto de consultas constante, incluyendo
autorizacion.

## Datos reales

Consulta read-only del batch para 2026:

| Atleta | Timezone | Sesiones planificadas 2026 | Sesiones pasadas evaluadas | Hoy/futuro evaluado | Estados |
| --- | --- | ---: | ---: | ---: | --- |
| Carlos Murat | Europe/Madrid | 23 | 8 | 0 | 8 `UNMATCHED` |
| CARLOS2 | Europe/Madrid | 0 | 0 | 0 | ninguno |
| Jenny Ruiz | Europe/Madrid | 0 | 0 | 0 | ninguno |

Las sesiones `UNMATCHED` se presentan como "Sin actividad vinculada". No existe
un caso positivo real `COMPLETED` en los datos consultados; queda pendiente de
observacion natural. No se fabricaron actividades ni vinculos para obtenerlo.

## Hoy, futuro y DST

El backend calcula `as_of_date` con `now.astimezone(ZoneInfo(timezone_name))`.
Las sesiones con `date >= as_of_date` no se devuelven en el batch y el frontend
tambien evita adjuntar evidencia a hoy/futuro aunque una respuesta defectuosa la
incluyera. Validado por tests de cutoff local en Europe/Madrid, incluido cambio
de dia y DST, y por la consulta real: `future_or_today_returned = 0`.

## Evidencia y targets

El detalle reutiliza `ExecutionSessionView`, `SessionExecutionEvidence`,
`TargetAdherenceEvidence` y `LinkProvenance` ya usados por D.2/Q. No inventa
cumplimiento, no traduce ausencia de vinculo como fallo y no convierte la
fraccion redondeada de adherencia en un contador de bloques acertados. Los
tests verifican estados C.1, actividades multiples, provenance manual/automatico
y targets con/sin laps.

## Refresh tras sincronizacion

Calendario escucha `tricoach:activity-sync-completed`, filtra por atleta activo
y recarga el rango visible. La prueba frontend `list shows badge and detail only
for elapsed sessions and refreshes on sync` confirma que ignora eventos de otro
atleta y refresca con el atleta correcto. `post_sync_execution.py` confirma que
el procesamiento post-sync conserva vinculos manuales, crea automaticos cuando
corresponde y no fuerza links ambiguos.

## Multiatleta y permisos de coach

El endpoint usa `require_athlete_capability(READ_TRAINING_PLANNING)` y valida
aislamiento por `X-TriCoach-Athlete-Id`. La prueba de permisos del endpoint
cubre roles `owner`, `athlete` y `coach`, rechaza atleta no autorizado con 403 y
mantiene `Cache-Control: private, no-store`. Los auditores reales multiatleta y
Strava devuelven `issue_count: 0`.

## Visual

La validacion visual con navegador in-app quedo bloqueada: tras seguir la skill
de Browser, la conexion devolvio `Browser is not available: iab`. No hay
capturas nuevas de D.3. Como cobertura parcial, se ejecutaron los tests DOM de
Lista/Mes/Ano y el build completo, que validan etiquetas accesibles, badges,
detalle, seleccion Ano -> Lista, rango mensual de 42 dias y ausencia de estados
prematuros. La comprobacion visual bitmap desktop/movil queda pendiente por
herramienta, no por cambio de producto.

## No cambios fuera de alcance

`git diff` confirma cero cambios en:

- `backend/app/application/planned_session_activity_matching.py`
- `backend/app/api/v1/routes/planned_session_activity_links.py`
- `backend/app/db/models/planning.py`
- `backend/app/domains/planning/*`
- `backend/app/application/planning.py`
- `backend/app/application/planning_preview.py`

No se modificaron reglas de matching, vinculos manuales, formulas de
planificacion, workout builder, migraciones ni estado persistido.

## Archivos D.3

Modificados:

- `backend/app/api/v1/routes/dashboard.py`
- `backend/app/application/execution_evidence.py`
- `frontend/src/features/calendar/AnnualCalendar.tsx`
- `frontend/src/features/calendar/CalendarPage.tsx`
- `frontend/src/features/calendar/MonthlyCalendar.tsx`
- `frontend/src/features/calendar/calendarItems.ts`
- `frontend/src/features/dashboard/ExecutionOverviewSection.tsx`
- `frontend/src/services/apiClient.ts`

Creados:

- `backend/app/application/calendar_execution.py`
- `backend/tests/test_calendar_execution.py`
- `frontend/src/features/calendar/CalendarExecution.tsx`
- `frontend/src/features/calendar/CalendarExecution.test.tsx`
- `frontend/src/features/calendar/calendarExecution.css`
- `frontend/src/features/calendar/calendarExecutionTypes.ts`
- `frontend/src/features/execution/executionPresentation.ts`
- `docs/calendar-execution-audit.md`
- `docs/calendar-execution-report.md`

Excluidos de la entrega: `backups/`, `informe/`, temporales, caches y
`frontend/tsconfig.app.tsbuildinfo`.
