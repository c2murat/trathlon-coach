# Onboarding deportivo por atleta — arquitectura 0.8D.1

Estado: auditoría cerrada y contrato propuesto; sin cambios de runtime ni migraciones.

## 1. Estado actual

Evidencia: rama `sprint-0.8a-authentication`, HEAD `65a2026 fix(athlete): clarify athlete selector role labels`, árbol inicialmente limpio. PostgreSQL está en `0018_athlete_onboarding` (current=head). Preflight: schema `0018`, issue_count 0, 2 AthleteProfiles, 2 memberships activas/owner y 1 default. Carlos Murat y Jenny Ruiz están aislados; solo Carlos tiene IntegrationAccount Strava.

DECISIÓN: 0.8D continuará sobre la separación User → memberships → AthleteProfile. IMPACTO: ningún dato deportivo se mueve a User y ningún endpoint deportivo autoriza por identidad de cuenta sin membership.

## 2. Inventario User

User es cuenta/autenticación, no atleta.

| Campo | Tipo / null / constraint | Introducción | Responsabilidad / edición actual |
|---|---|---|---|
| id | UUID PK, no null | 0001 | identidad interna; no editable |
| email | varchar(320), no null | 0001 | correo de acceso; lectura en Cuenta |
| normalized_email | varchar(320), no null, unique | 0001 | login canónico; no público/editable |
| auth_subject | varchar(255), no null, unique | 0001 | identidad de autenticación; interno |
| password_hash | text nullable | 0017 | secreto; solo operación password |
| status | varchar(32), no null, active/disabled/pending_deletion | 0001 | habilitación de cuenta; interno |
| timezone | varchar(64), no null, ORM UTC | 0001 | preferencia de cuenta; no es timezone deportiva del Athlete |
| display_name | varchar(200), nullable | 0001 | nombre visible de cuenta; editable en Cuenta |
| last_login_at | timestamptz nullable | 0001 | auditoría de acceso; lectura |
| deleted_at | timestamptz nullable | 0001 | borrado lógico; interno |
| created_at / updated_at | timestamptz, no null | 0001 | auditoría temporal |

## 3. Inventario AthleteProfile

| Campo | Tipo | Nullable/default/constraint | Migración | Uso backend | Uso frontend / editable hoy | Semántica |
|---|---|---|---|---|---|---|
| id | UUID PK | no null; uuid4 ORM | 0001 | scope/FK | contexto; no | atleta |
| display_name | varchar(200) | no null; trim 1..200 | 0018 | contexto/alta | selector/alta; solo al crear | identidad deportiva |
| timezone | varchar(64) | no null; ORM UTC; API alta valida IANA | 0001 | dashboard/alta | alta; no después | zona deportiva |
| unit_system | varchar(16) | no null; metric/imperial; ORM metric | 0001 | alta | alta; no después | presentación |
| birth_year | integer | nullable; sin check específico | 0001 | sin uso runtime encontrado | no expuesto | contexto fisiológico aproximado |
| sex_for_training_context | varchar(32) | nullable; sin enum/check | 0001 | sin uso algorítmico encontrado | no expuesto | contexto deportivo, no identidad User |
| height_m | numeric(5,3) | nullable; >0 | 0001 | sin cálculo encontrado | no expuesto | altura canónica en metros |
| weight_kg | numeric(6,3) | nullable; >0 | 0001 | sin cálculo directo encontrado | no expuesto | snapshot básico actual en kg |
| experience_level | varchar(32) | nullable; sin enum/check | 0001 | sin uso encontrado | no expuesto | experiencia descriptiva |
| deleted_at | timestamptz | nullable | 0001 | exclusión de contexto | no | borrado lógico |
| created_at / updated_at | timestamptz | no null | 0001 | auditoría | no | temporal |

`user_id` singular fue eliminado en 0018. La única relación User↔Athlete es `UserAthleteMembership`.

## 4. Inventario Performance Profile

`AthletePerformanceProfileVersion` (0007) es versionado por Athlete + effective_from: origin, algorithm_version, note, FC reposo/máxima, peso, FTP, umbral FC ciclismo, umbral FC carrera, ritmo umbral carrera, CSS y longitud de piscina. Genera zonas de FC, potencia, ritmo y natación.

`AthletePerformanceReference` (0008) guarda referencias granulares y versionadas por Athlete, sport, metric_type y effective_from: value/unit, origin, quality, measured_at, method, algorithm version y note.

