# TriCoach AI

Personal triathlon planning, monitoring, recovery, and AI-coaching platform.

## Current project status

The backend foundation is complete through Version 0.3.2. FastAPI,
PostgreSQL/Alembic persistence, the provider abstraction, Strava OAuth,
connection status/disconnect, token refresh, and historical activity-summary
import are implemented. The importer is paginated, resumable, incremental, and
idempotent; it has successfully imported 1,382 real activities. The backend
regression suite passes. Version 0.4 now adds athlete-scoped activity/import
reads and the first React dashboard; local frontend dependency installation and
execution require Node.js.

## Planned stack

- React frontend
- FastAPI backend
- PostgreSQL database
- Strava integration
- Garmin-compatible import and synchronization

React is the next implementation milestone; later coaching capabilities remain
defined by the product and domain documentation.

## Repository areas

- `backend/` - API, use cases, domain modules, persistence, analytics, and integrations.
- `frontend/` - React application organized by product feature.
- `infra/` - future local, deployment, observability, and database infrastructure.
- `docs/` - architecture decisions, data model, API contracts, and integration notes.

See [docs/architecture.md](docs/architecture.md) for the full module map and responsibilities.

## Documentation

- [Product definition](docs/PRODUCT.md) - users, journeys, MVP scope, privacy, and safety boundaries.
- [Development roadmap](docs/ROADMAP.md) - incremental versions, acceptance criteria, tests, and exclusions.
- [First visible release](docs/UI_FIRST_RELEASE.md) - Version 0.4 page contract, states, wireframe, and required backend reads.
- [Coaching model](docs/COACHING_MODEL.md) - initial training principles, recovery inputs, analysis, and coaching safety rules.
- [Coach Engine architecture](docs/COACH_ENGINE.md) - future evidence, observations, recommendations, safety, audit, and deterministic/AI boundaries.
- [Analytics architecture](docs/ANALYTICS_ARCHITECTURE.md) - analytics levels, sport-aware metric catalogue, provenance, recomputation, privacy, and validation.
- [Domain model](docs/DOMAIN_MODEL.md) - business concepts, rules, events, and shared coaching terminology independent of implementation.
- [Data model](docs/DATA_MODEL.md) - conceptual entities, ownership, constraints, privacy, and PostgreSQL guidance.
- [Entity-relationship diagrams](docs/ERD.md) - complete logical ERDs and a simplified MVP view.
- [Strava integration specification](docs/STRAVA_INTEGRATION.md) - OAuth, synchronization, webhook, security, and testing contracts.
- [Strava historical activity import](docs/STRAVA_ACTIVITY_IMPORT.md) - phased backfill, resumability, deduplication, rate limits, mapping, and reconciliation strategy.

## Coach Engine strategy

The future Coach Engine will follow a deterministic, evidence-first pipeline: provider facts are normalized, versioned analytics produce traceable metrics, reviewed rules create observations, safety policy limits eligible recommendations, and the athlete retains every decision. Missing data, coverage, uncertainty, metric versions, and rule versions remain visible and auditable.

Language-model assistance is not part of the current product or Version 0.6 plan. A later explicitly approved sprint may use it only to explain already-approved evidence and decisions, with minimized inputs, audit metadata, safety validation, and a deterministic fallback. It will not own calculations, medical inference, or coaching authority. See [Coach Engine architecture](docs/COACH_ENGINE.md) and [Analytics architecture](docs/ANALYTICS_ARCHITECTURE.md).
## Provider Architecture

External platforms are isolated behind provider-neutral interfaces in `backend/app/providers/base`. Provider-specific adapters live in their own packages, beginning with `backend/app/providers/strava`. Strava OAuth, token refresh, and historical summary requests use replaceable HTTP transports. Activity details, laps, streams, and webhooks remain deferred.

## Strava OAuth connection (Sprint 0.2.3)

`GET /integrations/strava/connect` creates a single-use OAuth state and returns HTTP 307 to Strava. Configure it in PowerShell before starting the backend:

```powershell
$env:STRAVA_CLIENT_ID = "replace_with_your_client_id"
$env:STRAVA_CLIENT_SECRET = "replace_with_your_client_secret"
$env:STRAVA_REDIRECT_URI = "http://127.0.0.1:8000/integrations/strava/callback"
$env:STRAVA_AUTHORIZATION_URL = "https://www.strava.com/oauth/authorize"
$env:STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
$env:STRAVA_REVOCATION_URL = "https://www.strava.com/oauth/revoke"
$env:STRAVA_SCOPES = "read,activity:read_all"
$env:OAUTH_STATE_TTL_SECONDS = "600"
& ".\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Then open `http://127.0.0.1:8000/integrations/strava/connect` in a browser. Strava returns to the local callback URI `http://127.0.0.1:8000/integrations/strava/callback`; the callback validates one-time state, exchanges the code, and returns only the provider and connection status.

Real credentials belong only in a local ignored `.env` file or separately loaded environment variablesâ€”never commit them or place the client secret in a URL. This version stores OAuth credentials as plaintext for development only; production encryption is mandatory. In development, OAuth state is stored in a local ignored SQLite database, survives application restarts, and is shared by local processes using the same file. It is not the production state-store design; production still requires a shared PostgreSQL, Redis, or equivalent durable store.

Sprint 0.2.4 also provides `GET /integrations/strava/status` and `DELETE /integrations/strava/disconnect`. Status returns only allow-listed connection metadata. Disconnect calls Strava's configured revocation endpoint, hard-deletes the local OAuth credential after confirmed success, marks the account disconnected, and is safe to repeat. Previously imported activities are preserved. If remote revocation fails, credentials remain available only so revocation can be retried; the endpoint does not falsely report success. Production credential encryption and secure-erasure controls remain pending.

## Strava historical summary import (Sprint 0.3.2)

An active Strava connection is required. Start the non-blocking historical
summary import from PowerShell:

```powershell
$job = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/integrations/strava/imports"
$job
```

Check its safe, checkpointed status with the returned job identifier:

```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/integrations/strava/imports/$($job.job_id)"
```

Sprint 0.3.2 imports activity summaries only. It paginates historical results,
updates existing provider-owned summary fields idempotently, preserves local
athlete-authored fields, and resumes from committed page checkpoints. Activity
details, laps, and streams are deliberately deferred to later phases.

Repeated start requests reuse a queued, running, or retry-scheduled job. After a
job reaches a terminal state, the next request creates a new job. Following a
successful history import, that job is incremental: it starts from the newest
stored activity with the configured overlap (24 hours by default), while the
existing provider-account/activity identity prevents duplicates.

## Version 0.4 â€” First usable web interface

Version 0.4 delivers the first usable React page: TriCoach AI application shell,
backend and Strava status, imported activity total, last synchronization, recent
10 activities, import progress, and Connect/Synchronize actions with complete
loading, empty, offline, and error states.

Before the page can be complete, Sprint 0.4 must add athlete-scoped recent
activity/total and latest-import-status read endpoints. Activity details,
analytics, planning, recovery, and AI are explicitly outside this milestone.
See [the first UI release specification](docs/UI_FIRST_RELEASE.md).

## Backend 0.1 on Windows

The following commands use the required Python 3.13 executable. Run them in PowerShell from the repository root.

### Install dependencies

```powershell
cd backend
& "C:\Users\LENOVO\AppData\Local\Programs\Python\Python313\python.exe" -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
```

### Configure environment variables

The service has safe development defaults. To customize them, copy the example and load the values into your PowerShell environment:

```powershell
Copy-Item .env.example .env
$env:TC_ENVIRONMENT = "development"
$env:TC_HOST = "127.0.0.1"
$env:TC_PORT = "8000"
$env:TC_LOG_LEVEL = "info"
$env:TC_DATABASE_URL = "postgresql+psycopg://triathlon:triathlon@localhost:5432/triathlon_coach"
$env:FRONTEND_ORIGIN = "http://127.0.0.1:5173"
```

The backend loads `backend/.env` automatically using an absolute path, and process-level environment variables can override its values.

PostgreSQL is the production database target. The URL above contains local development placeholders only; use separately managed credentials in deployed environments. SQLite is used only by unit tests and is not a supported production database.

### Start PostgreSQL on Windows

Open PowerShell as Administrator, discover the installed PostgreSQL service, and
start it:

```powershell
$postgresService = Get-Service -Name "postgresql*" | Select-Object -First 1
Start-Service -Name $postgresService.Name
Get-Service -Name $postgresService.Name
```

The final command must report `Running`. Ensure the database named by
`TC_DATABASE_URL` exists and its local credentials match your ignored
`backend/.env` file.

### Database migrations

After PostgreSQL is running and `TC_DATABASE_URL` points to it, apply the schema from the `backend` directory:

```powershell
& ".\.venv\Scripts\python.exe" -m alembic upgrade head
```

The initial migration creates the user, athlete, integration account, isolated OAuth credential, completed activity, synchronization job, webhook inbox, and audit tables. Migration `0002_provider_account_owner` adds global provider-account ownership uniqueness. Migration `0003_strava_summary_import` adds summary metrics and enforces one active historical summary job per Strava account. OAuth tokens are plaintext placeholders in this development foundation and must be encrypted before production use.

### Seed the local development athlete

After applying migrations, run the idempotent development seed from the `backend` directory:

```powershell
& ".\.venv\Scripts\python.exe" -m app.cli.seed_development_user
```

The command creates the fixed local MVP user and its athlete profile using placeholder development data. It is safe to run repeatedly and does not create duplicates.

### Run the backend

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/health`. The response is:

```json
{
  "status": "ok",
  "service": "triathlon-coach"
}
```

### Run tests

```powershell
& ".\.venv\Scripts\python.exe" -m pytest
```

## Frontend 0.4 on Windows

Install a current Node.js LTS release first. Then run these commands in a new
PowerShell window from the repository root:

### Install frontend dependencies

```powershell
cd frontend
Copy-Item .env.example .env
npm install
```

The development environment contains only the public backend origin:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Never put a Strava secret or OAuth token in a `VITE_*` variable because Vite
exposes those values to the browser.

### Run the frontend

```powershell
npm run dev
```

### Run frontend tests and build

```powershell
npm test
npm run build
```

## Local URLs

- Frontend dashboard: `http://127.0.0.1:5173`
- Backend API and OAuth callback host: `http://127.0.0.1:8000`
- Backend health: `http://127.0.0.1:8000/health`
- Interactive API documentation: `http://127.0.0.1:8000/docs`

## First-use workflow

1. Start PostgreSQL.
2. From `backend`, apply Alembic migrations and seed the fixed development user.
3. Start the backend on `127.0.0.1:8000`.
4. From `frontend`, install dependencies and start Vite on `127.0.0.1:5173`.
5. Open the frontend dashboard.
6. If Strava is disconnected, choose **Connect Strava** and complete OAuth in
   the browser. Return to or reload the dashboard afterward.
7. Choose **Synchronize activities**. The page polls the safe job endpoint and
   refreshes the activity total and recent list after success.

### Estado del dashboard pulido de Version 0.4

El dashboard de Version 0.4 esta pulido y localizado al espanol: estados, deportes, fechas, metricas, sincronizacion accesible y disposicion adaptable. Los comandos exactos del frontend, desde `frontend/`, son:

```powershell
npm install
npm run dev
npm test
npm run build
```

### Captura de pantalla

> Pendiente: anadir aqui una captura del dashboard de Version 0.4 en escritorio y movil.

### Limitaciones conocidas de Version 0.4

- Usa un unico atleta local de desarrollo y el saludo fijo `Hola, Carlos`; no incluye autenticacion ni edicion de perfil.
- Muestra resumenes recientes de actividades, no detalles, vueltas, streams, mapas ni graficos.
- La sincronizacion depende de una conexion Strava y del backend local disponibles.
- No incluye IA, planificacion, Garmin ni funcionalidades de Version 0.5.

## Version 0.5A — Athlete dashboard

Version 0.5A adds athlete-owned deterministic summaries from the activity data already stored in PostgreSQL. These metrics describe recorded training history; they are not coaching advice, readiness scores, or recommendations.

Analytics endpoints (backend: `http://127.0.0.1:8000`):

- `GET /dashboard/summary?period=week` (`week`, `month`, `last_30_days`, `year`)
- `GET /dashboard/trends?weeks=8` (4–52 ISO weeks, oldest to newest)
- `GET /dashboard/consistency?weeks=12` (4–52 weeks)

