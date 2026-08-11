# Alta multiatleta — auditoría y diseño 0.8C.1

Estado: diseño aprobado para implementación posterior. En 0.8C.1 no se crean atletas, endpoints ni migraciones.

## Objetivo y arquitectura actual

La sesión autentica un `User`; no contiene atleta. `UserAthleteMembership` es la autoridad de acceso y enlaza Users y `AthleteProfile` con rol, activación y preferencia. `CurrentAthleteContext` resuelve una membership activa, opcionalmente seleccionada mediante `X-TriCoach-Athlete-Id`, y las consultas deportivas aplican `athlete_id`.

El alta futura debe ser una operación de cuenta independiente del atleta activo:

```text
User autenticado
  -> AthleteApplication.create_owned_athlete
  -> AthleteProfile
  -> UserAthleteMembership(role=owner)
  -> default sólo si es la primera membership activa
  -> commit único
```

No aceptará `user_id`, owner, role, membership ni atleta activo desde HTTP.

## AthleteProfile real

| Campo | Tipo/nullable | Default/constraint |
| --- | --- | --- |
| `id` | UUID, no nulo, PK | `uuid4` ORM |
| `user_id` | UUID, no nulo | FK `users.id ON DELETE CASCADE`, UNIQUE legado |
| `timezone` | string(64), no nulo | default ORM `UTC` |
| `unit_system` | string(16), no nulo | default ORM `metric`; check `metric/imperial` |
| `birth_year` | integer, nullable | ninguno |
| `sex_for_training_context` | string(32), nullable | ninguno |
| `height_m` | numeric(5,3), nullable | si existe, mayor que cero |
| `weight_kg` | numeric(6,3), nullable | si existe, mayor que cero |
| `experience_level` | string(32), nullable | ninguno |
| `deleted_at` | UTC datetime, nullable | borrado lógico |
| `created_at` | UTC datetime, no nulo | `utc_now` ORM |
| `updated_at` | UTC datetime, no nulo | `utc_now`, actualizado por ORM |

No existe `name`, `display_name`, `nickname` ni otro identificador humano. `/session/context` improvisa `Mi atleta` cuando hay uno y `Atleta · <4 caracteres UUID>` cuando hay varios. Esto es insuficiente para onboarding.

Hoy la fila mínima ORM es `AthleteProfile(user_id=<user>)`: timezone y unidades toman defaults; el resto es nullable. Para la API futura no se deben confiar defaults implícitos de Python: nombre, timezone y unidades formarán parte del contrato validado.

## Auditoría de AthleteProfile.user_id

`0001_strava_foundation` creó `user_id NOT NULL`, FK con cascade y `uq_athlete_profiles_user_id`. El modelo reproduce `unique=True`; `User.athlete_profile` es singular y usa `uselist=False` con delete-orphan. La restricción impide dos `AthleteProfile` con el mismo `user_id`.

Usos clasificados:

| Uso | Clasificación | Observación |
| --- | --- | --- |
| `0014_user_athlete_memberships` | B/C: compatibilidad y ownership histórico | Backfill único: convierte cada `user_id` en membership owner/default |
| `User.athlete_profile` / `AthleteProfile.user` | C/E: ownership informativo y deuda | Fuente singular duplicada; no autoriza endpoints |
| `seed_development_user` | D: bootstrap | Busca/crea el atleta local por `AthleteProfile.user_id` |
| Tests/factories con `AthleteProfile(user=...)` | D: creación de fixtures | Conveniencia heredada; deberán crear membership explícita |
| Tests Strava que consultan por `user_id` | B/D | Lookup de fixture local, no autorización productiva |
| `CurrentAthleteContext`, routers y servicios deportivos | A: autorización real | No usan `AthleteProfile.user_id`; usan membership y `athlete_id` |

No se encontró autorización productiva basada en el propietario legado. Mantenerlo produciría dos fuentes de verdad y limita el modelo. Se elige la alternativa A: eliminar `AthleteProfile.user_id` y las relaciones ORM singulares; memberships serán la única autoridad.

## UserAthleteMembership real

- PK UUID y timestamps no nulos.
- `user_id`: FK User con cascade, no nulo e indexado.
- `athlete_profile_id`: FK AthleteProfile con cascade, no nulo e indexado.
- `role`: no nulo, check `owner|coach|editor|viewer`.
- `is_active`: no nulo, default ORM/servidor `true` en migración.
- `is_default`: no nulo, default ORM/servidor `false`.
- UNIQUE `(user_id, athlete_profile_id)`.

