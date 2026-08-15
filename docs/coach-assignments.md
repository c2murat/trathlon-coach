# Asignaciones de entrenadores

0.8E.6 reutiliza `UserAthleteMembership`; no introduce tabla ni migración nuevas.

- Autoridad administrativa: `User.account_plan=owner`.
- Target Coach: User activo, no eliminado y `account_plan=coach`.
- Target deportivo: AthleteProfile existente y no eliminado.
- Persistencia: `role=coach`, `is_active=true`; default sólo para la primera membership activa.
- Duplicado activo: idempotente.
- Fila Coach histórica inactiva: se reactiva.
- Relación existente con otro rol: conflicto, nunca conversión silenciosa.
- Revocación: histórica, `is_active=false`, `is_default=false`.

Los endpoints owner-only son `GET /coach-assignments/candidates`, `GET /coach-assignments`, `POST /coach-assignments` y `DELETE /coach-assignments/{membership_id}`. Los datos deportivos continúan protegidos por Current User + Current Athlete + membership activa + capability.