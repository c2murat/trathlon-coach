# Runbook 0018 — Athlete onboarding

Estado: implementación preparada; migración real NO APLICADA.

## Ventana de despliegue

El ORM posterior a 0018 requiere `athlete_profiles.display_name` y ya no usa `user_id`. No arrancar backend ni workers nuevos mientras PostgreSQL siga en 0017. Detener servicios, migrar y auditar antes de arrancarlos.

## Aplicación manual

1. Detener backend, frontend y workers.
2. `git status --short` y revisar/commit de la implementación aprobada.
3. Crear fuera del repositorio un backup con timestamp (PowerShell):
   `$stamp = Get-Date -Format yyyyMMdd_HHmm; pg_dump --format=custom --file "C:\backups\tricoach_pre_0018_$stamp.dump" --dbname $env:TC_DATABASE_URL`
   No incluir contraseña en el comando; usar `.pgpass`/prompt o la configuración segura existente.
4. `cd backend`
5. `\.venv\Scripts\python.exe scripts\preflight_athlete_onboarding.py --all-athletes --format json`
6. Guardar el JSON agregado como baseline externo; exigir `issue_count: 0`.
7. `\.venv\Scripts\python.exe -m alembic upgrade head`
8. `\.venv\Scripts\python.exe -m alembic current` (debe ser `0018_athlete_onboarding`).
9. `\.venv\Scripts\python.exe scripts\audit_multi_athlete_integrity.py --all-athletes --format json`
10. Comparar IDs y conteos por Athlete: perfiles, memberships/owner/default, actividades, cargas, agregados, fuerza, perfiles/referencias, Training Status e IntegrationAccount Strava.
11. Arrancar backend y hacer smoke test del Athlete A. Continuar con 0.8C.2B solo si todo coincide.

## Fallo y rollback

El downgrade es seguro solo si cada Athlete tiene exactamente un owner activo y ningún User posee más de un Athlete. Ejecutar `alembic downgrade 0017_authentication_base` únicamente con esas condiciones y servicios detenidos. La migración aborta ante ownership ambiguo; nunca elige ni elimina filas. Si el upgrade o la comprobación posterior falla y el downgrade no es seguro, mantener servicios detenidos y restaurar el dump en una base limpia siguiendo el procedimiento operativo PostgreSQL (`createdb` + `pg_restore --clean --if-exists`), sin sobrescribir la única copia antes de verificar el backup.