La cardinalidad ya es many-to-many: un User puede tener varias memberships y un Athlete varios Users. No hay límite de owners por User o Athlete, ni índice que garantice un único default activo por User. Runtime y auditor detectan múltiples defaults, pero no previenen la carrera.

## Migración propuesta para 0.8C.2

Una revisión `0018_athlete_onboarding` debe:

1. Ejecutar preflight y abortar si existe Athlete sin membership owner activa, más de un owner legado incompatible, múltiples defaults activos o membership que apunte a atleta borrado de forma incoherente.
2. Añadir `athlete_profiles.display_name VARCHAR(200)` inicialmente nullable.
3. Backfill determinista: usar el `User.display_name` no vacío del owner legado; si falta, `Atleta <primeros 8 caracteres del UUID>`. Los duplicados son válidos.
4. Normalizar y convertir `display_name` en `NOT NULL`, con check de longitud tras trim (`1..200`). No añadir UNIQUE.
5. Crear índice parcial único por `user_athlete_memberships(user_id)` donde `is_active IS TRUE AND is_default IS TRUE`, con variantes PostgreSQL/SQLite usadas por el proyecto.
6. Eliminar `uq_athlete_profiles_user_id`, FK y columna `athlete_profiles.user_id`.
7. Actualizar ORM: eliminar `User.athlete_profile` y `AthleteProfile.user`; mantener únicamente las relaciones de memberships.
8. Adaptar el seed para localizar su membership owner/default o crear Athlete + membership en una sola transacción.

El downgrade sólo puede reconstruir el esquema singular si ningún User posee más de un Athlete. Debe precomprobarlo y abortar de forma explícita antes de recrear `user_id NOT NULL UNIQUE`; nunca escoger un owner silenciosamente ni perder atletas.

## Nombre, timezone y unidades

Nuevo campo recomendado: `AthleteProfile.display_name`, `VARCHAR(200)`, no nulo, trim/whitespace normalizado, longitud 1–200 y sin unicidad global ni por owner. `User.display_name` no se reutiliza en runtime porque cuenta y atleta son identidades distintas.

La creación exigirá:

- `display_name` explícito.
- `timezone` IANA explícita, prellenada en frontend desde `User.timezone` o navegador pero confirmada por el usuario. Nunca se copiará del atleta activo.
- `unit_system` explícito, `metric` o `imperial`, prellenado con `metric`.

Birth year, contexto sexual, altura, peso y experiencia son onboarding opcional posterior. FTP, FC, CSS, ritmos, zonas y referencias son perfil deportivo posterior. Strava nunca es requisito de alta.

## Transacción y default

`AthleteApplication.create_owned_athlete(current_user.id, input)` debe bloquear la fila User (`SELECT FOR UPDATE` en PostgreSQL), contar memberships activas, insertar Athlete y owner membership, hacer flush y un único commit controlado por el router. Cualquier fallo revierte ambos registros.

- Cero memberships activas: nueva membership `is_default=true`.
- Ya existe A activa/default: B se crea `is_default=false`; A permanece intacta.
- Varias memberships: no se altera ninguna preferencia existente.
- Configuración previa inválida (múltiples defaults): `409 athlete_default_configuration_invalid`, sin crear nada.

El índice parcial es requisito de 0.8C.2, no deuda aplazable: la creación concurrente hace insuficiente el control exclusivo de aplicación.

## Selección actual y selección tras alta

Flujo vigente:

```text
cookie -> User -> GET /session/context -> memberships activas
-> selección persistida en localStorage por User o default del backend
-> FetchApiClient.setActiveAthlete
-> X-TriCoach-Athlete-Id
-> membership activa -> CurrentAthleteContext
```

`AthleteSelector` ya lista varias memberships, persiste la selección por User, cambia el header y cancela respuestas del atleta anterior. Tras crear B, `refreshContext` puede obtenerlo, pero el label debe proceder de `AthleteProfile.display_name` y tanto `/session/context` como `resolve_current_athlete` deben excluir `deleted_at IS NOT NULL`.

UX elegida: seleccionar B inmediatamente. 0.8C.3 debe añadir una operación `refreshContext({preferredAthleteId: B.id})` o equivalente que valide B en la respuesta nueva, lo active y lo persista sin depender de estado React obsoleto. Después navega a un estado inicial/onboarding ligero. Seleccionar ahora no cambia `is_default`.

## API propuesta

`POST /athletes` es coherente con el recurso creado. Es una mutación autenticada de cuenta, no depende de `CurrentAthleteContext` ni exige `X-TriCoach-Athlete-Id`; reutiliza sesión, CSRF y Origin.

Request estricto (`extra=forbid`):