DECISIÓN: FTP, FC máxima/reposo/umbrales, ritmos, CSS, longitud de piscina, zonas, origen/calidad/vigencia permanecen en rendimiento. No se duplican en AthleteProfile.

Hay una duplicidad histórica objetiva: `weight_kg` existe como snapshot básico y dentro de cada versión de rendimiento. 0.8D.2 debe declarar AthleteProfile como peso actual de perfil básico; una versión de rendimiento conserva el peso contextual usado por aquella versión. No deben sincronizarse silenciosamente.

## 5. Clasificación y fuente única de verdad

| Concepto | Categoría | Fuente de verdad | Onboarding |
|---|---|---|---|
| nombre | A identidad básica | AthleteProfile.display_name | creación; editable después |
| timezone | C preferencia | AthleteProfile.timezone | creación; editable |
| unidades | C preferencia | AthleteProfile.unit_system | creación; editable |
| año nacimiento | B contexto fisiológico | AthleteProfile.birth_year | básico opcional |
| sexo de contexto | B contexto fisiológico | AthleteProfile.sex_for_training_context | opcional |
| altura | B contexto fisiológico | AthleteProfile.height_m (m) | opcional |
| peso actual | B contexto fisiológico | AthleteProfile.weight_kg (kg) | opcional |
| experiencia | C preferencia/contexto | AthleteProfile.experience_level | aplazar hasta enum útil |
| disciplinas objetivo | G no necesaria | ninguna | fuera 0.8D |
| objetivo/race/plan | G posterior | futuro dominio planning | fuera |
| FTP/FC/umbrales/ritmo/CSS/piscina | D rendimiento | ProfileVersion/Reference | Perfil de rendimiento |
| zonas | F derivado | cálculo desde referencias/versiones | nunca input básico |
| actividades | E/F fuente deportiva | CompletedActivity | import/manual |
| Strava | E integración | IntegrationAccount + OAuthCredential | conexión separada |
| cargas/status | F derivado | tablas de load/aggregate/status | nunca input |

## 6. Perfil básico MVP y validación

DECISIÓN: el editor 0.8D.2 incluye exactamente `display_name`, `timezone`, `unit_system`, `birth_year`, `sex_for_training_context`, `height_m`, `weight_kg`. `experience_level` se devuelve read-only o se aplaza hasta fijar vocabulario: hoy no tiene constraint ni consumidor. MOTIVO: evitar persistir categorías libres sin semántica.

Creación sigue requiriendo solo nombre, timezone IANA y unidades. Athlete incompleto es válido y usable.

Validaciones propuestas: nombre normalizado 1..200; timezone IANA; unit metric/imperial; birth_year entre año actual-100 y año actual-13 (política a confirmar); sex enum pendiente de decisión de producto; height_m 0.50..2.50; weight_kg 20..400. DB conserva metros/kg; frontend convierte según unit_system. Null permitido en los cuatro datos fisiológicos.

## 7. Required, optional y completitud

- Requerido al crear: display_name, timezone, unit_system.
- Requerido para estado `basic`: esos tres únicamente; el Athlete ya es operativo.
- Recomendado para coaching contextual: birth_year y, cuando el usuario consienta, sex_for_training_context, height_m y weight_kg.
- `performance_ready`: existe al menos una referencia/version de rendimiento aplicable; se informa por separado, no bloquea.
- `integration_ready`: conexión activa de Strava; independiente y no bloquea.

DECISIÓN: no persistir `profile_complete`. Derivar un DTO `completeness` con `level: minimal|contextual`, `missing_fields` y `recommended_fields`; omitir porcentaje porque da falsa precisión. `minimal` exige los tres campos no nulos actuales; `contextual` exige además birth_year, height_m y weight_kg; sexo permanece recomendado/consentido y no debe bloquear. La lógica será una función de dominio pura y testeada.

## 8. API propuesta 0.8D.2

DECISIÓN: `GET /athlete/profile` y `PATCH /athlete/profile`, coherentes con los prefijos athlete-scoped existentes (`/athlete/performance-profile`). Ambos resuelven `CurrentAthleteContext` y nunca aceptan athlete_id en path/body.

Response:
```json
{"id":"uuid","display_name":"Jenny Ruiz","timezone":"Europe/Madrid","unit_system":"metric","birth_year":null,"sex_for_training_context":null,"height_m":null,"weight_kg":null,"experience_level":null,"completeness":{"level":"minimal","missing_fields":["birth_year","height_m","weight_kg"],"recommended_fields":["sex_for_training_context"]},"updated_at":"..."}
```

