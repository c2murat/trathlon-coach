# Pipeline automatico post-Strava

Desde 0.8E.3, una sincronizacion iniciada desde el navegador representa la actualizacion completa de TriCoach, no solo la descarga de actividades.

## Flujo

`OAuth o Sincronizar ahora -> SyncJob -> import paginado -> cargas por actividad -> agregados combinados diarios/semanales -> Training Status -> succeeded`.

El callback OAuth inicia el primer job despues de persistir `IntegrationAccount` y `OAuthCredential`. Las sincronizaciones posteriores reutilizan `POST /integrations/strava/imports`. `/latest` y `/{job_id}` exponen estado, etapa y contadores sin credenciales.

## Transacciones e idempotencia

Cada pagina importada se confirma por separado. Las actividades nuevas o materialmente modificadas se guardan como alcance del job. El procesamiento local derivado usa una transaccion posterior: si falla, las actividades importadas permanecen y el job termina `partially_succeeded` con `post_processing_failed`. Reintentar desde el navegador crea/reanuda una generacion idempotente sin duplicar filas.

La unicidad de jobs activos por cuenta Strava evita pipelines concurrentes. El boton deshabilitado mejora la UX, pero no es la barrera de integridad.

## Rango e aislamiento

Solo se recalcula `ActivityTrainingLoad` para IDs nuevos/modificados. Daily y weekly se recalculan para el intervalo local afectado usando el agregador combinado, por lo que conservan fuerza manual. Training Status se propaga desde la primera fecha afectada hasta hoy por su dependencia acumulativa.

Todas las consultas usan `athlete_id`, `IntegrationAccount` y membership/capability del Athlete seleccionado. Los Performance Profiles se buscan exclusivamente para ese Athlete; si no existe uno, se conservan los fallbacks del motor.

La zona horaria procede de `AthleteProfile.timezone`. Un cambio posterior requiere un recalculo administrativo completo con la nueva zona; el pipeline no fija `Europe/Madrid` globalmente.

## Errores, retry y proceso

Rate limits y errores temporales mantienen `retry_scheduled`. Errores derivados dejan un estado recuperable visible en el navegador. Los jobs se ejecutan como tareas propiedad del proceso FastAPI: cerrar el navegador no los cancela, aunque un reinicio del servidor puede requerir que el usuario pulse Reintentar para reanudar el checkpoint persistido.

El enrichment remoto de detalles/evidence conserva sus jobs, rate limits y politicas de retencion existentes; no se lanzan miles de llamadas remotas dentro del pipeline local.

`backfill_training_load.py` y `backfill_training_status.py` permanecen solo para mantenimiento, reparacion o auditoria. No forman parte del flujo normal del deportista.