```json
{
  "display_name": "Atleta B",
  "timezone": "Europe/Madrid",
  "unit_system": "metric"
}
```

Respuesta `201 Created`, DTO explícito:

```json
{
  "id": "uuid",
  "display_name": "Atleta B",
  "timezone": "Europe/Madrid",
  "unit_system": "metric",
  "role": "owner",
  "is_default": false,
  "capabilities": ["..."]
}
```

No devuelve `user_id`, owner interno, memberships ajenas ni datos deportivos. Códigos: `201`; `401 authentication_required`; `403` CSRF/Origin; `409 athlete_default_configuration_invalid`; `422` schema/timezone/unidades; `500` seguro con rollback. `Location: /athletes/{id}` es apropiado aunque el detalle no se implemente aún.

`GET /session/context` sigue siendo el listado canónico; debe usar `AthleteProfile.display_name`, filtrar borrados y reflejar B tras refresh. No hace falta endpoint de selección: header/localStorage es selección efímera; default es persistencia separada.

## Aislamiento inicial por dominio

Crear Athlete no inserta nada fuera de `athlete_profiles` y `user_athlete_memberships`.

| Dominio | Modelo/tablas | Scope | B recién creado |
| --- | --- | --- | --- |
| Actividades | `CompletedActivity` | FK/index `athlete_id`; queries por current athlete | 0 |
| Detalle/evidencia | `ActivityLap`, `ActivityStream`, `ActivityRouteEvidence`, `ActivityEvidenceState` | Indirecto por activity scoped | vacío |
| Métricas | `ActivityMetric` | Indirecto por activity scoped | vacío |
| Carga por actividad | `ActivityTrainingLoad` | Indirecto por activity scoped | vacío |
| Agregados | `AthleteDailyTrainingLoad`, `AthleteWeeklyTrainingLoad` | FK `athlete_profile_id` | vacío |
| Fuerza | `ManualStrengthSession` y loads | FK `athlete_id`; loads indirectos | vacío |
| Rendimiento | `AthletePerformanceProfileVersion`, `AthletePerformanceReference`; zonas derivadas | FK `athlete_profile_id` | sin versiones/referencias/zonas |
| Training Status | `AthleteDailyTrainingStatus` | FK `athlete_profile_id` | vacío |
| Dashboard/estadísticas | consultas sobre actividades/agregados scoped | current athlete | ceros/empty state |
| Strava | `IntegrationAccount`, `OAuthCredential` | cuenta FK a athlete; credencial indirecta | no conectado |
| Imports/jobs | `SyncJob` | FK `athlete_id` y cuenta coherente | ninguno |
| Webhooks | `WebhookEvent` | indirecto por IntegrationAccount/SyncJob | ninguno |
| Auditoría | `AuditEvent.athlete_id` nullable | evento explícito | sólo eventual evento de alta si se decide |
| Calendario/planes | no hay modelo funcional actual | sin datos persistidos | no aplica/vacío |
| Salud | no hay modelo deportivo persistido actual | pantalla sin dominio propio | no aplica/vacío |

## Strava

OAuth state liga `user_id` y `athlete_id`; callback vuelve a validar membership y capability. `IntegrationAccount` pertenece a Athlete, OAuthCredential a IntegrationAccount, actividades/jobs a Athlete y cuenta. Existe UNIQUE global `(provider, external_account_id)` además del único activo por `(athlete_id, provider)`.

Por ello B puede conectar una cuenta Strava distinta. La misma identidad Strava ya vinculada a A se rechaza con `409 strava_external_account_already_linked`; no se duplica ni transfiere silenciosamente. Una transferencia futura exigiría flujo explícito, confirmación, tratamiento de historial y auditoría, fuera de 0.8C.

## Permisos y actor de creación

Cualquier User autenticado, activo y no eliminado puede crear su propio Athlete; no necesita ser owner de otro Athlete. Coach/editor/viewer sobre A no crea “en nombre de A”: la operación deriva owner exclusivamente de `current_user`.

La membership nueva usa `role=owner`; `capabilities_for_role('owner')` concede todas las capacidades actuales: lectura, recálculo, CRUD de fuerza, perfil/referencias, lectura/gestión Strava, importación, enriquecimiento, evidencia y limpieza de ubicación. No se crea un sistema de permisos nuevo.

## Prerrequisitos obligatorios de 0.8C.2

