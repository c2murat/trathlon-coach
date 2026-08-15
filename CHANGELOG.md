## 0.8E.5 — Registro self-service desde navegador

- Restringe la creación posterior de AthleteProfiles a cuentas internas Owner; Athlete y Coach no ven ni pueden invocar `POST /athletes`.

- Añade registro público exclusivo para Atleta y Entrenador, con account plan persistente separado del rol athlete-scoped.
- Crea atómicamente el perfil propio del Atleta y permite al Coach empezar sin memberships en un estado estable.
- Reutiliza Argon2, normalización de email, sesiones, CSRF y rate limiting existentes; Owner no es registrable.

## 0.8E.4 — Modelo definitivo de roles y permisos

- Define OWNER como administración athlete-scoped, ATHLETE como identidad self-service y COACH como entrenador de perfiles previamente asignados.
- Separa las capabilities Strava de conexión y desconexión; Coach puede consultar, sincronizar y desconectar, pero no conectar ni reconectar.
- Protege Salud y perfil físico frente a Coach, mantiene rendimiento editable y evita leakage de capabilities entre memberships.
- Añade revocación administrativa transaccional, idempotente y con dry-run para memberships, preservando el invariante de controller.
- Documenta límites actuales de planificación y autoría de sesiones sin introducir migraciones ni endpoints ficticios.
- Muestra en Inicio el rol de producto de la membership activa, actualizado al cambiar de atleta, sin añadir roles al selector.
## 0.8D.3 — Frontend del perfil deportivo

- Añade `Configuración → Perfil deportivo` con formulario athlete-scoped, PATCH parcial y semántica null explícita.
- Presenta altura y peso en unidades métricas o imperiales conservando metros/kg como valores canónicos.
- Muestra la completitud derivada y un banner progresivo no bloqueante en Inicio.
- Protege el cambio A/B frente a datos dirty y respuestas stale, respeta capabilities y mantiene Cuenta y Perfil de rendimiento independientes.
- Incorpora estados accesibles, diseño responsive y pruebas bajo React StrictMode.

## 0.8D.2 — Backend del perfil deportivo básico

- Añade `GET/PATCH /athlete/profile` con scope del Athlete activo y aislamiento multiatleta.
- Incorpora completitud básica derivada, sin estado persistido.
- Añade la capability `edit_athlete_profile` para owner/editor y mantiene coach/viewer en solo lectura.
- Valida y actualiza parcialmente nombre, timezone, unidades y contexto fisiológico básico sin tocar cuenta, rendimiento, actividades ni Strava.
## 0.8C.3 — Frontend Nuevo atleta

- Añade “Nuevo atleta” al selector y “Crear mi primer atleta” al estado sin perfiles.
- Incorpora un formulario accesible y responsive con nombre, zona horaria y unidades.
- Crea mediante la API account-scoped, refresca el contexto y selecciona/persiste inmediatamente el nuevo atleta.
- Evita dobles envíos, conserva los datos ante fallos y permite recuperar una creación cuyo refresh todavía no la muestre sin repetir el POST.
# Changelog

## 0.8D.4 — Strava multiatleta athlete-scoped

- Añadida `Configuración → Conexiones` como gestión única y contextual de conexión, reconexión, desconexión y sync de Strava.
- El estado se limpia y recarga por Athlete con protección frente a respuestas stale; Inicio queda como resumen enlazado.
- Ampliadas las pruebas A/B y la cobertura del binding OAuth, conflicto de identidad externa y aislamiento de importación existentes.
- Ampliado el auditor read-only con cuentas de integración ligadas a Athlete eliminado y providers no normalizados.
- No se conectó una segunda cuenta Strava real ni se modificó la base real.

## 0.8C.2B — API backend de alta de Athlete

- Añadido `POST /athletes` como operación autenticada de cuenta, independiente del Athlete activo.
- Creación atómica de `AthleteProfile` y membership owner, con primer Athlete como default y preservación del default existente.
- Añadidas validación estricta, protección CSRF/Origin, bloqueo por User y pruebas de aislamiento, rollback y concurrencia.
- No se creó un segundo Athlete real ni se añadió frontend de onboarding.

