# Changelog

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
