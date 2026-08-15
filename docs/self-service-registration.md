# Registro self-service

## Plan de cuenta y rol deportivo

`User.account_plan` representa el producto de la cuenta. Los planes públicos son `athlete` y `coach`; `owner` es exclusivamente interno y nunca se acepta en `/auth/register`.

`account_plan` no es `UserAthleteMembership.role`. El segundo expresa la relación del User con un AthleteProfile concreto y sigue siendo athlete-scoped.

## Efectos del registro

- Athlete: crea de forma atómica User, AthleteProfile propio y membership `athlete` activa/default; inicia sesión y continúa en Perfil deportivo.
- Coach: crea User y sesión, sin AthleteProfile ni memberships. Inicio muestra un estado vacío hasta que un flujo autorizado futuro le asigne atletas.

El registro normaliza email, aplica la política Argon2 existente, valida timezone IANA, limita intentos y usa las cookies de sesión/CSRF existentes. No acepta IDs, roles ni flags administrativos.

Los precios son configuración de producto pendiente. Esta fase no implementa pagos, verificación de email, recuperación de contraseña ni asignación Coach–Athlete. El registro público debe permanecer deshabilitado en producción hasta completar ese hardening.