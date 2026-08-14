# Validación real de una segunda integración Strava

Estado: 0.8D.5 CLOSED. Ejecucion real multiatleta completada y validada sin tenant leakage. No contiene secretos.

## PRE

1. Detener cualquier sync de Carlos durante la ventana controlada.
2. Desde `backend`, ejecutar `python -m alembic current`, `python -m alembic heads`, `python scripts/preflight_athlete_onboarding.py --all-athletes --format json`, `python scripts/audit_authentication.py --format json`, `python scripts/audit_multi_athlete_integrity.py --all-athletes --format json` y `python scripts/audit_multi_athlete_strava_state.py --all-athletes --format json` usando `\.venv\Scripts\python.exe`.
3. Confirmar schema 0018, dos Athletes, una cuenta Strava, cero issues, Carlos conectado y Jenny desconectada. Guardar la salida JSON como evidencia fuera del repositorio.
4. Crear un backup fuera del repositorio: `$stamp=Get-Date -Format yyyyMMdd_HHmm; pg_dump --format=custom --file "C:\backups\tricoach_pre_jenny_strava_$stamp.dump" --dbname $env:TC_DATABASE_URL`. Verificar que el dump existe y no está vacío. No imprimir la URL.

## CONNECT

1. Abrir TriCoach y seleccionar `Jenny Ruiz`.
2. Ir a `Configuración → Conexiones` y confirmar `Jenny Ruiz — Sin conectar`.
3. Pulsar `Conectar Strava para Jenny Ruiz` una sola vez.
4. En Strava, comprobar que la sesión pertenece a la cuenta distinta de Jenny y aceptar los permisos.
5. Volver a TriCoach y confirmar que la pantalla identifica a Jenny como conectada.

OAuth no inicia importación automáticamente. El callback solo persiste IntegrationAccount/OAuthCredential. No pulsar todavía `Sincronizar actividades`.

## POST-CONNECT

Repetir preflight y ambos auditores, incluido `audit_multi_athlete_strava_state.py`. Exigir dos cuentas Strava, dos identidades externas distintas, una cuenta por Athlete y cero issues. No publicar los external IDs.

## FIRST-SYNC

La API no ofrece rango, límite ni dry-run. El primer `POST /integrations/strava/imports` crea un job con `range_start=null` y `range_end=ahora`; por tanto puede recorrer todo el histórico disponible en páginas. Antes de continuar, aceptar expresamente ese alcance.

Con Jenny seleccionada, pulsar `Sincronizar actividades` una sola vez y esperar el estado terminal. No sincronizar Carlos durante esta ventana.

## POST-SYNC

1. Ejecutar otra vez el auditor específico y conservar la salida como AFTER first import.
2. Confirmar job Jenny → account Jenny; actividades Jenny → source account Jenny; cargas, daily/weekly y status exclusivamente Jenny; auditor general en cero.
3. Comparar los contadores Carlos BEFORE/AFTER. Si la cuenta Jenny no contiene actividades, cero importadas es válido y debe anotarse.
4. Validación visual: Jenny y Carlos por separado en Actividades, Carga de entrenamiento y Estado de forma.

## ROLLBACK/STOP CONDITIONS

Detenerse antes o durante CONNECT si Jenny muestra datos de Carlos, OAuth identifica la cuenta equivocada, el callback aparenta conectar Carlos, no aparecen exactamente dos cuentas, las identidades no son distintas o cualquier auditor informa issues.

Detenerse durante FIRST-SYNC si el job Jenny usa account Carlos, aparece una actividad en el Athlete incorrecto, cambian inesperadamente contadores de Carlos o aparece cualquier mismatch.

Ante un STOP: no desconectar, no borrar cuentas/actividades, no ejecutar SQL correctivo y no restaurar automáticamente. Capturar únicamente estado read-only, detener nuevos syncs y diagnosticar. La restauración del dump requiere una decisión operativa explícita y una base de destino limpia.


## Compatibilidad 0.8D.6 antes de reanudar CONNECT

Nota historica previa a la ejecucion: antes de conectar Jenny se debia revisar `alembic current` y `alembic heads`; revisar y aplicar manualmente `0019_athlete_membership_role`; crear un NUEVO backup post-migration; y repetir todo PRE. El dump 0018 existente sigue siendo valido, no se sobrescribe ni se restaura automaticamente.


