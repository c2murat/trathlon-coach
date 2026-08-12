# Validación real de una segunda integración Strava

Estado: 0.8D.5 preparada; pendiente de CONNECT y FIRST-SYNC manuales de Jenny Ruiz. No contiene secretos.

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