The frontend remains at `http://127.0.0.1:5173`. From `frontend/`, run `npm run dev`, `npm test`, and `npm run build`.

Known limitations: aggregates depend on imported summary completeness; moving time, distance, and elevation missing from a provider summary contribute zero; the current week is partial; there are no activity details, laps, streams, maps, coaching metrics, AI, planning, Garmin, or authentication.

## Version 0.5A.1 — UX and dashboard polish

Version 0.5A.1 adds a responsive application shell, accessible sidebar/mobile navigation, a time-aware Spanish greeting, a compact development user menu, persisted light/dark themes, refined dashboard cards, keyboard-readable chart values, and a non-error activity-detail placeholder.

Routes: `/` redirects to `/dashboard`; `/dashboard` is operational; `/activities`, `/calendar`, `/statistics`, `/health`, and `/settings` display honest `Próximamente` pages. Theme selection defaults to the system preference and persists under `tricoach-theme` in `localStorage`.

Exact startup commands from the repository root:

```powershell
& ".\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
cd frontend
npm install
npm run dev
```

Run `npm test` and `npm run build` from `frontend/` for verification.

### Screenshot

Expected path: `docs/screenshots/dashboard-0.5A.1.png`. No fake screenshot is committed.

Known limitations: only Dashboard is operational; activity details remain a Version 0.5B placeholder; profile editing and sign-out are disabled; production hosting must provide SPA fallback; analytics are deterministic summaries, not coaching advice.

## Version 0.5B — Activity browsing foundations

Version 0.5B makes `http://127.0.0.1:5173/activities` operational. The athlete can explicitly apply combined filters, preserve them in the URL, paginate through safe summary cards, and open `http://127.0.0.1:5173/activities/{activityId}` for an imported-summary-only view.

Backend endpoints:

- `GET http://127.0.0.1:8000/activities` — offset pagination (20 by default, 100 maximum) and optional `sport`, `date_from`, `date_to`, `min_distance_metres`, `max_distance_metres`, `trainer`, `manual`, `visibility`, and `search` filters.
- `GET http://127.0.0.1:8000/activities/filter-options` — athlete-owned available sports, visibility values, and activity date bounds.
- `GET http://127.0.0.1:8000/activities/{activity_id}` — athlete-owned allow-listed imported summary or 404.

Filters use AND semantics. The total is calculated after filtering, rows are newest first with deterministic ID ordering, and deleted/provider-deleted/future activities are excluded. Frontend filters are fetched only after **Aplicar filtros**, except page changes; browser back/forward restores URL state.

Exact local startup commands remain:

```powershell
& ".\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
cd frontend
npm install
npm run dev
```

Known limitations: detail uses only stored Strava summary fields; missing fields display as unavailable; there are no laps, streams, maps, editing, deletion, renaming, comments, social features, authentication, AI, coaching, planning, or Garmin support.

## Version 0.5B.1 — Activity summary display polish

Version 0.5B.1 changes presentation only. Activity detail metrics remain sourced exclusively from the stored Strava summary; the frontend does not request enrichment.

Sport-aware formatting:

- Running and walking speed is displayed as pace in `min/km`.
- Cycling speed is displayed in Spanish-decimal `km/h`.
- Swimming speed is displayed as `mm:ss /100 m`.
- Other meaningful positive speeds use `km/h`; zero, invalid, and missing values display as `No disponible`.
- Running cadence uses `ppm`, meaning pasos por minuto. Cycling cadence uses `rpm`. Swimming cadence remains unavailable because the canonical field does not confirm stroke-rate semantics.
- Average and weighted power are rounded and always use the literal unit `W`.

Visibility, trainer, manual-entry, and commute metadata are localized into readable Spanish phrases. The detail view is organized into **Resumen**, **Rendimiento**, and **Información de la actividad**.

Known limitations: pace and speed quality depends on imported summary values; maximum stored speed is presented as best pace where applicable; swimming stroke cadence is deliberately not inferred; laps, streams, maps, enrichment, editing, AI, coaching, planning, and Garmin remain unavailable.

## Version 0.5B.2 — Activity detail final polish

