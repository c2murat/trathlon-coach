# TriCoach AI Roadmap 1.0

This roadmap reflects implemented behavior as of July 2026. Each version must
remain deployable, documented, and backward-compatible where practical.

## Current status

| Horizon | Status |
|---|---|
| Completed | Versions 0.1 through 0.3.2: backend, persistence, provider layer, Strava OAuth lifecycle, and historical summary import |
| In progress | Version 0.4 implementation; frontend runtime validation remains pending on a local Node.js installation |
| Next | Complete Version 0.4 local frontend tests, build, and browser acceptance |
| Later | Activity enrichment, athlete analytics, profile/zones, planning/recovery, coaching, and post-1.0 integrations |

The production-shaped backend uses FastAPI, PostgreSQL, SQLAlchemy, and Alembic.
Strava OAuth and connection management work, and the historical summary importer
has successfully imported 1,381 real activities with pagination, checkpoints,
resume behavior, incremental overlap, and deduplication. There is no usable
frontend yet.

## Completed foundation

### Version 0.1 â€” FastAPI backend and health

- **Goal:** Establish a minimal runnable backend.
- **User value:** Provides a dependable service boundary and visible availability check.
- **Scope:** FastAPI application, environment settings, dependency configuration, Windows instructions, and `GET /health`.
- **Acceptance criteria:** The application starts locally and health returns the documented HTTP 200 payload.
- **Tests:** Application import, settings, and health endpoint contract.
- **Explicit exclusions:** Persistence, providers, frontend, and coaching behavior.
- **Dependencies:** Python 3.13 and FastAPI.
- **Risks:** Local setup drift; mitigated by exact commands and automated tests.

### Version 0.2 â€” PostgreSQL persistence foundation

- **Goal:** Make PostgreSQL the durable system of record.
- **User value:** Connection and activity data survive restarts safely.
- **Scope:** SQLAlchemy 2.x models, Alembic, UUID identifiers, UTC timestamps, athlete ownership, integration accounts, credentials, activities, sync jobs, webhook envelopes, and audits.
- **Acceptance criteria:** Migrations create the documented MVP schema and model constraints preserve ownership and provider identities.
- **Tests:** Model creation, UUIDs, uniqueness, credential redaction, and SQLite-compatible unit constraints.
- **Explicit exclusions:** Live provider calls, PostgreSQL production operations, and public persistence APIs.
- **Dependencies:** Version 0.1, PostgreSQL, SQLAlchemy, Alembic, and psycopg.
- **Risks:** Development credentials remain plaintext; production encryption is mandatory.

### Version 0.2.1 â€” Provider abstraction

- **Goal:** Isolate external-provider behavior behind stable contracts.
- **User value:** Strava can evolve and future providers can be added without rewriting product logic.
- **Scope:** Provider, OAuth, activity mapper, synchronization, webhook interfaces, shared errors, and Strava metadata.
- **Acceptance criteria:** Strava metadata satisfies the provider interface without network or business behavior.
- **Tests:** Interface inheritance, provider metadata, and exception hierarchy.
- **Explicit exclusions:** OAuth execution, API calls, synchronization, and persistence changes.
- **Dependencies:** Version 0.2.
- **Risks:** Premature abstraction; controlled by implementing only demonstrated provider needs.

### Version 0.2.2 â€” Strava connect endpoint

- **Goal:** Begin Strava authorization securely.
- **User value:** An athlete can navigate from TriCoach AI to Strava consent.
- **Scope:** Validated configuration, read-only scopes, one-time user-bound OAuth state, and canonical redirect response.
- **Acceptance criteria:** `GET /integrations/strava/connect` returns a valid Strava redirect without exposing secrets.
- **Tests:** Configuration validation, state generation, URL construction, redirect behavior, and safe failures.
- **Explicit exclusions:** Callback exchange, token persistence, activity import, and frontend.
- **Dependencies:** Version 0.2.1 and a registered Strava application.
- **Risks:** State loss or redirect mismatch; mitigated by durable development state and strict URI validation.

### Version 0.2.3 â€” OAuth callback and credential persistence