## 0.8B.4 — Frontend de Cuenta

- Añadida `/settings/account` bajo Configuración con datos seguros y edición de `display_name`.
- Añadido cambio de contraseña accesible, feedback en español y cliente central con CSRF/cookies.
- AppShell refresca nombre e inicial desde AuthContext sin mezclar estado deportivo.

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

## 0.8C.2A — Base persistente multiatleta

- Añadida la migración segura 0018 con `display_name`, ownership exclusivo por memberships y un único default activo por User.
- Endurecida la exclusión de atletas eliminados en contexto, selección y OAuth Strava.
- Añadidos preflight, auditoría compatible 0017/0018, pruebas PostgreSQL temporales y runbook.
- La migración PostgreSQL real queda pendiente de revisión y aplicación manual; no se creó un segundo Athlete.

## 0.8D.6 - role athlete y self-access

- Incorpora `athlete` como relacion self-service explicita y una matriz central, auditable y deny-by-default de capabilities deportivas.
- Mantiene permisos por membership y Athlete seleccionado, sin union global, bypass por identidad ni cambios en owner/editor/coach/viewer.
- Adapta auditor y preflight a la invariante controladora `owner OR athlete`.
- Prepara la migracion 0019 del CHECK de roles sin backfill ni cambios de datos reales, con tests de dominio, endpoints, contexto, aislamiento y migracion.
- En ese cierre de codigo no se convirtieron memberships ni se conecto Strava; la validacion real posterior se documenta en 0.8D.5.

## 0.8E.1 - provisioning interno de User atleta

- Prepara un CLI seguro para vincular un User nuevo con un AthleteProfile existente mediante role athlete.
- Reutiliza normalizacion de email, politica/hash productivos, contraseña oculta, confirmacion, dry-run y transaccion atomica.
- Añade unicidad DB de una identidad athlete activa por AthleteProfile, auditor/preflight y tests de login y aislamiento.
- La implementacion no creo a Jenny real ni modifico Strava; la operacion real posterior quedo validada y cerrada documentalmente.


## 0.8D.5 - segunda integracion Strava real validada

- Validada una segunda cuenta Strava real con identidad externa distinta y primer sync de Jenny completado con 451 actividades.
- Generadas 451 cargas por actividad, 409 agregados diarios, 137 semanales y 1127 estados diarios.
- Confirmado aislamiento A/B de accounts, credentials, jobs, activities, loads, aggregates y status.
- Auditor Strava y auditor multiatleta finalizaron con issue_count 0.
- 0.8D.5 queda cerrada; 0.8E.1 tambien quedo validada y cerrada documentalmente.


## 0.8E.2 - normalizacion de roles multiusuario

- Incorpora una operacion administrativa transaccional e idempotente para cambiar el role de una membership existente.
- Añade CLI con dry-run y confirmacion, proteccion del ultimo controller y rechazo previo de una segunda identidad athlete.
- Refuerza tests de owner/coach/athlete por Athlete seleccionado y ausencia de capability leakage.
- Documenta la normalizacion Carlos owner propio, coach de Jenny y Jenny athlete self-service sin tocar Strava.

## 0.8E.3 - pipeline automatico post-Strava

- Encadena automaticamente import, Training Load, agregados combinados y Training Status dentro del SyncJob athlete-scoped.
- Persiste alcance, etapa y progreso sin migracion; los fallos derivados conservan el import y permiten retry idempotente desde navegador.
- Inicia la primera preparacion tras OAuth, protege concurrencia por cuenta y mantiene rate limits/enrichment remoto separados.
- Actualiza la UX con estados de importacion/procesamiento, errores recuperables, accesibilidad y guardas stale por Athlete.
- Los scripts de backfill quedan reservados para mantenimiento y dejan de ser necesarios en el flujo normal.
