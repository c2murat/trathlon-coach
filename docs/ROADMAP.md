# Triathlon Coach Roadmap

Each version should remain deployable, documented, and backward-compatible where practical. Acceptance requires the stated tests; passing tests alone does not expand scope.

## Version 0.1 - Backend foundation

**Scope:** Minimal FastAPI package, environment-based settings, dependency configuration, `GET /health`, and one endpoint test.

**Acceptance criteria:** The documented Windows setup starts the service; `/health` returns HTTP 200 with the documented payload.

**Tests:** Application import, settings defaults, and automated health endpoint response.

**Excluded:** Database, authentication, integrations, frontend, coaching, and training features.

## Version 0.2 - Strava OAuth connection

**Scope:** Strava authorization start/callback, state validation, minimum scopes, encrypted token handling, connection status, refresh, and disconnect.

**Acceptance criteria:** An athlete can connect a test Strava account, inspect status/scopes, refresh an expired token, and revoke the local connection safely.

**Tests:** OAuth state and callback contracts, token refresh, provider error mapping, encryption boundary, and disconnect behavior using mocked Strava responses.

**Excluded:** Activity import, webhooks, PostgreSQL activity storage, dashboard, and other providers.

## Version 0.3 - Historical activity import

**Scope:** Athlete-triggered paginated Strava history import, provider mapping, deduplication keys, progress, retry, and import summaries. Temporary persistence may be used until 0.4.

**Acceptance criteria:** A bounded date range imports supported historical activities once, reports successes/failures, and can resume without duplicates.

**Tests:** Pagination, mapping fixtures, date boundaries, rate-limit/retry behavior, duplicate events, partial failure, and resume.

**Excluded:** Durable activity database model, real-time webhooks, analytics, and frontend views.

## Version 0.4 - PostgreSQL activity storage

**Scope:** PostgreSQL configuration and migrations for canonical activities, integration accounts, external record identities, and synchronization runs; repository adapters and basic activity reads.

**Acceptance criteria:** Imported activities survive restarts, external IDs are unique per account/provider, migrations work on an empty database, and activity reads are athlete-scoped.

**Tests:** Migration up path, repository integration tests, uniqueness/idempotency, transaction rollback, and athlete isolation.

**Excluded:** Webhook ingestion, detailed stream storage, training load, calendar, and dashboard UI.

## Version 0.5 - New Strava activity webhook

**Scope:** Webhook verification, event inbox, signature/subscription checks supported by Strava, idempotent asynchronous fetch/update/delete handling, retries, and audit status.

**Acceptance criteria:** New or changed activities appear once after valid events; duplicate/out-of-order events are safe; invalid events are rejected; failures are visible and retryable.

**Tests:** Verification challenge, valid/invalid events, duplicates, ordering, create/update/delete, retry, and mocked provider failures.

**Excluded:** Garmin, push notifications, training analysis, and frontend synchronization controls.

## Version 0.6 - Athlete profile, zones, and equipment

**Scope:** Athlete profile, units, availability, goals/limitations, heart-rate/pace/power zone records, threshold history, and equipment inventory with activity assignment.

**Acceptance criteria:** The athlete can create and update profile data, maintain effective-dated zones, manage gear, and associate supported equipment with an activity.

**Tests:** API validation, zone ordering/effective dates, unit handling, ownership, equipment lifecycle, and activity association.

**Excluded:** Automatic zone estimation, maintenance prediction, coaching recommendations, and frontend dashboard.

## Version 0.7 - Basic React dashboard

**Scope:** React application shell and a responsive dashboard showing connection status, recent activities, weekly totals, profile summary, equipment, upcoming races when available, loading/empty/error states, and freshness.

**Acceptance criteria:** The athlete can load the dashboard and understand recent training and synchronization health on desktop and mobile-sized screens.

**Tests:** Component states, API contract integration, accessibility smoke checks, responsive end-to-end journey, and backend dashboard query tests.

**Excluded:** Workout planning, advanced charts, AI insights, calendar editing, and native mobile apps.

## Version 0.8 - Planned workouts and calendar

**Scope:** Races/goals, training blocks, sport-specific swim/bike/run/strength workouts, templates, calendar placement/rescheduling, completion matching, and planned-versus-completed comparison.

**Acceptance criteria:** The athlete can create a race, schedule and adjust structured workouts, link a completed activity, and see meaningful planned/actual differences without changing raw activity data.

**Tests:** Workout validation by sport, calendar/timezone behavior, conflicts, rescheduling, matching, comparison, authorization, and core UI journeys.

**Excluded:** Automatic plan generation, AI changes, device workout export, Google Calendar, and advanced periodization.

## Version 0.9 - Training load and recovery

**Scope:** RPE/session RPE, sleep, fatigue, soreness, stress, pain and illness check-ins; versioned weekly volume, intensity distribution, progression, readiness context, and post-workout/weekly summaries.

**Acceptance criteria:** Analysis uses stored evidence, displays freshness and missing inputs, recomputes deterministically, avoids diagnosis, and raises safety guidance for concerning athlete-reported inputs.

**Tests:** Calculation fixtures and boundaries, missing/stale data, recalculation idempotency, safety rules, explanation payloads, and dashboard presentation.

**Excluded:** Medical advice, opaque readiness scores, autonomous plan changes, AI interpretation, and claims of validated TSS/CTL/ATL/TSB equivalence across sports.

## Version 1.0 - Stable personal coaching platform

**Scope:** Harden and integrate versions 0.1-0.9 with reliable onboarding, planning, synchronization, analysis, privacy controls, export/deletion, observability, accessibility, and operational documentation.

**Acceptance criteria:** One amateur athlete can complete all MVP journeys reliably; recovery from provider failures is clear; data export/deletion works; security/privacy review and release checklist are complete.

**Tests:** Full end-to-end MVP journeys, regression suite, migration rehearsal, backup/restore, deletion verification, provider failure recovery, basic performance/load, security, and accessibility checks.

**Excluded:** AI coaching, Garmin, Google Calendar, weather, workout export, multi-athlete coaching, and medical functionality.

## Later versions

**Scope:** Incremental releases for explainable AI coaching, Garmin integration, Google Calendar synchronization, contextual weather, and standards/provider-specific workout export. Each capability receives its own version and consent model.

**Acceptance criteria:** AI cites stored evidence and requires approval for material changes; every integration exposes permissions/status/disconnect; calendar sync resolves conflicts; weather shows provenance/freshness; exports validate provider-compatible structure.

**Tests:** AI structured-output, evidence/provenance, safety and approval tests; provider contract/sandbox tests; calendar conflict/idempotency tests; weather fallback tests; export schema and device/provider fixture tests.

**Excluded:** Unexplainable or autonomous coaching, medical diagnosis, unsupported scraping or unofficial provider access, silent calendar overwrites, guaranteed forecasts, and unsupported device compatibility claims.
