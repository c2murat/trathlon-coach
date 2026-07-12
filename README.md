# Triathlon Coach

Personal triathlon planning, monitoring, recovery, and AI-coaching platform.

## Planned stack

- React frontend
- FastAPI backend
- PostgreSQL database
- Strava integration
- Garmin-compatible import and synchronization

This repository currently contains architecture only. Application code and runtime configuration have intentionally not been added yet.

## Repository areas

- `backend/` - API, use cases, domain modules, persistence, analytics, and integrations.
- `frontend/` - React application organized by product feature.
- `infra/` - future local, deployment, observability, and database infrastructure.
- `docs/` - architecture decisions, data model, API contracts, and integration notes.

See [docs/architecture.md](docs/architecture.md) for the full module map and responsibilities.
