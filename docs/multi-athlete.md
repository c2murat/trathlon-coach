# Arquitectura multiatleta

La versión 0.7G permite que un usuario trabaje con más de un atleta y que varios usuarios accedan al mismo atleta con permisos diferentes. Este aislamiento de datos no equivale a autenticación pública: la aplicación todavía utiliza el usuario local de desarrollo.

## Arquitectura y contexto activo

- `User` representa al usuario actual.
- `AthleteProfile` representa el perfil deportivo y es la raíz del aislamiento de datos.
- `UserAthleteMembership` vincula un usuario con un atleta e incluye `role`, `is_active` e `is_default`.
- `CurrentAthleteContext` reúne el usuario actual, el atleta activo y la membresía activa; de esta última se obtienen el rol y las capacidades.

Una membresía permite que varios usuarios accedan al mismo `AthleteProfile`. Cada vínculo puede conceder capacidades diferentes mediante los roles `owner`, `editor`, `coach` y `viewer`.

## Resolución del atleta activo

`resolve_current_athlete` considera únicamente membresías activas:

| Situación | Resultado |
| --- | --- |
| Cero membresías | `404 athlete_profile_not_found` |
| Una membresía | Se selecciona automáticamente |
| Varias y una predeterminada | Se selecciona la predeterminada |
| Varias sin predeterminada | `409 athlete_selection_required` |
| Cabecera explícita válida y autorizada | Se selecciona esa membresía |
| Atleta solicitado no autorizado | `403 athlete_not_authorized` |
| Identificador inválido | `422 invalid_athlete_id` |
| Varias membresías predeterminadas | `409 athlete_default_configuration_invalid` |

## Cabecera de selección

La selección explícita usa `X-TriCoach-Athlete-Id`. El frontend la añade automáticamente después de resolver el contexto. Los clientes API manuales deben añadirla cuando el usuario tenga varias membresías. La cabecera no es una prueba de autorización: el backend valida siempre la membresía activa.

```powershell
curl.exe -H "X-TriCoach-Athlete-Id: <ATHLETE_UUID>" `
  "http://127.0.0.1:8000/activities"
```

## Contexto frontend

`GET /session/context` expone el usuario, los atletas disponibles, el atleta seleccionado, el rol y las capacidades de cada membresía, además de `selection_required`. Con una sola membresía o una predeterminada la selección es automática; con varias sin predeterminada la interfaz exige elegir. El selector persiste la preferencia por usuario, actualiza el cliente API y cancela peticiones del contexto anterior.

## Roles y capacidades

| Operación                                 | Owner | Editor | Coach | Viewer |
| ----------------------------------------- | ----: | -----: | ----: | -----: |
| Lectura                                   |    Sí |     Sí |    Sí |     Sí |
| Recálculos                                |    Sí |     Sí |    Sí |     No |
| Crear y editar fuerza                     |    Sí |     Sí |    Sí |     No |
| Eliminar fuerza                           |    Sí |     Sí |    No |     No |
| Crear perfil y referencia                 |    Sí |     Sí |    Sí |     No |
| Conectar o desconectar Strava             |    Sí |     Sí |    No |     No |
| Importar, enriquecer y generar evidencias |    Sí |     Sí |    Sí |     No |
| Eliminar ubicación                        |    Sí |     Sí |    No |     No |

El backend es la autoridad de seguridad mediante `AthleteCapability` y `require_athlete_capability`. El frontend solo adapta la experiencia visual. Las comprobaciones deben usar capacidades centralizadas, no comparaciones dispersas por nombre de rol.

## Aislamiento de Strava

El inicio seguro usa `POST /integrations/strava/connect/start`. El estado OAuth queda ligado al usuario y al atleta; el callback recupera y revalida ese contexto independientemente del selector frontend. Las cuentas, credenciales y tokens, actividades y jobs están ligados al atleta. La cuenta activa no se elige arbitrariamente y los workers revalidan la coherencia del contexto.

## Integridad relacional

- Solo puede existir una cuenta Strava activa por atleta y proveedor.
- Una actividad y su cuenta de origen deben pertenecer al mismo atleta.
- Un job y su cuenta de integración deben pertenecer al mismo atleta.
- Los `activity_ids` de los agregados deben existir, ser únicos y pertenecer al atleta del agregado.
- Las migraciones abortan ante corrupción; no reparan datos silenciosamente.

Los recursos de otro atleta se tratan como no encontrados en las lecturas aisladas, evitando confirmar su existencia.

## Auditor de integridad

Desde `backend`:

```powershell
.\.venv\Scripts\python.exe `
  scripts\audit_multi_athlete_integrity.py `
  --all-athletes `
  --format text
```

```powershell
.\.venv\Scripts\python.exe `
  scripts\audit_multi_athlete_integrity.py `
  --all-athletes `
  --format json
```

También admite `--athlete-id <ATHLETE_UUID>`. Es de solo lectura y revierte la sesión. Devuelve `0` sin incidencias, `1` si detecta alguna, `2` ante argumentos inválidos y `3` ante un error de ejecución.

## Backfills con alcance explícito

El backfill de carga exige exactamente uno de `--athlete-id` o `--all-athletes`. `--dry-run` ejecuta y revierte; el alcance global requiere además `--confirm-all-athletes`. No existe alcance global implícito.

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\backfill_training_load.py `
  --athlete-id <ATHLETE_UUID> `
  --dry-run
```

```powershell
.\.venv\Scripts\python.exe scripts\backfill_training_load.py `
  --all-athletes `
  --confirm-all-athletes `
  --dry-run
```

El backfill de estado exige `--athlete-id` y admite `--dry-run`, pero no `--all-athletes`:

```powershell
.\.venv\Scripts\python.exe scripts\backfill_training_status.py `
  --athlete-id <ATHLETE_UUID> `
  --dry-run
```

## Migraciones

- `0014_user_athlete_memberships`: crea membresías y genera membresías `owner` predeterminadas para propietarios heredados.
- `0015_strava_oauth_state_athlete`: ordena el despliegue del estado OAuth ligado al atleta; el adaptador SQLite migra su esquema e invalida estados pendientes heredados.
- `0016_multi_athlete_integrity`: precomprueba y aplica unicidad de cuenta activa y coherencia atleta–cuenta para actividades y jobs en PostgreSQL.

## Limitaciones actuales

- La autenticación pública no está implementada; se usa un usuario local de desarrollo.
- No existe registro ni gestión de membresías desde la interfaz.
- No existe cambio de rol desde la interfaz ni transferencia de propiedad.
- `AthleteProfile.user_id` continúa como propietario legado.
- El frontend no crea atletas.
- No existe despliegue productivo todavía.
