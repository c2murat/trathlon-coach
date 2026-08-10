# Arquitectura de cuenta de usuario — 0.8B.1

Estado del roadmap:

- 0.8B.1: auditoría y diseño completados.
- 0.8B.2: perfil de cuenta backend implementado.
- 0.8B.3: cambio seguro de contraseña implementado.
- 0.8B.4: frontend de Cuenta planificado.

## Implementado actualmente

La petición HTTP se resuelve en capas independientes:

```text
cookie HttpOnly → UserAuthSession → AuthenticatedUser(User.id)
                                      ↓
X-TriCoach-Athlete-Id → UserAthleteMembership activa → CurrentAthleteContext
                                      ↓
                          rol/capacidades → dominio deportivo
```

La sesión identifica solo al usuario y no contiene atleta. `get_current_user` rechaza sesiones ausentes, expiradas, revocadas o pertenecientes a usuarios no activos/eliminados. Las mutaciones autenticadas aplican CSRF y, cuando está presente, validación de Origin.

## Modelo actual

### User: cuenta e identidad

| Campo | Responsabilidad | Autoservicio previsto |
| --- | --- | --- |
| `id` | Identidad interna de cuenta | Solo lectura |
| `email` | Correo de acceso mostrado | Solo lectura en 0.8B |
| `normalized_email` | Clave canónica única de login | Nunca público/editable directamente |
| `auth_subject` | Identificador interno/externo único legado | Nunca público/editable |
| `password_hash` | Credencial Argon2 nullable | Nunca se devuelve; solo operación dedicada |
| `status` | `active`, `disabled`, `pending_deletion` | Interno |
| `timezone` | Preferencia general de cuenta actualmente duplicada con atleta | No editar hasta definir precedencia |
| `display_name` | Nombre visible de cuenta | Editable en 0.8B.2 |
| `last_login_at` | Evento de seguridad | Solo lectura |
| `deleted_at` | Borrado lógico de cuenta | Interno |
| `created_at`, `updated_at` | Auditoría temporal | Solo lectura (`created_at`); `updated_at` opcional en API |

`normalized_email` y `auth_subject` son únicos. `status` tiene check constraint. El borrado físico de User propaga por FK/cascade a sesiones, memberships y al perfil deportivo propietario legado.

### AthleteProfile: sujeto deportivo

Contiene `id`, `timezone`, `unit_system`, `birth_year`, `sex_for_training_context`, `height_m`, `weight_kg`, `experience_level`, `deleted_at`, timestamps y el `user_id` propietario legado. Altura/peso tienen constraints positivos y `unit_system` admite `metric`/`imperial`.

El atleta es el scope de actividades, integraciones Strava, perfiles y referencias de rendimiento, cargas, fuerza, métricas, jobs y training status. Ninguno de estos datos pertenece al perfil de cuenta.

### Relación

El acceso vigente es many-to-many mediante `UserAthleteMembership(user_id, athlete_profile_id, role, is_active, is_default)`. La pareja usuario-atleta es única, ambas FK usan `ON DELETE CASCADE`, hay índices por cada FK y el rol se limita a `owner`, `coach`, `editor`, `viewer`.

Coexiste `AthleteProfile.user_id`, único y no nullable, que representa el propietario legado y crea una relación adicional User 1 → 0..1 AthleteProfile. Esta columna no es la autoridad para autorizar: la autoridad es la membership activa. Restringe temporalmente que una cuenta sea propietaria legado de más de un atleta y debe resolverse en un bloque multiatleta específico, no dentro de cuenta autoservicio.

## Hallazgos de seguridad y deuda