Version 0.5B.2 is a presentation-only release for the stored-summary activity page. It introduces a responsive sport-decorated hero, a compact localized summary and weekday/date line, a friendly roadmap notice, stronger primary metric typography, decorative performance cues, metadata badges, softer empty states, and refined light/dark hover and focus behavior.

Power values are rendered with a code-owned literal SI unit (`W`). Number localization is applied only to the numeric portion, so values such as `174 W` and `184 W` cannot become translated direction words.

No API, persistence, migration, enrichment, or Strava behavior changed. Activity data still comes exclusively from stored Strava summaries.

Remaining UI limitations before Version 0.6:

- Hero summaries are limited to fields already present in imported summaries.
- Missing metrics use an em dash and cannot distinguish unavailable provider data from unsupported device recording.
- Decorative symbols use the existing lightweight character icon approach rather than a formal SVG icon system.
- There are no maps, laps, streams, advanced analysis, editing, AI, coaching, planning, Garmin, or authentication features.




## Version 0.6A — Strava activity detail enrichment

Version 0.6A adds selective, athlete-owned enrichment of stored activity summaries through `GET /activities/{external_activity_id}` at Strava. The frontend never calls Strava directly.

- `POST /integrations/strava/enrichments` accepts optional local `activity_ids` and `limit` (default 10, maximum 50), returns HTTP 202, and schedules bounded work.
- `GET /integrations/strava/enrichments/{job_id}` returns allow-listed progress, checkpoints, retry time, and a safe error category.
- Activities are selected when never enriched, changed by a later summary synchronization, or previously failed and remain eligible. Repeated successful enrichment updates the same `CompletedActivity` and avoids unnecessary field writes.
- Provider-owned description and perceived exertion are stored separately from the athlete's local `description` and `rpe`. No raw Strava payload is retained.
- Migration `0004_strava_activity_detail` adds only provider detail and enrichment lifecycle columns.
- Temporary failures and rate limits pause with a checkpoint; expired tokens use the existing refresh service; revoked credentials require reconnection; unavailable activities follow the provider-deleted lifecycle.

Known limitations: execution uses the current in-process task mechanism, so production still needs a durable worker/lease strategy. Detail fields depend on Strava availability and scopes. Laps, streams, maps, route rendering, metrics, coaching, recommendations and AI are not included.

## Version 0.6B — Laps, streams, and factual evidence

Version 0.6B adds selective activity evidence without coaching interpretation:

- `POST /integrations/strava/evidence` queues athlete-owned lap and selected-stream retrieval.
- `GET /integrations/strava/evidence/{job_id}` returns allow-listed progress only.
- `GET /activities/{activity_id}/evidence` returns bounded laps, supported non-location streams, route state, coverage and missing-stream names.
- `DELETE /integrations/strava/evidence/location` removes retained `latlng` streams and route evidence for the current athlete when location retention is disabled.

Supported initial streams are `time`, `distance`, `heartrate`, `watts`, `cadence`, `altitude`, `velocity_smooth`, and optionally `latlng`. General stream retention defaults on; location retention defaults off. Configure `TC_ACTIVITY_STREAM_RETENTION_ENABLED`, `TC_ACTIVITY_LOCATION_STREAM_RETENTION_ENABLED`, `TC_ACTIVITY_STREAM_MAX_SAMPLES` (default 1000), and `TC_ACTIVITY_STREAM_RETENTION_DAYS` (`0` means no automatic age deletion).

Streams use portable SQLAlchemy JSON: PostgreSQL stores JSONB and SQLite stores JSON. One row exists per activity/type with checksum, version, original/retained counts and timestamps. Deterministic shared-index downsampling preserves first/final samples and alignment. API responses remain capped by the configured sample maximum. Raw provider payloads are not stored.

The activity page provides a responsive laps table and lightweight SVG stream charts with Spanish tabs, shared factual axes, downsampling disclosure and a text alternative. Location-disabled state is explicit. A route placeholder is shown when evidence exists; third-party maps and tokens remain deferred.

Known limitations: the background executor remains in-process; retention expiry is enforced when an evidence job starts (there is no standalone scheduler); provider streams can be absent; polylines are not decoded into a map. No deterministic sport metrics, observations, recommendations, coaching, planning or AI are included.

Next sprint: Version 0.6C — deterministic factual metrics and coverage rules. It is not part of Version 0.6B and has not begun.

