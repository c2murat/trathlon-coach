# Triathlon Coach

Personal triathlon planning, monitoring, recovery, and AI-coaching platform.

## Planned stack

- React frontend
- FastAPI backend
- PostgreSQL database
- Strava integration
- Garmin-compatible import and synchronization

Backend version 0.1 provides a minimal FastAPI service and health endpoint. The other planned capabilities remain architecture-only.

## Repository areas

- `backend/` - API, use cases, domain modules, persistence, analytics, and integrations.
- `frontend/` - React application organized by product feature.
- `infra/` - future local, deployment, observability, and database infrastructure.
- `docs/` - architecture decisions, data model, API contracts, and integration notes.

See [docs/architecture.md](docs/architecture.md) for the full module map and responsibilities.

## Documentation

- [Product definition](docs/PRODUCT.md) - users, journeys, MVP scope, privacy, and safety boundaries.
- [Development roadmap](docs/ROADMAP.md) - incremental versions, acceptance criteria, tests, and exclusions.
- [Coaching model](docs/COACHING_MODEL.md) - initial training principles, recovery inputs, analysis, and coaching safety rules.
- [Domain model](docs/DOMAIN_MODEL.md) - business concepts, rules, events, and shared coaching terminology independent of implementation.
- [Data model](docs/DATA_MODEL.md) - conceptual entities, ownership, constraints, privacy, and PostgreSQL guidance.
- [Entity-relationship diagrams](docs/ERD.md) - complete logical ERDs and a simplified MVP view.
- [Strava integration specification](docs/STRAVA_INTEGRATION.md) - OAuth, synchronization, webhook, security, and testing contracts.
- [Strava historical activity import](docs/STRAVA_ACTIVITY_IMPORT.md) - phased backfill, resumability, deduplication, rate limits, mapping, and reconciliation strategy.

## Provider Architecture

External platforms are isolated behind provider-neutral interfaces in `backend/app/providers/base`. Provider-specific adapters live in their own packages, beginning with `backend/app/providers/strava`. The Strava authorization-code exchange is implemented through a replaceable HTTP transport; activity API calls, webhook handling, and synchronization remain deferred.

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

Real credentials belong only in a local ignored `.env` file or separately loaded environment variables—never commit them or place the client secret in a URL. This version stores OAuth credentials as plaintext for development only; production encryption is mandatory. OAuth state remains process-local and is unsuitable for restarts, multiple workers, or production. Activity import is not implemented yet.

Sprint 0.2.4 also provides `GET /integrations/strava/status` and `DELETE /integrations/strava/disconnect`. Status returns only allow-listed connection metadata. Disconnect calls Strava's configured revocation endpoint, hard-deletes the local OAuth credential after confirmed success, marks the account disconnected, and is safe to repeat. Previously imported activities are preserved. If remote revocation fails, credentials remain available only so revocation can be retried; the endpoint does not falsely report success. Production credential encryption and secure-erasure controls remain pending.

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
```

The backend reads `TC_*` environment variables directly. The `.env` file is a local reference and is not automatically loaded in version 0.1.

PostgreSQL is the production database target. The URL above contains local development placeholders only; use separately managed credentials in deployed environments. SQLite is used only by unit tests and is not a supported production database.

### Database migrations

After PostgreSQL is running and `TC_DATABASE_URL` points to it, apply the schema from the `backend` directory:

```powershell
& ".\.venv\Scripts\python.exe" -m alembic upgrade head
```

The initial migration creates the user, athlete, integration account, isolated OAuth credential, completed activity, synchronization job, webhook inbox, and audit tables. Migration `0002_provider_account_owner` adds global provider-account ownership uniqueness. OAuth tokens are plaintext placeholders in this development foundation and must be encrypted before production use.

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
