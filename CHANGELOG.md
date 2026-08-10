# Changelog

## 0.8B.3 — Cambio seguro de contraseña

- Añadido `POST /account/password` con verificación de la contraseña actual y política Argon2/pwdlib 12–1024.
- La sesión actual se conserva y las demás sesiones activas del usuario se revocan en la misma transacción.
- Respuesta `204`, whitelist estricta, CSRF/Origin centralizados y ausencia de dependencia del atleta.

## 0.8B.2 — Perfil de cuenta backend

- Añadidos `GET /account` y `PATCH /account` para autoservicio del usuario autenticado.
- La respuesta expone únicamente identidad y timestamps seguros; solo `display_name` es editable.
- Whitelist estricta, normalización de nombre, protección CSRF/Origin e independencia total del atleta.
## 0.8A.3 — Hardening de autenticación y sesiones

- Rate limiting configurable de login por IP y correo normalizado, con estado in-memory acotado.
- Máximo configurable de sesiones activas y revocación de las más antiguas.
- Cleanup administrativo y auditor determinista de autenticación.
- Validación productiva de cookies seguras y defensa Origin complementaria a CSRF.
- Rehash Argon2 oportunista y mensaje frontend específico para HTTP 429.
## 0.8A.2 — Login, logout y sesión HTTP real

### Añadido

- `POST /auth/login`, `GET /auth/me` y `POST /auth/logout` con cookies de sesión HttpOnly.
- Cookie CSRF legible y validación central para métodos inseguros autenticados.
- Bootstrap administrativo de contraseñas y flujo React de login, restauración y logout.

### Seguridad

- Errores de credenciales uniformes y verificación Argon2 ficticia cuando no existe un hash usable.
- `credentials: include` y `X-CSRF-Token` centralizados en el cliente HTTP.
- Sin JWT, secretos en JSON o almacenamiento web; la sesión continúa sin `athlete_id`.
## 0.8A.1 — Base de autenticación real

### Añadido

- Hash y verificación de contraseñas con Argon2.
- Sesiones opacas server-side con tokens de sesión y CSRF hasheados.
- Configuración explícita `development`/`session`, cookie y TTL.
- Resolución de usuario desde cookie, expiración y revocación idempotente.
- Migración `0017_authentication_base` y pruebas de seguridad y aislamiento.

### Seguridad

- Sin JWT, tokens en almacenamiento web ni secretos raw en base de datos.
- Sin fallback a identidad de desarrollo en modo sesión.
- La sesión identifica solo al usuario; selección de atleta y autorización permanecen separadas.

### No incluido

- Endpoints o interfaz de login/logout, registro, recuperación de contraseña y OAuth de usuario.


## 0.7G — 2026-08-08

### Añadido

- Membresías usuario–atleta y resolución explícita del atleta activo.
- Roles, capacidades centralizadas, selector frontend y `GET /session/context`.
- Auditor multiatleta de solo lectura.
- Inicio OAuth seguro mediante `POST /integrations/strava/connect/start`.

### Cambiado

- Consultas y recursos deportivos aislados por atleta.
- Strava aislado por atleta y jobs ligados explícitamente al atleta.
- Backfills con alcance explícito y frontend con identidad y permisos dinámicos.

### Seguridad

- Eliminado el fallback `current_user.id → athlete_id`.
- Recursos ajenos tratados como no encontrados y `viewer` limitado a lectura.
- Coherencia relacional atleta–cuenta y unicidad de cuenta activa reforzadas.
- Tokens y estados OAuth aislados por atleta.

### Migraciones

- `0014_user_athlete_memberships`.
- `0015_strava_oauth_state_athlete`.
- `0016_multi_athlete_integrity`.

### No incluido

- Autenticación pública, registro o gestión de miembros.
- Despliegue productivo.