- **Goal:** Complete authorization and retain the connection safely.
- **User value:** The athlete can grant read access once and use later synchronization.
- **Scope:** State consumption, callback validation, code exchange, scope enforcement, account ownership, credential persistence, and audits.
- **Acceptance criteria:** A valid callback creates or rotates one owned Strava connection; replay and ownership conflicts are rejected.
- **Tests:** Callback outcomes, exact-once state, token exchange mapping, rollback, reconnection, ownership, and real-process development flow.
- **Explicit exclusions:** Production credential encryption, activity import, webhooks, and frontend.
- **Dependencies:** Version 0.2.2, PostgreSQL, and Strava token exchange.
- **Risks:** Token disclosure and state replay; mitigated by redaction, isolated schemas, TTL, binding, and atomic consumption.

### Version 0.2.4 â€” Strava status and disconnect

- **Goal:** Give the athlete control over the provider connection.
- **User value:** Connection health is visible and access can be revoked safely.
- **Scope:** Safe status projection, remote revocation, local credential deletion after confirmed success, repeatable disconnect, and audits.
- **Acceptance criteria:** Status exposes no secret, and disconnect never claims success before safe completion.
- **Tests:** Connected/disconnected states, ownership, revocation success/failure, credential retention on retryable failure, and redaction.
- **Explicit exclusions:** Activity deletion, synchronization UI, and provider webhooks.
- **Dependencies:** Version 0.2.3 and the Strava revocation endpoint.
- **Risks:** Ambiguous remote failure; mitigated by retaining the retry credential until revocation is confirmed.

### Version 0.3.1 â€” Activity import specification

- **Goal:** Define a safe, phased historical-import contract before implementation.
- **User value:** Historical training can be imported predictably without duplicates or lost progress.
- **Scope:** Summary/detail/lap/stream phases, state machine, checkpoints, pagination, retries, rate limits, mapping, reconciliation, and UX expectations.
- **Acceptance criteria:** The specification identifies bounded phases, ownership, deduplication, restart behavior, and acceptance conditions.
- **Tests:** Documentation review against product, data, coaching, and Strava contracts.
- **Explicit exclusions:** Runtime import code and provider requests.
- **Dependencies:** Existing product, domain, data-model, and Strava specifications.
- **Risks:** Provider behavior drift; mitigated by mockable contracts and incremental implementation.

### Version 0.3.2 â€” Strava historical summary import

- **Goal:** Import real Strava activity summaries durably.
- **User value:** The athlete's training history becomes available in TriCoach AI.
- **Scope:** Mockable activity client, token refresh/rotation, pagination, mapping, page commits, checkpoints, job status, incremental overlap, and idempotent upserts.
- **Acceptance criteria:** Imports run in the background, resume safely, isolate malformed activities, pause on provider limits, and never duplicate provider activities. A real import completed with 1,381 activities.
- **Tests:** First and multi-page import, active/terminal job lifecycle, incremental sync, mapping, refresh, rate limits, temporary/permanent failures, rollback, ownership, redaction, and API contracts.
- **Explicit exclusions:** Details, laps, streams, webhooks, analytics, and frontend.
- **Dependencies:** Versions 0.2â€“0.3.1, active Strava connection, and PostgreSQL.
- **Risks:** Rate limits, late uploads, and process-local task execution; mitigated by durable progress, overlap, deduplication, and safe resume.

## Next visible product versions

### Version 0.4 â€” First usable web interface

- **Goal:** Deliver the first athlete-facing page.
- **User value:** The athlete can see whether the system works, inspect recent training, and operate Strava synchronization without API tools.
- **Scope:** React application shell; backend/Strava status; activity total; recent 10 activities; last sync; import status; connect and synchronize actions; loading, empty, offline, and error states.
- **Acceptance criteria:** A local athlete can open one responsive page, understand freshness and connection state, connect when needed, start a sync, observe progress, and see recent summary activities.
- **Tests:** Frontend unit/component states, accessibility smoke checks, API contract tests, activity-read ownership tests, and one browser journey covering disconnected and connected states.
- **Explicit exclusions:** Advanced analytics, activity details, laps, streams, planning, recovery, and AI.
- **Dependencies:** Version 0.3.2; activity-list/count and latest-import read endpoints; frontend tooling; local CORS/proxy configuration.
- **Risks:** Frontend scope expansion and contract mismatch; controlled by [UI_FIRST_RELEASE.md](UI_FIRST_RELEASE.md) and a single-page release.

