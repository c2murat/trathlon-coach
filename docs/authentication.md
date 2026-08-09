# Autenticación HTTP

La versión 0.8A.2 completa el primer flujo de navegador con sesiones opacas server-side. No usa JWT ni almacena autenticación en `localStorage` o `sessionStorage`.

## Separación de responsabilidades

1. `get_current_user` autentica exclusivamente al `User`.
2. `CurrentAthleteContext` interpreta `X-TriCoach-Athlete-Id` y valida la membresía.
3. `UserAthleteMembership`, roles y capacidades autorizan la operación.

`UserAuthSession` no contiene `athlete_id`; una sesión válida nunca concede acceso a un atleta por sí sola.

## Configuración

```dotenv
TC_AUTH_MODE=development
TC_SESSION_COOKIE_NAME=tricoach_session
TC_CSRF_COOKIE_NAME=tricoach_csrf
TC_SESSION_TTL_SECONDS=1209600
TC_SESSION_COOKIE_SECURE=false
TC_SESSION_COOKIE_SAMESITE=lax
TC_SESSION_COOKIE_PATH=/
TC_CSRF_HEADER_NAME=X-CSRF-Token
```

`development` conserva la identidad local solo en entornos de desarrollo y test. `session` exige una sesión real y nunca hace fallback local. Para HTTP local, `Secure=false`; bajo HTTPS debe configurarse `true`. CORS mantiene `allow_credentials=True` con orígenes explícitos.

## Endpoints

- `POST /auth/login`: recibe `{"email":"...","password":"..."}`. Normaliza el correo, verifica Argon2, estado activo y ausencia de borrado. Todo fallo de credenciales devuelve `401 invalid_credentials`. En un modo distinto de `session` devuelve `409 authentication_mode_mismatch`. La respuesta solo contiene `id`, `email`, `display_name` y `authentication_mode`.
- `GET /auth/me`: usa `get_current_user` y devuelve el mismo DTO seguro. En modo sesión sin cookie válida devuelve `401 authentication_required`; en desarrollo devuelve la identidad local.
- `POST /auth/logout`: con una sesión válida exige CSRF, la revoca y elimina ambas cookies. Sin cookie o con sesión ya inválida limpia las cookies y responde `204`, por lo que es idempotente. Un CSRF incorrecto sobre una sesión válida devuelve `403 csrf_validation_failed`.

## Cookies y CSRF

El login crea dos secretos independientes mediante `secrets.token_urlsafe(32)` y solo persiste sus hashes SHA-256:

- `tricoach_session` (o `TC_SESSION_COOKIE_NAME`): token raw, siempre `HttpOnly`, con `Secure`, `SameSite`, `Path`, `Max-Age` y `Expires` configurados.
- `tricoach_csrf` (o `TC_CSRF_COOKIE_NAME`): token CSRF raw, legible por JavaScript (`HttpOnly=false`) y con el resto de atributos coherentes con la sesión.

En modo `session`, la dependencia central de autenticación exige `TC_CSRF_HEADER_NAME` en toda petición autenticada `POST`, `PUT`, `PATCH` o `DELETE`, y compara de forma constante su hash con el de la sesión. `GET`, `HEAD` y `OPTIONS` no lo requieren. El login queda excluido porque todavía no existe una sesión autenticada. Los endpoints externos que no dependen de `get_current_user` no quedan protegidos accidentalmente.

El cliente HTTP común usa siempre `credentials: "include"`; para métodos inseguros, salvo login, lee la cookie CSRF en el momento de la petición y añade `X-CSRF-Token`. No persiste ninguno de los dos secretos.

## Contraseña inicial

Desde `backend`, con el entorno configurado:

```powershell
.venv\Scripts\python.exe scripts\set_user_password.py --email usuario@ejemplo.com
```

El script busca el usuario por correo normalizado, solicita dos veces la contraseña mediante `getpass`, exige coincidencia y un mínimo de 12 caracteres, genera Argon2 y hace un único commit. No acepta contraseñas por argumento ni imprime contraseña o hash.

## Persistencia

La migración `0017_authentication_base` contiene todo el esquema necesario. `user_auth_sessions` guarda `id`, `user_id`, `token_hash`, `csrf_token_hash`, `created_at`, `expires_at` y `revoked_at`. Se permiten varias sesiones simultáneas por usuario.

## Fuera de alcance

No se incluyen registro público, recuperación o cambio de contraseña en UI, OAuth de usuario, invitaciones, gestión de memberships, JWT, refresh tokens, “recordarme”, cierre global de sesiones ni despliegue.