1. Eliminar `AthleteProfile.user_id` legado y adaptar seed/fixtures.
2. Añadir `AthleteProfile.display_name` y usarlo en contexto/selector.
3. Filtrar `AthleteProfile.deleted_at IS NULL` en `resolve_current_athlete`, `/session/context` y callback OAuth. Un atleta borrado sí puede aparecer hoy mediante una membership activa.
4. Añadir el índice parcial de un default activo por User.
5. Ampliar auditor con: atleta sin owner activo; múltiples owners si la política lo prohíbe (por ahora al menos uno); membership activa a atleta borrado; múltiples defaults; y, antes de retirar la columna, incoherencia owner legado/membership.

## Matriz de validación real 0.8C.4

1. Registrar IDs y conteos de A; confirmar cuenta y sesión.
2. Crear B desde el flujo de autoservicio; comprobar Athlete + owner membership y ausencia de más filas.
3. Confirmar selector A/B con nombres y roles; B queda seleccionado sin cambiar default de A.
4. En B comprobar 0 actividades, fuerza, perfiles, referencias, cargas, agregados, status, jobs e integración Strava.
5. Intentar acceder con IDs de recursos de A bajo header B; esperar 404/403 según contrato, nunca datos.
6. Conectar nada: confirmar estado Strava B no conectado y A intacto.
7. Volver A y comparar IDs/conteos/historial con baseline.
8. Recargar: selección persistida válida; default sigue siendo A.
9. Crear datos propios mínimos en B en una fase autorizada; verificar que no aparecen en A.
10. Confirmar `/settings/account`, email, nombre User, password y sesión idénticos al alternar A/B.
11. Con User distinto y Athlete C, manipular `X-TriCoach-Athlete-Id: C`; esperar `403 athlete_not_authorized`.

## Tests futuros

### 0.8C.2 backend

- Migración upgrade/backfill/preflight/downgrade seguro en PostgreSQL y SQLite.
- Dos Athletes owner para el mismo User; mismo nombre permitido.
- Usuario sin atleta: primer Athlete owner/default.
- Usuario con A: B owner/no-default, A intacto.
- Creación atómica y rollback en cada fallo; concurrencia/default.
- Payload extra, `user_id`, role, owner y athlete ID rechazados.
- Cuenta inactiva/no autenticada; CSRF y Origin.
- B sin filas en todos los dominios inventariados.
- Contexto lista nombres A/B; borrados ausentes.
- Cabecera ajena rechazada; recursos cruzados ocultos.
- Owner obtiene capabilities completas; sesiones/auth/account no cambian.
- Strava externo global duplicado rechazado.
- Auditor ampliado a cero y detectando fixtures corruptas.

### 0.8C.3 frontend

- Acción “Nuevo atleta” en selector y empty state sin atleta.
- Formulario mínimo, validación, whitelist y doble submit deshabilitado.
- Cliente POST sin header deportivo, con cookies/CSRF.
- 201 refresca contexto, selecciona/persiste B y navega a empty/onboarding.
- A permanece default; selector muestra nombres duplicados sin colisión lógica.
- Error conserva input y no cambia atleta/contexto.
- Cuenta y AuthContext no cambian al seleccionar Athlete.
- Responsive, teclado, labels, live regions y regresión completa.

## Roadmap

### 0.8C.2 — Backend alta multiatleta

Migración 0018, preflight, modelo/seed, hardening de borrados/default, `AthleteApplication`, `POST /athletes`, actualización de `/session/context`, tests y auditor.

### 0.8C.3 — Frontend nuevo atleta

Acción en selector y empty state, formulario mínimo, cliente tipado, refresh con selección preferida, feedback y tests.

### 0.8C.4 — Prueba real segundo atleta

Crear B en la cuenta real únicamente después de cerrar 0.8C.2/3; ejecutar la matriz A/B, conservar baseline y documentar resultados.

No se propone 0.8C.5 ahora. Un onboarding amplio puede planificarse después de validar el MVP real; 0.8C.3 sólo necesita un empty state con siguientes pasos.

## Estado de implementación

- 0.8C.1 — designed.
- 0.8C.2A — migration/hardening implemented, pending real DB application.
- 0.8C.2B — planned.
- 0.8C.3 — planned.
- 0.8C.4 — planned.

La retirada de la FK legacy `AthleteProfile.user_id -> users.id ON DELETE CASCADE` elimina el borrado físico implícito de Athlete al borrar User. En el producto las cuentas usan estados y `deleted_at`; autenticación bloquea usuarios no utilizables. No se introduce una política nueva de borrado físico. Tras 0018, borrar User elimina sus memberships, pero el Athlete sobrevive para otros owners/coaches y sus datos deportivos no quedan bajo `delete-orphan` desde User. El auditor exige al menos un owner activo por Athlete.