PATCH `extra=forbid`, campos editables MVP únicamente; respuesta idéntica. No admite id, user_id, role, memberships, default, Strava, capabilities, deleted_at ni datos de rendimiento.

Errores: 401 auth; 403 athlete_not_authorized/athlete_permission_denied y CSRF/Origin; 404 athlete_profile_not_found; 409 solo conflicto objetivo; 422 schema/timezone/rangos/enum; 500 seguro con rollback.

## 9. PATCH semantics

- Omitido: conservar valor.
- `null`: limpiar solo birth_year, sex_for_training_context, height_m y weight_kg.
- `display_name`, `timezone`, `unit_system`: null rechazado.
- Blank: nombre/timezone rechazados después de trim; enums blank rechazados, no convertidos a null.
- Valores numéricos: unidades canónicas; cero/negativos/fuera de rango rechazados.
- PATCH vacío: 422 o no-op explícito; se recomienda 422 `athlete_profile_update_empty`.
- Normalización solo para nombre; response es fuente final.

## 10. Capabilities y roles actuales

Capabilities reales: read/recalculate athlete data; create/update/delete manual strength; create performance profile/reference; read/manage Strava; run import/enrichment/evidence; delete location evidence.

| Operación | owner | editor | coach | viewer |
|---|---:|---:|---:|---:|
| leer perfil/actividades | sí | sí | sí | sí |
| recalcular | sí | sí | sí | no |
| crear/actualizar fuerza | sí | sí | sí | no |
| borrar fuerza | sí | sí | no | no |
| crear rendimiento/referencia | sí | sí | sí | no |
| leer Strava | sí | sí | sí | sí |
| conectar/desconectar Strava | sí | sí | no | no |
| importar/enriquecer/evidencia | sí | sí | sí | no |
| borrar evidencia ubicación | sí | sí | no | no |

DECISIÓN: 0.8D.2 añade capability específica `edit_athlete_profile`, inicialmente owner/editor; coach/viewer solo lectura. No reutilizar `create_performance_profile`. La matriz definitiva se endurece en D.6.

## 11. Propietario, User-atleta y coach

Hoy `owner` es por Athlete, no global. Un User puede gestionar sus propios datos con owner/editor, pero el modelo no expresa que sea el sujeto humano del Athlete. `editor` además tiene privilegios casi idénticos a owner, incluido Strava/destrucción, por lo que no es una semántica apropiada para self-service a largo plazo.

DECISIÓN role athlete: **AÑADIR**, pero solo en 0.8D.6 tras diseñar migración/capabilities. Alternativa A (sin athlete) es compatible y simple, pero confunde identidad propia con delegación. Alternativa B distingue `AthleteProfile` (sujeto) de `User role=athlete` (usuario self-service), permite consentimientos y permisos propios, a cambio de enum/migración/tests. `athlete` no implica ownership global ni vuelve al Athlete un User.

Propietario global: NO modelar ahora. Ownership por Athlete basta mientras no existan billing, workspace o administración transversal. Si aparece una operación global real, diseñar ese agregado entonces, no inferirlo de defaults.

Coach = User con memberships `coach` sobre uno o varios AthleteProfiles. Hoy puede leer, recalcular, crear/editar fuerza, rendimiento y ejecutar procesos Strava, pero no gestionar conexión, borrar fuerza ni ubicación. Es adecuado como base. El selector ya lista solo memberships activas autorizadas; por tanto un futuro Coach ve A/B/C asignados y nada ajeno.

## 12. Strava actual

Flujo real:
1. `POST /integrations/strava/connect/start` requiere `MANAGE_STRAVA_CONNECTION` sobre CurrentAthleteContext.
2. Crea state aleatorio de 256 bits y guarda `value,user_id,athlete_id,created_at,expires_at,consumed_at` en SQLite durable de desarrollo.
3. Callback requiere User autenticado, consume state atómicamente/exactamente una vez y valida user.
4. Usa athlete_id capturado, reconsulta membership activa + Athlete no borrado y revalida capability.
5. Intercambia code, valida scopes y persiste IntegrationAccount para ese athlete, credential y audit en transacción.
6. Import selecciona cuenta por athlete; jobs llevan athlete_id + integration_account_id; actividades llevan athlete_id + source account; agregados/status usan athlete_profile_id.