- No existen `/users/{id}` ni endpoints genéricos de autoservicio que acepten un usuario arbitrario. Esto evita una superficie IDOR innecesaria.
- Los DTO actuales de autenticación y sesión exponen únicamente identidad segura, memberships y capacidades; no exponen hashes, tokens de sesión/CSRF ni credenciales OAuth.
- Las consultas deportivas usan `CurrentAthleteContext` y scope por `athlete_id`; los recursos ajenos se rechazan o se presentan como no encontrados según el contrato.
- `resolve_current_athlete` requiere membership activa, maneja cero memberships, selección ambigua y múltiples defaults. Las FK evitan memberships huérfanas y la restricción única evita duplicados.
- Una cuenta sin membership obtiene lista vacía en `/session/context`; las dependencias deportivas devuelven `404 athlete_profile_not_found`.
- Una cuenta deshabilitada o eliminada no puede resolver una sesión real.
- Riesgo existente: `resolve_current_athlete` no excluye explícitamente `AthleteProfile.deleted_at`. Debe endurecerse y auditarse fuera de 0.8B.1 antes de depender del borrado lógico de atletas.
- La unicidad de un único default activo por usuario no está garantizada por constraint parcial; se detecta en runtime/auditor. Es deuda multiatleta, no de cuenta.
- `User.timezone` y `AthleteProfile.timezone` requieren una política de precedencia antes de exponer una preferencia editable.

## Implementado en 0.8B.2 — Perfil de cuenta

### API

```text
GET   /account
PATCH /account
```

No se crearán rutas `/users/{user_id}`. Ambas operaciones obtendrán el usuario exclusivamente desde `get_current_user`; no aceptarán `user_id`, `athlete_id`, membership ni rol en path, query o body.

Respuesta prevista:

```json
{
  "id": "uuid",
  "email": "persona@example.com",
  "display_name": "Persona",
  "created_at": "2026-08-10T00:00:00Z",
  "last_login_at": "2026-08-10T08:00:00Z"
}
```

`last_login_at` puede ser null. No se incluirán `normalized_email`, `auth_subject`, `password_hash`, estado interno, borrado, sesiones, tokens, memberships ni atleta.

`PATCH /account` aceptará exclusivamente:

```json
{"display_name":"Nuevo nombre"}
```

`display_name` se normaliza colapsando whitespace. El resultado admite hasta 200 caracteres.
`null`, una cadena vacía o solo whitespace eliminan el nombre visible y persisten `NULL`; el shell puede continuar usando el email como fallback. El payload debe incluir explícitamente el campo y cualquier propiedad adicional produce 422.

Schema previsto:

- `AccountResponse`: `id`, `email`, `display_name`, `created_at`, `last_login_at`.
- `AccountUpdateRequest`: únicamente `display_name`, nullable, longitud normalizada máxima 200 y `extra="forbid"`.
- Debe rechazarse payload vacío si no produce cambio y cualquier `id`, `email`, `password_hash`, `status`, `deleted_at`, `last_login_at`, `user_id`, `athlete_id` o relación.

El cambio de email queda fuera de 0.8B: requiere reautenticación, normalización/unicidad, verificación y notificación propias.

### Servicio de aplicación

Crear `AccountApplication` en vez de ampliar el servicio de sesiones:

- `get_account(user_id)` carga por la identidad autenticada y rechaza cuenta inexistente/inactiva.
- `update_account(user_id, display_name)` aplica whitelist y flush; el router controla commit/rollback.

El router traduce HTTP y dependencias; schemas validan el contrato; `AccountApplication` contiene casos de uso; SQLAlchemy conserva persistencia. `AuthenticationApplication`/`UserAuthSessionService` continúa gestionando sesiones y credenciales.

## Implementado en 0.8B.3 — Cambio de contraseña

### Contrato

```text
POST /account/password
```

```json
{
  "current_password": "...",
  "new_password": "..."
}
```

`PasswordChangeRequest` utilizará `SecretStr`, límites compatibles con la política central existente (12–1024), `extra="forbid"` y nunca serializará secretos en respuesta/logs. Éxito: `204 No Content`.

### Flujo transaccional

1. Resolver internamente sesión y User mediante la cookie y `get_current_auth_session`; el cliente no aporta identificadores de sesión.
2. Exigir CSRF y Origin con la protección central ya existente.
3. Cargar User por el id autenticado; exigir `status == active`, `deleted_at IS NULL` y `password_hash` presente.
4. Verificar `current_password` con `verify_and_update_password` de pwdlib usando `400 current_password_invalid`; cualquier rehash intermedio se descarta.
5. Validar `new_password` con `validate_password`; no crear una política paralela.
6. Rechazar con `400 new_password_unchanged` una contraseña nueva igual a la actual; generar Argon2 con `hash_password` solo después de todas las validaciones.
7. Revocar todas las demás sesiones activas del mismo User dentro de la misma transacción.
8. Commit único y respuesta `204 No Content`; ante cualquier fallo, rollback y hash/sesiones sin cambios.