## EJECUCION REAL FINAL - 0.8D.5 CLOSED

La operacion real se completo el 14 de agosto de 2026. Se conservaron las identidades User/Athlete separadas y no se publican external account IDs, credenciales ni configuracion sensible.

### PRE real

- Users: 2.
- AthleteProfiles: 2.
- Memberships: 3 (2 owner, 1 athlete).
- Defaults activos: 2.
- Carlos tenia una integracion Strava activa.
- Jenny tenia User propio, membership athlete y AthleteProfile existente; antes del primer sync tenia 0 actividades.
- Auditores de autenticacion, multiatleta y Strava: issue_count 0.

### POST-CONNECT real

- Carlos: 1 IntegrationAccount y 1 OAuthCredential.
- Jenny: 1 IntegrationAccount y 1 OAuthCredential.
- Cuentas Strava totales: 2.
- Identidades externas distintas: 2.
- No se publicaron sus identificadores.
- Auditor Strava y auditor multiatleta: issue_count 0.

La configuracion local valida uso el mismo host loopback que la sesion frontend: 127.0.0.1:8000. No fue necesario debilitar el validador, que ya admite localhost, 127.0.0.1 e ::1 en development/test.

### POST-SYNC real

Jenny completo su primer sync con:

- 451 CompletedActivity, todas Strava.
- 1 SyncJob.
- 451 ActivityTrainingLoad.
- Sin contaminacion con actividades, cuenta, credential o job de Carlos.

Carlos conservo su integracion propia y 1418 actividades Strava.

### POST-LOAD real

Jenny quedo con:

- 409 AthleteDailyTrainingLoad.
- 137 AthleteWeeklyTrainingLoad.
- 451 cargas por actividad.

Carlos conservo:

- 1307 ActivityTrainingLoad.
- 330 AthleteWeeklyTrainingLoad.
- 3 sesiones de fuerza manual.
- 4 PerformanceProfileVersion.
- 6 PerformanceReference.

### POST-STATUS real

El dry-run de Training Status cubrio 2023-07-15 a 2026-08-14 con algoritmo 0.7f.1. Ultimo estado previsto: fitness 27.55, fatigue 32.87 y form -5.32.

Tras el backfill real:

- Jenny: 1127 AthleteDailyTrainingStatus.
- Carlos: 10397 filas de Training Status.

### Evidencia final de aislamiento

- Carlos y Jenny tienen Users, AthleteProfiles, IntegrationAccounts, OAuthCredentials y SyncJobs propios.
- accounts = 2.
- distinct_external_identities = 2.
- No hubo tenant leakage en activities, jobs, credentials, loads ni aggregates.
- Auditor Strava: issue_count = 0 y todos sus checks vacios.
- Auditor multiatleta: issue_count = 0 y todos sus checks vacios.
- Preflight: users 2, athlete_profiles 2, memberships 3, athlete_memberships 1, owner_memberships 2, active_defaults 2, integration_accounts 2, strava_accounts 2, issue_count 0.
- El valor schema=0018 del preflight identifica la familia estructural sin AthleteProfile.user_id; no representa Alembic current.

### Incidencias operativas resueltas

1. Strava Athlete Capacity se amplio de 1 a 10.
2. Se corrigio el redirect local desde un puerto incorrecto.
3. Se mantuvo 127.0.0.1 de extremo a extremo para conservar la sesion.
4. Un bucle 403 durante la validacion de 0.8E.1 procedia de un proceso Uvicorn antiguo con codigo stale, no del runtime actual.

### Criterios de aceptacion

Cumplidos: dos cuentas reales distintas, un account por Athlete, primera importacion Jenny completada, cargas/agregados/status generados, aislamiento A/B demostrado y auditores en cero.

Estado final: **0.8D.5 CLOSED**.


### Revalidacion read-only del cierre

La reejecucion documental de los auditores, sin sync ni escrituras, mantuvo accounts=2, distinct_external_identities=2 e issue_count=0 en ambos auditores. El estado vivo observado entonces fue: Carlos 1418 actividades, 1308 cargas por actividad, 71 jobs y 10397 status; Jenny 451 actividades/cargas, 410 agregados diarios, 137 semanales, 1 job, 1 fuerza manual y 1127 status. Estas variaciones posteriores no alteran el snapshot por etapas anterior ni la conclusion de aislamiento.