### Version 0.5 â€” Activity detail pages

- **Goal:** Make imported summaries browsable and useful individually.
- **User value:** The athlete can find sessions and understand their core sport-specific results.
- **Scope:** Paginated/filterable activity list, summary cards, detail route, and basic swim/bike/run/strength fields already available from summaries.
- **Acceptance criteria:** Athlete-scoped filters and details work across supported sports with correct units, timezones, empty fields, and navigation.
- **Tests:** Query/filter contracts, ownership, unit formatting, card/detail component states, accessibility, and browser navigation.
- **Explicit exclusions:** Provider detail calls, laps, streams, advanced charts, and editing imported facts.
- **Dependencies:** Version 0.4 and stable activity read models.
- **Risks:** Inconsistent provider fields; mitigated by canonical labels and explicit missing-data presentation.

### Version 0.6 — Evidence and deterministic coaching foundations

Version 0.6 is divided into four independently accepted increments. Enrichment supplies evidence; visualization presents it; analytics derives reproducible metrics; the Coach Engine interprets only approved evidence. None of these increments introduces LLM-generated coaching.

#### Version 0.6A — Activity detail enrichment (implemented)

- **Goal:** Enrich selected stored summaries with provider detail and provenance.
- **User value:** The athlete can access additional source facts needed by later analysis.
- **Scope:** On-demand Strava activity detail, device/equipment context, available splits metadata, idempotent/resumable jobs, rate awareness, retention, deletion, and freshness.
- **Acceptance criteria:** Enrichment is athlete-scoped, selective, source-attributed, retry-safe, observable, and bounded by an approved retention policy.
- **Tests:** Provider fixtures, detail mapping, retries, deduplication, authorization, deletion, retention, and PostgreSQL integration.
- **Explicit exclusions:** Bulk stream import, charts, derived coaching metrics, recommendations, AI, Garmin, and workout export.
- **Dependencies:** Version 0.5B.2 plus schema, privacy, retention, and provider-rate decisions.
- **Delivered:** Selective detail endpoint client, migration `0004_strava_activity_detail`, provider-neutral mapper, bounded resumable jobs, owned progress API, and single-activity frontend refresh. No raw payload storage.

#### Version 0.6B — Laps, streams, and evidence visualization (implemented)

- **Goal:** Import only approved high-value laps/streams and present factual activity evidence.
- **User value:** The athlete can inspect how an activity unfolded without receiving automated coaching claims.
- **Scope:** Selective lap/stream retrieval, minimization, location-sensitive retention, factual split/series visualization, empty/partial states, and accessible rendering.
- **Acceptance criteria:** Evidence provenance and coverage are visible; imports are selective; visualizations reconcile with stored samples and remain usable without them.
- **Tests:** Lap/stream contracts, selection and retention policy, unit/time alignment, privacy deletion, visualization accessibility, and partial-data states.
- **Explicit exclusions:** Importing every stream, maps unless separately approved, training prescriptions, Coach Engine decisions, and AI.
- **Dependencies:** 0.6A and explicit stream/location privacy decisions.
- **Delivered:** Provider-neutral lap/stream/route tables, JSONB/JSON stream values, configurable location retention, shared-index downsampling, resumable evidence jobs, bounded reads, responsive lap table, and accessible SVG charts.

#### Version 0.6C — Deterministic sport metrics