`last_login_at` no cambia porque cambiar contraseña no es un login.

El endpoint utiliza la protección central de CSRF y Origin, no crea ni renueva cookies, no registra secretos y no depende de atletas, memberships o selección deportiva.

### Política de sesiones elegida

Conservar la sesión actual y revocar todas las demás sesiones activas. La sesión actual se identifica en backend resolviendo el token raw de la cookie a `UserAuthSession`; el token nunca sale del proceso ni se añade al DTO. El servicio debe recibir el `current_session.id` o la entidad ya resuelta y ejecutar un UPDATE scoped por `user_id`, `revoked_at IS NULL`, `expires_at > now` e `id != current_session.id`.

Si no se puede resolver inequívocamente la sesión actual, la operación debe fallar de forma segura; no debe preservar una sesión por un identificador proporcionado por el cliente.

Errores previstos: `401 authentication_required` para sesión/cuenta inválida; `400 current_password_invalid` o equivalente genérico para contraseña actual incorrecta; `422` para nueva contraseña que incumpla política; `403` para CSRF/Origin. Nunca se devuelven contraseñas, hashes o recuentos sensibles de sesiones.

## Diseño frontend para 0.8B.4

La navegación prevista es:

```text
Configuración
├── Cuenta                 /settings/account
└── Perfil de rendimiento /settings/performance-profile
```

`/auth/me` seguirá siendo la fuente mínima de identidad y estado de autenticación del shell. `GET /account` será una consulta independiente de detalles editables, cargada solo al abrir Cuenta.

Después de actualizar `display_name`, la respuesta segura de PATCH debe actualizar la identidad en memoria de `AuthContext` mediante un método explícito (`refreshUser()` consultando `/auth/me` o `setUser` encapsulado). `AthleteContext` también contiene una copia del usuario procedente de `/session/context`; para evitar dos nombres divergentes, el shell debe usar preferentemente `AuthContext.user`, y el contexto deportivo debe reservarse para memberships/atleta. Como alternativa mínima, refrescar `/auth/me` y `/session/context` coordinadamente hasta eliminar esa duplicación en un cambio acotado.

El cliente HTTP común añadirá `account()`, `updateAccount()` y `changePassword()`; seguirá centralizando cookies, CSRF y Origin del navegador sin almacenar tokens.

## Escenarios obligatorios futuros

### 0.8B.2

- Usuario autenticado obtiene únicamente su propia cuenta; no existe selector arbitrario.
- Sin autenticación: 401.
- Respuesta sin credenciales, hashes, sesiones, relaciones ni atleta.
- PATCH modifica solo `display_name`; campos internos y extras son rechazados.
- Usuario A nunca consulta/modifica B y ninguna operación cambia memberships u ownership.
- Cuenta sin atleta puede consultar/modificar su cuenta.

### 0.8B.3

- Contraseña actual correcta/incorrecta y cuenta inexistente/deshabilitada/eliminada.
- Hash inmutable ante fallo y distinto/verificable tras éxito.
- Login nuevo funciona y el antiguo deja de funcionar.
- Sesión actual se conserva; otras activas se revocan; expiradas/revocadas permanecen semánticamente inactivas.
- `last_login_at` no cambia.
- CSRF y Origin se aplican; payloads extra se rechazan.
- No hay secretos en DTO, logs o excepciones.
- Cambio para User A no altera User B ni selección/ownership de atletas.

## Persistencia

0.8B.2 no necesita migración: User ya contiene `display_name`, timestamps, email y `last_login_at`.

0.8B.3 tampoco necesita migración: User ya contiene `password_hash` y `UserAuthSession` contiene todo lo necesario para preservar una sesión y revocar las demás.

No se modificará ahora `AthleteProfile.user_id`. Su retirada o reinterpretación requerirá una migración multiatleta dedicada con backfill, prechecks y actualización de ownership, fuera del alcance de 0.8B.

## Fuera de alcance

Registro, recuperación de contraseña, email/verificación/notificaciones, eliminación de cuenta, OAuth social, MFA, passkeys, administración, impersonación, gestión de memberships/atletas, sesiones visuales, revocación manual global, despliegue, Redis, TLS y cambios generales del dominio deportivo.