También existe DELETE `/integrations/strava/disconnect`, athlete-scoped, con revocación y limpieza local segura.

DECISIÓN: el binding actual es seguro frente a cambiar selector/pestaña durante OAuth. El callback no re-resuelve desde el atleta activo ni confía en athlete_id del navegador.

Deuda de despliegue: el state store SQLite debe sustituirse por PostgreSQL/Redis compartido multiinstancia; OAuthCredential declara tokens plaintext-dev y exige envelope encryption en producción.

## 13. Unicidad, reconexión y Strava objetivo

Constraints: UNIQUE `(athlete_id, provider, external_account_id)`, UNIQUE global `(provider, external_account_id)` añadida en 0002, y único account activo por `(athlete_id, provider)` condicionado por status/deleted_at.

Misma cuenta externa en otro Athlete: 409 `strava_external_account_already_linked`. Mismo external account en el mismo Athlete: reconexión y rotación de credential. External account distinto mientras existe cuenta local no revocada: conflicto; nunca transferencia silenciosa.

0.8D.4 no necesita rediseñar el binding; debe cerrar UX y pruebas A/B: mostrar atleta seleccionado antes de redirigir, confirmar retorno, mapear conflictos/reautorización, conservar selección independiente del callback y probar cambio de selector entre start/callback.

## 14. Aislamiento de importación y auditor

La cadena queda scoped: IntegrationAccount.athlete_id → SyncJob athlete/account → CompletedActivity athlete/source → ActivityTrainingLoad por actividad → agregados/status por athlete. Los mappers validan external owner y servicios filtran por athlete.

El auditor actual cubre cuentas activas duplicadas, credencial huérfana/faltante, mismatch activity-account, mismatch job-account, agregados missing/mismatch/duplicate y memberships/defaults. Huecos priorizados: coherencia de webhooks con account/job, referencias/profile/status con Athlete borrado, y prueba de dos IntegrationAccounts reales distintos. No hay evidencia de fallback a User/default en el pipeline productivo auditado.

Criterio D.4/D.5: cuentas externas diferentes, credenciales/accounts/jobs/activities/loads/status separados; acceso cruzado rechazado; uniqueness intacta; A no cambia al importar B.

## 15. UX 0.8D.3

DECISIÓN: combinación Inicio + Configuración. Dashboard muestra aviso no bloqueante `Completa tu perfil deportivo` solo si faltan recomendados, con `Ahora` y posibilidad de ignorarlo. Editor completo en `/settings/athlete-profile`, navegación `Configuración → Perfil deportivo`, entre Cuenta y Perfil de rendimiento.

Naming: Cuenta (User), Perfil deportivo (Athlete básico), Perfil de rendimiento (versiones/referencias), Conexiones / Strava (Athlete). Nunca membership/owner/AthleteProfile en UI.

Estados: loading, ready, saving, success, validation, authorization/network; conserva input; responsive a una columna; labels/fieldset, foco y live regions. Al cambiar A/B, key por athlete_id y cancelar respuestas stale; refrescar AthleteContext después de guardar nombre/timezone/unidades para selector/header y transporte. Athlete incompleto sigue navegando y usando dominios vacíos.

## 16. Datos sensibles y privacidad

Birth year, sex_for_training_context, height_m y weight_kg son personales. Siempre athlete-scoped, solo visibles con membership/capability, excluidos de logs y metadata de auditor salvo necesidad minimizada. Sexo es contexto deportivo, no identidad general ni campo User. Birth year permite edad aproximada y cambia su derivación cada año; no se necesita fecha completa.

Altura se persiste en metros y peso en kg, nunca duplicados imperial. UI convierte con redondeo reversible. El peso de AthleteProfile es snapshot actual; un histórico de peso puede ser útil para salud/rendimiento, pero no se crea en 0.8D. El versionado existente de rendimiento no debe reutilizarse como historial clínico.

Salud (diagnósticos, lesiones, sueño, HRV, menstruación, medicación, readiness) queda fuera.

## 17. Contratos de fases

### 0.8D.2 backend perfil deportivo
Migración solo si hacen falta checks/enums; GET/PATCH athlete-scoped; DTO/completeness; capability; tests auth/CSRF/tenant/PATCH/rangos/concurrencia.

### 0.8D.3 frontend
Ruta `/settings/athlete-profile`, aviso dashboard, editor mínimo, conversiones, accesibilidad, switching/stale/StrictMode, refresh del contexto.

