<h1 align="center">CollabFlow</h1>

<p align="center">
  <b>A real-time collaboration and project-management platform.</b><br>
  A focused hybrid of Jira (projects, tasks, boards) and Slack (live updates, presence).
</p>

<p align="center">
  <img alt="Status" src="https://img.shields.io/badge/status-in%20development-blue">
  <img alt="Phase" src="https://img.shields.io/badge/phase-1%20of%209%20%E2%80%94%20foundation-brightgreen">
  <img alt="Backend" src="https://img.shields.io/badge/backend-FastAPI%20%2B%20async%20SQLAlchemy-009688">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12%2B-3776AB">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-black">
</p>

---

## What this is

CollabFlow is a from-scratch build of a team workspace where planning and communication
live in the same place. Teams organize work into **organizations → workspaces → projects →
tasks**, and every change — a task moved across the board, a new comment, someone joining a
project — propagates to everyone viewing it in real time, with no page refresh.

This repository is being built and committed **phase by phase**. Each phase is a self-contained,
reviewable slice of functionality with its own migration, tests, and progress notes. See the
[roadmap](#roadmap) below and [`docs/`](docs/) for the detailed report on each completed phase.

## Architecture at a glance

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI** (async) | First-class async, automatic OpenAPI docs, dependency-injection that maps cleanly onto per-request auth and RBAC |
| ORM | **SQLAlchemy 2.0** (async, typed `Mapped[...]`) | Fully typed models, explicit unit-of-work, async engine over `asyncpg` |
| Database | **PostgreSQL 16** | Native `uuid`, enum types, and constraint support the domain leans on |
| Migrations | **Alembic** (async env) | Every schema change is a versioned, reviewable script — no auto-sync in any environment |
| Real-time | **WebSockets + Redis pub/sub** *(Phase 4)* | Horizontal-scale-ready fan-out: any instance can deliver an event to any connected client |
| Background jobs | **Celery + Redis** *(Phase 5)* | Email notifications and scheduled reminders off the request path |
| File storage | **S3-compatible object storage / MinIO** *(Phase 6)* | Attachments never touch the app server's disk; downloads use presigned URLs |

## Data model (Phase 1)

```
users ──< workspace_memberships >── workspaces >── organizations >── users (owner)
                    │
                  role: owner | admin | member
```

- **User** — email (unique, indexed), hashed password, full name, active flag.
- **Organization** — the billing/ownership boundary. Has a unique `slug` and an `owner_id`.
- **Workspace** — a team space inside an organization. `slug` is unique **per organization**
  (`uq_workspace_org_slug`), not globally.
- **WorkspaceMembership** — join table carrying a `role` enum. One row per `(workspace, user)`
  pair (`uq_membership_workspace_user`). Role rank (`member < admin < owner`) drives the
  "minimum role" permission checks added in Phase 2.

Every table uses a UUID primary key (`default=uuid4`, generated app-side) and timezone-aware
`created_at` / `updated_at` columns via shared mixins in [`app/db/base.py`](backend/app/db/base.py).

## Quickstart

**Requirements:** Python 3.12+, Docker (for Postgres & Redis), or your own local instances.

```bash
# 1. Infrastructure
docker compose up -d postgres redis

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# 3. Schema
alembic upgrade head

# 4. Run
uvicorn app.main:app --reload
```

- API + interactive docs: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health> — returns `{"status": "ok"}`

### Tests

```bash
cd backend
pytest
```

## Roadmap

| Phase | Scope | State |
|------:|-------|:-----:|
| **1** | Foundation — app skeleton, typed settings, async DB layer, org/workspace/membership models, first migration | ✅ **Done** |
| 2 | Auth (JWT register/login/refresh) + RBAC dependencies + projects, tasks, labels, comments | ⏳ Planned |
| 3 | Activity log + task filtering, sorting, search, pagination | ⏳ Planned |
| 4 | Real-time: WebSocket endpoint, Redis pub/sub fan-out, presence tracking | ⏳ Planned |
| 5 | Notifications (in-app + email via Celery) + due-soon reminders | ⏳ Planned |
| 6 | File attachments on tasks (S3-compatible storage, presigned downloads) | ⏳ Planned |
| 7 | Frontend — React 19 + TypeScript, boards, real-time client | ⏳ Planned |
| 8 | Hardening — Docker Compose stack, structured logging, CI, health checks | ⏳ Planned |
| 9 | Deployment — managed Postgres/Redis/object storage + hosted frontend | ⏳ Planned |

## Repository layout

```
backend/
  app/
    core/config.py       # typed settings (pydantic-settings)
    db/base.py           # DeclarativeBase + UUID / timestamp mixins
    db/session.py        # async engine + session dependency
    models/              # User, Organization, Workspace, WorkspaceMembership
    main.py              # FastAPI app + /health
  migrations/            # Alembic (async env) + versioned scripts
  pyproject.toml
docker-compose.yml       # Postgres, Redis, MinIO for local dev
docs/                    # per-phase reports
PROGRESS.md              # running phase log
```

## License

MIT — see [`LICENSE`](LICENSE).
