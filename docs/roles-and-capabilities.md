# Roles y capabilities athlete-scoped

## Semántica de producto

- **OWNER** administra un `AthleteProfile` y sus accesos. Su autoridad existe solo sobre perfiles con una membership `owner` activa; no es un administrador global ni implica ser el deportista.
- **ATHLETE** es la identidad self-service: el `User` representa a la persona del `AthleteProfile`. No es un nivel jerárquico. PostgreSQL mantiene como máximo una membership `athlete` activa por perfil.
- **COACH** entrena perfiles previamente asignados mediante memberships `coach` activas. Al iniciar sesión ve “Mis atletas”, selecciona uno en el selector existente y recibe únicamente las capabilities de esa membership.

`editor` y `viewer` se conservan por compatibilidad, pero no son roles principales del producto.

En la validación real de 0.8E.4 no existe todavía ningún User con una membership coach activa; ese rol y su matriz de capabilities se validan mediante pruebas automatizadas.

Inicio muestra como texto secundario el rol de la membership activa: Propietario, Atleta, Entrenador, Editor o Solo lectura. La etiqueta se deriva del mismo Athlete seleccionado en /session/context, cambia con la selección y no forma parte de las opciones del selector, que contienen solo nombres de AthleteProfile.

La autorización deportiva siempre se calcula como `Current User + Current Athlete + active membership → capabilities`. Las capabilities de memberships distintas nunca se unen. Conocer el UUID de un perfil sin membership activa produce `403`.

## Matriz canónica

| Acción | OWNER | ATHLETE | COACH |
|---|:---:|:---:|:---:|
| Ver actividades, métricas, carga y estado | ✅ | ✅ | ✅ |
| Ver Salud athlete-scoped | ✅ | ✅ | ❌ |
| Modificar peso, altura y perfil físico | ✅ | ✅ | ❌ |
| Modificar FTP, FC/ritmo umbral, CSS y referencias | ✅ | ✅ | ✅ |
| Ver estado Strava | ✅ | ✅ | ✅ |
| Conectar o reconectar Strava | ✅ | ✅ | ❌ |
| Sincronizar Strava y ejecutar pipeline | ✅ | ✅ | ✅ |
| Desconectar Strava | ✅ | ✅ | ✅ |
| Crear/actualizar fuerza manual | ✅ | ✅ | ✅ |
| Borrar fuerza manual | ✅ | ✅ | ❌* |
| Gestionar memberships/Coaches | ✅ | ❌ | ❌ |

`*` La regla “Coach borra solo sesiones propias” queda reservada: `ManualStrengthSession` no tiene hoy autor persistido. Añadir creator ownership exigiría diseño y migración; no se inventa esquema en 0.8E.4.

La capability histórica `manage_strava_connection` se conserva para compatibilidad, pero ningún endpoint nuevo debe usarla como autorización combinada. Las operaciones se expresan mediante `connect_strava`, `disconnect_strava`, `read_strava_integration` y `run_strava_import`.

El `/health` actual es readiness público del servicio, no información clínica/deportiva. La pantalla Salud todavía es futura; su navegación y acceso directo ya están condicionados por `read_athlete_health`, y cualquier API athlete-scoped futura deberá exigir la misma capability.

## Gestión de accesos

La asignación de Coaches es una operación account-scoped reservada a `account_plan=owner`; no depende del AthleteProfile seleccionado ni concede acceso deportivo al Owner. ATHLETE no busca, añade ni elimina entrenadores. COACH no busca atletas globalmente: el selector lista exclusivamente memberships activas devueltas por `/session/context`.

Cambiar una membership a `athlete` es identity-sensitive y se rechaza semánticamente si ya existe otra identidad `athlete` activa. La revocación administrativa se hace con `scripts/revoke_athlete_membership.py`; valida existencia, perfil no eliminado, controller restante, bloqueo transaccional, idempotencia y rollback.

Un perfil es íntegro si conserva al menos un controller activo `owner` o `athlete`. Jenny (`athlete` de sí misma sin OWNER) es por tanto válida. El flujo futuro para asignar Coach a un Athlete sin OWNER (administración de plataforma, invitación, solicitud/aceptación o transferencia) queda pendiente y fuera de 0.8E.4.

## Funciones futuras

El motor de planificación, registro público, invitaciones, marketplace, búsqueda global y transferencia completa de identidad no existen todavía. Cuando haya sesiones planificadas con autor, COACH solo podrá borrar las que haya creado; no se añaden endpoints vacíos ni columnas prematuras.
## Asignación Coach–Athlete (0.8E.6)

La autoridad para crear y revocar asignaciones es account-scoped: únicamente un `User.account_plan=owner` puede usar el directorio mínimo y los endpoints `/coach-assignments`. Esto no le concede acceso deportivo global ni crea memberships Owner.

El acceso deportivo del entrenador sigue siendo athlete-scoped: requiere una `UserAthleteMembership(role=coach, is_active=true)` para cada AthleteProfile. El directorio administrativo expone solo identidad mínima de Coaches activos y nombres de AthleteProfiles, nunca actividades, Salud, Strava ni métricas.

La primera asignación activa del Coach se convierte en default. Las posteriores no sobrescriben una selección válida. Revocar conserva la fila histórica con `is_active=false` e `is_default=false`; el siguiente `/session/context` elimina inmediatamente el perfil y resuelve el único restante o vuelve al estado de cero atletas.