### 0.8D.4 Strava por Athlete
Hardening y UX del flujo existente: atleta explícito, state-bound callback, reconexión/conflictos, tests de cambio de selector y auditor extendido. No conectar cuentas reales durante implementación.

### 0.8D.5 validación real
Si hay dos cuentas Strava distintas: baseline A, conectar B, importar rango controlado, comprobar accounts/credentials/jobs/activities/load/status y aislamiento bidireccional. Si solo hay una cuenta: no vulnerar uniqueness; usar proveedor fake/test y validar el 409 real al intentar reutilizarla, dejando B desconectada.

### 0.8D.6 roles/capabilities
Diseñar/añadir `athlete`, capability edit profile, matriz owner/athlete/editor/coach/viewer, migración explícita sin inferir automáticamente qué User es el atleta, tests self-service y coach. Sin invitaciones.

## 18. Deudas priorizadas

1. P0 producción: cifrado envelope de OAuthCredential.
2. P0 despliegue multiinstancia: state store compartido PostgreSQL/Redis.
3. P1: capability específica de edición básica.
4. P1: constraints/vocabulario para birth_year, sex y experience antes de exponerlos.
5. P1: resolver semántica doble de weight (actual vs snapshot versionado) en API/docs.
6. P1: ampliar auditor a webhooks y referencias/status huérfanos/borrados.
7. P2: role athlete y vínculo self-service explícito.
8. P2: histórico de peso solo cuando exista caso de uso de Salud.

## 19. Open questions

- Vocabulario inclusivo y finalidad exacta de `sex_for_training_context`; hasta resolverlo debe ser opcional y no afectar completitud.
- Valores válidos y uso de `experience_level`; se aplaza del MVP editable.
- Edad mínima de producto/legal para birth_year (el rango 13–100 es propuesta, no contrato cerrado).
- Disponibilidad de una segunda cuenta Strava distinta para D.5.

## 20. Criterios de aceptación y roadmap

0.8D.2 sale con profile GET/PATCH aislado, whitelist, capability y completitud derivada. 0.8D.3 sale con UX no bloqueante A/B y Cuenta intacta. 0.8D.4 sale con pruebas automatizadas de binding/reconexión/conflicto y auditor ampliado. 0.8D.5 sale solo con evidencia real segura o alternativa documentada sin duplicar external account. 0.8D.6 sale con semántica y matriz probadas para self/coach, sin ampliar a organizaciones.

DECISIÓN final: secuencia 0.8D.2 backend básico → 0.8D.3 frontend progresivo → 0.8D.4 cierre Strava multiatleta → 0.8D.5 validación real → 0.8D.6 roles/self/coach.
## Estado de implementación 0.8D

- 0.8D.1 — closed.
- 0.8D.2 — closed: `GET/PATCH /athlete/profile`, completitud derivada y `edit_athlete_profile` para owner/editor.
- 0.8D.3 — implemented: `/settings/athlete-profile`, editor athlete-scoped, unidades visuales, completitud y banner progresivo en Inicio.
- 0.8D.4 — planned.
- 0.8D.5 — planned.
- 0.8D.6 — planned.

Contrato efectivo 0.8D.2: birth year admite 1900..año natural actual; `sex_for_training_context` conserva compatibilidad estructural nullable, trim, no blank y máximo 32 porque no existe vocabulario canónico; altura y peso aceptan valores positivos compatibles con `Numeric(5,3)` y `Numeric(6,3)`. La lista recomendada estable contiene birth year, sex context, height y weight. El PATCH vacío devuelve `422 athlete_profile_update_empty`. Cambiar timezone no reagrega históricos y cambiar unidades no convierte valores canónicos. La edición no sincroniza el snapshot de peso de PerformanceProfileVersion.

UX efectiva 0.8D.3: Cuenta sigue editando al User; Perfil deportivo edita solo el Athlete activo; Perfil de rendimiento conserva referencias y umbrales. El formulario descarta cambios locales sin guardar al cambiar de Athlete, nunca hace autosave y refresca SessionContext tras cambiar nombre, timezone o unidades. El campo de sexo se mantiene como texto opcional explicado, sin inventar vocabulario. En imperial la altura usa pies+pulgadas y el peso libras; el PATCH persiste exclusivamente metros/kg. Inicio consulta el perfil del Athlete activo y muestra el aviso solo para estado `minimal`.
