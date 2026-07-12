# Triathlon Coach Architecture

## Architecture style

The platform starts as a modular monolith: one React application, one FastAPI application, and one PostgreSQL database. Domain boundaries are explicit so ingestion, analytics, or AI workloads can later move to workers or separate services without redesigning the product.

Rules:

- Domain modules own business rules; API routes only translate HTTP.
- External provider payloads are normalized before entering the domain.
- Imports, recalculations, and AI generation run as retryable background jobs.
- Recommendations retain inputs, algorithm/model version, and explanation.
- Athlete identity is present on owned records, despite the personal-first scope.

## System context

```text
React browser -- HTTPS/JSON --> FastAPI application --> PostgreSQL
                                      |                    ^
                                      +--> job worker -----+
                                      +--> Strava
                                      +--> Garmin adapter
                                      +--> AI provider
```

FastAPI is the orchestration boundary and PostgreSQL is the system of record. Workers handle provider synchronization, analytics recalculation, equipment aggregation, and AI tasks outside request latency.

## Repository structure

```text
trathlon-coach/
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   |   |-- dependencies/        # Shared FastAPI dependencies
|   |   |   |-- middleware/          # Errors, logging, context, CORS
|   |   |   `-- v1/routes/           # Versioned HTTP endpoints
|   |   |-- application/
|   |   |   |-- commands/            # State-changing use cases
|   |   |   |-- queries/             # Read-oriented use cases
|   |   |   `-- jobs/                # Background task orchestration
|   |   |-- core/                    # Settings, security, logging, shared errors
|   |   |-- db/
|   |   |   |-- migrations/          # PostgreSQL schema evolution
|   |   |   |-- models/              # ORM persistence mappings
|   |   |   |-- repositories/        # PostgreSQL repository adapters
|   |   |   `-- session/             # Engine, transactions, unit of work
|   |   |-- domains/
|   |   |   |-- athlete/
|   |   |   |-- workouts/
|   |   |   |-- calendar/
|   |   |   |-- races/
|   |   |   |-- activities/
|   |   |   |-- training_load/
|   |   |   |-- recovery/
|   |   |   |-- equipment/
|   |   |   `-- coaching/
|   |   |-- integrations/
|   |   |   |-- strava/
|   |   |   |-- garmin/
|   |   |   `-- ai_provider/
|   |   |-- schemas/                 # Public request/response contracts
|   |   `-- workers/                 # Queue runtime and schedules
|   `-- tests/
|       |-- unit/                    # Domain rules without I/O
|       |-- integration/             # Database/provider adapters
|       |-- api/                     # HTTP contract tests
|       `-- fixtures/                # Builders and provider samples
|-- frontend/
|   |-- src/
|   |   |-- app/                     # Bootstrap, routes, providers, shell
|   |   |-- features/
|   |   |   |-- athlete-profile/
|   |   |   |-- dashboard/
|   |   |   |-- training-calendar/
|   |   |   |-- race-calendar/
|   |   |   |-- workout-planner/
|   |   |   |-- activity-history/
|   |   |   |-- training-load/
|   |   |   |-- recovery/
|   |   |   |-- equipment/
|   |   |   |-- ai-coach/
|   |   |   `-- integrations/
|   |   |-- components/              # Cross-feature UI
|   |   |-- services/                # API transport
|   |   |-- hooks/                   # Cross-feature hooks
|   |   |-- state/                   # Truly global client state
|   |   |-- types/                   # Shared frontend contracts
|   |   |-- utils/                   # Framework-independent helpers
|   |   `-- assets/                  # Static assets
|   `-- tests/unit/ and tests/e2e/
|-- infra/
|   |-- compose/                     # Future local service topology
|   |-- database/                    # PostgreSQL operational assets
|   |-- deployment/                  # Future environments
|   `-- observability/               # Logs, metrics, traces, dashboards
`-- docs/
    |-- adr/                         # Architecture decisions
    |-- api/                         # Endpoint/event contracts
    |-- data-model/                  # ER model and dictionary
    `-- integrations/                # Provider behavior
```

Each backend domain will contain entities/value objects, domain services, ports (interfaces required from storage/providers), and domain errors. Implementations stay in `db` or `integrations`.

Each frontend feature owns its pages, feature-only components, hooks, queries, validation, state, and tests. Only genuinely reusable pieces move to the shared top-level folders.

## Backend module responsibilities

### API

Authentication dependencies, validation, versioning, pagination, status codes, serialization, middleware, and route assembly. Routes call application use cases and never query PostgreSQL or providers directly.

### Application

Coordinates use cases and transactions. Commands mutate state, queries build read models, and jobs coordinate asynchronous workflows. Cross-domain behavior is orchestrated here or through domain events.

### Core

Configuration, secrets access, authentication/authorization primitives, time and ID abstractions, logging, telemetry, and base errors. It cannot depend on a product domain.

### Database

PostgreSQL sessions, transactions, migrations, indexes, ORM mappings, and repository implementations. ORM types do not leak into domain rules.

### Workers

Idempotent/retryable provider sync, webhook processing, metric recomputation, reminders, equipment usage updates, and AI generation.

## Domain responsibilities

### Athlete

Profile, physiological attributes, goals, sport preferences, availability, units, privacy choices, training zones, injuries/limitations, and benchmarks.

### Workouts

Plans, blocks, templates, planned sessions, intervals, targets, progression, and completion state. Sport prescriptions are explicit:

- Swimming: pool/open water, stroke, sets, distance, rest, pace, CSS zones.
- Cycling: duration/distance, terrain, power, cadence, heart rate, FTP zones.
- Running: duration/distance, surface, pace, heart rate, elevation, threshold zones.
- Strength: exercises, sets, reps, load, rest, movement pattern, RPE/RIR.

### Calendar

Workout placement, availability, rest days, reminders, recurrence, timezone intent, conflicts, rescheduling, and completion markers. It links to workout and race records but does not own their details.

### Races

Race dates, A/B/C priority, disciplines/distances, target, course notes, registration, logistics, taper link, and results.

### Activities

Canonical completed training records from manual input, Strava, or Garmin-compatible imports; laps/stream references, perceived effort, workout matching, and provider deduplication.

### Training load

Sport-specific and combined load, acute/chronic trends, monotony, strain, intensity distribution, progression, and threshold history. Metrics record source window, freshness, and algorithm version.

### Recovery

Sleep, resting heart rate, HRV, soreness, fatigue, stress, mood, illness/injury flags, wellness check-ins, and explainable readiness. It provides conservative guidance, not medical diagnosis.

### Equipment

Bikes, shoes, wetsuits, components and other gear; activity assignment, distance/time totals, maintenance, service intervals, retirement, and alerts.

### Coaching

Insights, conversations, plan-adjustment proposals, athlete feedback, and accepted/rejected decisions. Deterministic constraints surround AI output. Material workout/calendar changes require athlete acceptance.

## Integration responsibilities

### Strava

OAuth, encrypted token lifecycle, scopes, webhook verification, incremental imports, rate limits, retries, sync cursors, status, and mapping into canonical activities.

### Garmin compatibility

A provider adapter supports authorized sources such as an approved API connection or athlete-provided FIT/TCX/GPX files. It maps activities, laps, samples, wellness, and device data when available. Garmin-specific fields remain integration metadata unless the domain needs them.

### AI provider

Vendor abstraction, prompt/version management, minimal context assembly, structured-output validation, cost tracking, timeouts/retries, and redaction. Credentials and unnecessary personal data are never included in prompts.

## Frontend feature responsibilities

- Dashboard: readiness, current load, next workout, next race, recent activity, equipment alerts, and coaching insights via a backend-composed read model.
- Athlete profile: identity, goals, zones, availability, preferences, limitations, and units.
- Training calendar: week/month schedules, completion, conflicts, and rescheduling.
- Race calendar: priorities, countdowns, goals, logistics, and results.
- Workout planner: templates and sport-specific swim, bike, run, and strength prescriptions.
- Activity history: sessions, provider sync, planned/actual matching, and detail views.
- Training load: trends, intensity distribution, progression, and metric explanations.
- Recovery: wellness entry, readiness, sleep/HRV trends, and recommendations.
- Equipment: inventory, assignments, usage, maintenance, and alerts.
- AI coach: explainable insights, contextual questions, proposals, and accept/reject flows.
- Integrations: connection status, permissions, sync history/errors, reconnect, and file import.

## PostgreSQL data ownership

| Owner | Principal records |
|---|---|
| Athlete | athletes, athlete_preferences, sport_zones, goals, limitations |
| Workouts | training_plans, training_blocks, workouts, workout_steps, workout_templates |
| Calendar | calendar_entries, availability_rules, reminders |
| Races | races, race_disciplines, race_results |
| Activities | activities, activity_laps, activity_stream_refs, workout_activity_links |
| Training load | load_metrics, threshold_history, metric_runs |
| Recovery | wellness_entries, sleep_summaries, recovery_assessments |
| Equipment | equipment, equipment_usage, maintenance_events |
| Coaching | coaching_threads, recommendations, recommendation_decisions |
| Integrations | integration_accounts, sync_runs, external_records, webhook_events |

Keep summaries in PostgreSQL. Decide after measuring real volume whether dense activity streams use partitioned PostgreSQL tables or object storage; do not default to large unqueryable JSON documents.

## Main workflows

```text
Provider event/poll/file -> integration inbox -> deduplicate -> normalize Activity
                         -> match Workout -> recalculate load/recovery
                         -> update equipment -> refresh dashboard projections
```

```text
Athlete + calendar + races + load + recovery -> validated coaching context
-> deterministic constraints + AI analysis -> explained proposal
-> athlete accepts/rejects -> accepted application command updates plan
```

## Cross-cutting policies

- Encrypt provider tokens; authenticate access to all athlete data.
- Store instants in UTC and preserve the athlete timezone for calendar intent.
- Make sync/webhook handlers idempotent and auditable.
- Version public API contracts, calculations, and AI prompts.
- Show data freshness, coverage, and explanations for analytics and AI output.
- Retain raw provider payloads only when replay/debugging requires them and apply retention limits.
- Use domain events for downstream work instead of direct module coupling.

## Delivery sequence

1. Foundation: application shells, authentication, PostgreSQL conventions, contracts, and test harnesses.
2. Athlete, workouts, races, and calendars: the planning core.
3. Canonical activities plus Strava and Garmin-compatible ingestion.
4. Versioned training-load and recovery pipelines.
5. Dashboard and equipment automation.
6. AI coaching with explainable proposals and explicit athlete approval.

No application code, dependencies, migrations, or runtime configuration are included in this architecture step.