- **Goal:** Produce provider-neutral, versioned activity and period metrics.
- **User value:** The athlete gets explainable sport-specific summaries with visible coverage and uncertainty.
- **Scope:** The supported subset of Levels 0–4 in [ANALYTICS_ARCHITECTURE.md](ANALYTICS_ARCHITECTURE.md), beginning with duration, distance, frequency, elevation, sport distribution, comparable pace/speed, and transparent trends.
- **Acceptance criteria:** Results state formula/version, units, window/timezone, input provenance, coverage, missing-data policy, and user explanation; recomputation is deterministic and idempotent.
- **Tests:** Golden calculations, properties, boundaries, missing/partial data, reconciliation, version compatibility, and recomputation.
- **Explicit exclusions:** Opaque readiness, injury prediction, medical inference, recommendations, cross-athlete ranking, and AI.
- **Dependencies:** Stable normalized facts; metrics needing laps/streams additionally depend on 0.6B.

#### Version 0.6D — Coach Engine foundation and rule-based observations

- **Goal:** Establish traceable evidence contracts and a small reviewed set of deterministic observations.
- **User value:** The athlete can understand selected changes in their own training and why the system noticed them.
- **Scope:** `AnalysisContext`, evidence references, athlete-state snapshots, versioned observation/safety rules, confidence bands, uncertainty reasons, audit records, and template explanations as specified in [COACH_ENGINE.md](COACH_ENGINE.md).
- **Acceptance criteria:** Every observation is reproducible, evidence-linked, athlete-scoped, safely suppressible, and explainable; raw facts, metrics, observations, recommendations, and athlete decisions remain separate.
- **Tests:** Rule fixtures, provenance, version replay, missing-data suppression, safety precedence, access control, audit, and explanation accessibility.
- **Explicit exclusions:** Autonomous plans, medical diagnosis, opaque scores, unreviewed recommendations, LLM calls, and AI-authored decisions.
- **Dependencies:** An approved subset of 0.6C metrics plus safety and governance decisions.

An LLM may be considered only in a later explicitly approved sprint, after deterministic evidence, decision, safety, privacy, evaluation, audit, and fallback contracts are operating. Its role would be constrained explanation, never calculation or authority.

### Version 0.7 â€” Athlete dashboard

- **Goal:** Turn stored training into clear deterministic summaries.
- **User value:** The athlete can understand recent consistency and training composition at a glance.
- **Scope:** Weekly duration, distance by sport, elevation, frequency, consistency, freshness, and simple deterministic trends.
- **Acceptance criteria:** Dashboard totals reconcile with stored activities, explain date/unit boundaries, and handle missing or partial weeks.
- **Tests:** Calculation fixtures, timezone/week boundaries, aggregation ownership, API contracts, chart states, and browser smoke tests.
- **Explicit exclusions:** AI interpretation, opaque readiness scores, planning, and prescriptive coaching.
- **Dependencies:** Versions 0.4â€“0.6 and canonical activity data.
- **Risks:** Misleading totals from incomplete data; mitigated by freshness, coverage, and missing-data indicators.

### Version 0.8 â€” Athlete profile and zones

- **Goal:** Capture the athlete context needed for personal training guidance.
- **User value:** Training intensity and practical availability reflect the athlete rather than generic defaults.
- **Scope:** Profile, preferred days, availability, effective-dated heart-rate zones, cycling power/FTP, running pace, swimming CSS, and equipment.
- **Acceptance criteria:** The athlete can manage owned profile data and valid versioned zones with metric internal storage and clear effective dates.
- **Tests:** Validation, ordering, effective dates, unit conversion, ownership, equipment lifecycle, and UI journeys.
- **Explicit exclusions:** Automatic threshold diagnosis, autonomous zone changes, planning, and AI.
- **Dependencies:** Version 0.7 and profile/zone/equipment persistence APIs.
- **Risks:** Stale or incorrectly entered thresholds; mitigated by provenance, dates, validation, and athlete confirmation.

### Version 0.9 â€” Planning and recovery

- **Goal:** Connect intended training, completed work, and athlete-reported recovery.
- **User value:** The athlete can plan realistically and see why execution or readiness differs.
- **Scope:** Planned workouts, calendar, explicit planned/completed matching, RPE, sleep, fatigue, soreness, pain, illness warnings, and safe deterministic comparisons.
- **Acceptance criteria:** Plans evolve without mutating imported facts; matching is reversible; recovery inputs remain distinct; safety warnings follow the coaching model.
- **Tests:** Sport-specific workout validation, calendar/timezone behavior, matching/reversal, comparisons, sensitive-data access, safety rules, and UI journeys.
- **Explicit exclusions:** Medical diagnosis, autonomous plan changes, device export, and opaque AI advice.
- **Dependencies:** Version 0.8 and planning/recovery data models and access controls.
- **Risks:** Health-data sensitivity and overreaction to one signal; mitigated by strict access, uncertainty, trends, and conservative rules.

