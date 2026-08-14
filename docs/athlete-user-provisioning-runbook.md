# Provisioning interno de User atleta

Este procedimiento vincula un User nuevo con un AthleteProfile existente. No crea Athletes, no cambia memberships owner y no opera Strava.

## PRE

Confirmar working tree/commit revisado, Alembic current igual a heads en 0020_unique_active_self_athlete, auditores en cero y UUID exacto del AthleteProfile. Jenny debe seguir sin IntegrationAccount.

## BACKUP

Crear un backup PostgreSQL NUEVO posterior a 0019/0020 y validarlo con pg_restore --list. No sobrescribir ni restaurar automaticamente tricoach_pre_jenny_strava_20260813_113238.dump.

## DRY-RUN

Ejecutar provision_athlete_user.py con --athlete-id, --email, --display-name, --timezone y --dry-run. Comprobar Athlete, role athlete, active/default true y email enmascarado. Dry-run no pide password ni escribe.

## PROVISION

Repetir sin --dry-run. Verificar el resumen, escribir exactamente YES e introducir dos veces la contraseña mediante el prompt oculto. No pasar passwords como argumentos. La transaccion inserta User y membership conjuntamente.

## LOGIN-JENNY

Usar /login normal. Confirmar /auth/me con el User Jenny, Cuenta con su identidad y /session/context con unicamente Jenny AthleteProfile, role athlete y capabilities self-service.

## ISOLATION

Confirmar Jenny Profile/Dashboard vacios propios, Strava desconectado y acceso a Carlos denegado. Volver a Carlos y confirmar que conserva Carlos+Jenny, roles owner e historico Strava.

## POST

Ejecutar auditor de autenticacion, auditor multiatleta, preflight y auditor Strava. Esperado: users 2, Athletes 2, memberships 3, owners 2, athletes 1, defaults activos 2, issues 0. No ejecutar sync.

## STOP CONDITIONS

Detenerse si se crea otro AthleteProfile; cambia Carlos a Jenny; Jenny recibe Carlos; role no es athlete; aparece mas de una membership athlete activa; cualquier auditor tiene issues; o cambia Strava Jenny. No borrar filas ni restaurar automaticamente: capturar estado read-only y diagnosticar.


## VALIDACION REAL FINAL

0.8E.1 quedo validada con User Jenny real, login estandar correcto, identidad Jenny visible y Session Context limitado exclusivamente a AthleteProfile Jenny. Carlos no fue seleccionable desde su cuenta. Antes del primer sync Jenny mostraba 0 actividades; despues se conecto su Strava propio y solo recibio sus datos.

El bucle de respuestas 403 observado durante la operacion se resolvio al detectar un proceso Uvicorn antiguo con codigo stale. No era un defecto del codigo actual.

Estado final: **0.8E.1 CLOSED**.


## NORMALIZACION ADMINISTRATIVA DE ROLES - 0.8E.2

Los roles se cambian con scripts/set_athlete_membership_role.py, nunca mediante SQL manual. La herramienta exige --user-id, --athlete-id, --role y permite --dry-run/--yes. Resuelve una membership existente, bloquea la fila en cambios reales, no reactiva filas, no altera default ni crea memberships.

Antes de aplicar un cambio real se debe ejecutar dry-run, verificar current/requested role y confirmar Controller after transition=true. La operacion rechaza dejar un Athlete sin controller activo, donde controller significa owner OR athlete, y rechaza una segunda identidad athlete activa.

La autorizacion sigue siendo por membership del Athlete seleccionado. Tener owner sobre un Athlete no eleva las capabilities coach sobre otro Athlete.