### Version 1.0 â€” Stable personal coaching platform

- **Goal:** Integrate and harden the complete personal coaching MVP.
- **User value:** One amateur triathlete can synchronize, understand, plan, recover, and receive explainable guidance in one reliable product.
- **Scope:** Usable dashboard, reliable Strava synchronization, planning, recovery inputs, deterministic training load, explainable evidence-based recommendations, privacy/export/deletion, and stable deployment documentation.
- **Acceptance criteria:** Core journeys work end to end; calculations are reproducible; recommendations cite stored evidence; provider failures recover clearly; export/deletion and release reviews pass.
- **Tests:** Full MVP browser journeys, regression, PostgreSQL migrations, backup/restore, provider recovery, deterministic calculations, recommendation evidence/safety, privacy deletion/export, performance, security, and accessibility.
- **Explicit exclusions:** Medical functionality, autonomous unexplained coaching, Garmin, calendar/weather integrations, mobile apps, and multi-athlete coaching.
- **Dependencies:** Versions 0.1â€“0.9, production credential protection, durable workers, observability, and deployment operations.
- **Risks:** Cross-feature complexity, privacy obligations, and coaching trust; mitigated by staged releases, evidence, approvals, operational rehearsal, and safety review.

## Post-1.0

- **Goal:** Extend reach without weakening the stable personal platform.
- **User value:** More devices, contexts, export paths, and eventual coaching relationships.
- **Scope:** Garmin, Google Calendar, weather, workout export, mobile interface, and multi-athlete/coach functionality in separate releases.
- **Acceptance criteria:** Each integration has explicit consent, provenance, status, disconnect, idempotency, and failure recovery; coach access is athlete-controlled.
- **Tests:** Provider contracts/sandboxes, calendar conflicts, weather freshness, export schemas, mobile accessibility, tenant isolation, and consent revocation.
- **Explicit exclusions:** Unsupported scraping, silent calendar overwrites, guaranteed forecasts, and cross-athlete access without consent.
- **Dependencies:** Stable 1.0 contracts plus provider approval and feature-specific privacy reviews.
- **Risks:** Provider drift, broader sensitive-data exposure, and operational load; mitigated by isolated adapters, least privilege, auditability, and staged rollout.

## Release strategy

- `main` remains stable and contains only reviewed, working sprint outcomes.
- Use one short-lived branch per sprint.
- Commit after each stable sprint, including documentation and tests.
- Create semantic version tags when roadmap milestones are accepted.
- A milestone is complete only when its acceptance criteria, tests, exclusions,
  documentation, and migration/rollback considerations have been reviewed.

### Version 0.5A — Athlete dashboard (implemented)

- **Goal:** Turn stored activity summaries into a useful athlete overview.
- **Scope:** Weekly/monthly/rolling/year aggregates, normalized sport composition, eight-week deterministic trend, consistency and weekly streaks, responsive Spanish dashboard, and independent analytics failure handling.
- **API:** `/dashboard/summary`, `/dashboard/trends`, and `/dashboard/consistency` are athlete-owned and exclude deleted, provider-deleted, and future activities.
- **Boundary rule:** Calendar and ISO-week boundaries are evaluated in the athlete timezone; ISO weeks begin Monday, and trend results are oldest to newest.
- **Interpretation:** Metrics are deterministic historical summaries, not coaching advice.
- **Explicit exclusions:** Activity details, laps, streams, maps, AI, planning, Garmin, authentication, CTL, ATL, TSB, TSS, readiness, fatigue, and fitness scores.
- **Next sprint:** Version 0.5B — activity browsing foundations (pagination and summary filters only); it must be planned separately and is not part of Version 0.5A.

### Version 0.5A.1 — UX and dashboard polish (implemented)

- **Scope:** Responsive shell/navigation, six routes, coming-soon pages, time-aware greeting, development user menu, persistent system-aware light/dark themes, frontend-derived weekly averages, chart/activity polish, and accessibility refinements.
- **Explicit exclusions:** New analytics, migrations, activity details, laps, streams, maps, AI, coaching, planning, Garmin, and authentication.
- **Next sprint:** Version 0.5B — activity browsing foundations. It has not begun.

### Version 0.5B — Activity browsing foundations (implemented)

- **Goal:** Browse, filter, paginate, and inspect athlete-owned imported activity summaries.
- **Backend:** Filtered `/activities`, safe `/activities/filter-options`, and owned `/activities/{activity_id}` detail with deletion/future/ownership enforcement.
- **Frontend:** Operational `/activities` and `/activities/:activityId`, explicit URL-synchronized filters, responsive cards, pagination, safe retry/empty states, and summary-only detail.
- **Migration:** None; existing canonical summary fields and indexes are sufficient for the personal dataset.
- **Explicit exclusions:** Laps, streams, maps, provider detail fetches, editing, deletion, renaming, social features, AI, coaching, planning, Garmin, and authentication.
- **Next sprint:** Version 0.6 — Activity enrichment. It has not begun.

### Version 0.5B.1 — Activity summary display polish (implemented)

- **Scope:** Frontend-only sport-aware pace/speed conversion, literal power units, conservative cadence formatting, visibility and boolean localization, semantic metric sections, and responsive detail-page polish.
- **Data source:** Stored Strava summaries only; no provider or enrichment requests.
- **Running cadence:** `ppm` explicitly means pasos por minuto. Swimming stroke cadence is not inferred from the generic stored cadence field.
- **Migration:** None.
- **Explicit exclusions:** Enrichment, laps, streams, maps, editing, AI, coaching, planning, Garmin, and backend behavior changes.
- **Next sprint:** Version 0.6 — Activity enrichment. It has not begun.

### Version 0.6B — Laps, streams, route evidence, and factual visualization (implemented)

- **Scope:** Selective normalized laps and supported streams, deterministic bounded shared-index downsampling, optional route evidence, privacy-first retention, athlete-owned job/read APIs, and accessible factual visualization.
- **Storage:** Relational laps; JSONB-backed normalized stream series on PostgreSQL with portable JSON in SQLite; provenance, checksums, sample counts, and freshness state.
- **Privacy:** Location retention is off by default, location is not requested or returned while disabled, and retained location has an athlete-owned cleanup path.
- **Explicit exclusions:** Metrics, observations, recommendations, coaching, AI, planning, Garmin, editing, social features, segments, and live tracking.
- **Next sprint:** Version 0.6C — deterministic factual metrics and coverage rules. It has not begun.


## Version 0.6C — métricas factuales

La primera implementación de 0.6C calcula métricas deterministas sobre actividades ya importadas. Cada resultado conserva estado (`available`, `partial`, `unavailable`, `not_applicable`), unidad, fuente, muestras, cobertura, notas y motivo seguro de indisponibilidad. El algoritmo estable es `0.6c.1`.

La persistencia usa `activity_metrics`, relacionada con `completed_activities`, con unicidad por actividad, métrica y versión. Los endpoints son `GET /activities/{activity_id}/metrics` y `POST /activities/{activity_id}/metrics/recalculate`; el recálculo es aislado e idempotente.

Incluye tiempo, distancia, desnivel, velocidades, frecuencia cardiaca, potencia, cadencia, vueltas y muestras de streams. Las fuentes son resumen almacenado y streams disponibles; no se interpolan streams ausentes o desalineados. Los valores no numéricos, NaN e infinitos se descartan y nunca se convierten silenciosamente en cero.

Quedan fuera TSS, TRIMP, NP, IF, VI, GAP, SWOLF, zonas, umbrales, carga, recuperación, fatiga, readiness, coaching, recomendaciones, planificación e IA. No hay recálculo masivo automático ni worker independiente.
