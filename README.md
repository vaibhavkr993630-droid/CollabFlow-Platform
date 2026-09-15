<h1 align="center">CollabFlow</h1>

<p align="center">
  <b>A real-time collaboration and project-management platform.</b><br>
  A focused hybrid of Jira (projects, tasks, boards) and Slack (live updates, presence).
</p>

<p align="center">
  <img alt="Status" src="https://img.shields.io/badge/status-in%20development-blue">
  <img alt="Phase" src="https://img.shields.io/badge/phase-5%20of%209%20%E2%80%94%20notifications-brightgreen">
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
| Real-time | **WebSockets + Redis pub/sub** | Horizontal-scale-ready fan-out: any instance can deliver an event to any connected client |
| Background jobs | **Celery + Redis** | Email notifications and scheduled reminders off the request path |
| File storage | **S3-compatible object storage / MinIO** *(Phase 6)* | Attachments never touch the app server's disk; downloads use presigned URLs |

## Data model (Phase 1 + 2)

```
users ──< workspace_memberships >── workspaces >── organizations >── users (owner)
  │                                      │
  │                                      └──< projects ──< project_memberships >── users
  │                                                │
  │                                                ├──< tasks ──< comments >── users (author)
  │                                                │       │  └─< task_labels >── labels
  │                                                │       └─ parent_task_id (subtasks, self-FK)
  │                                                └──< labels
  └──────────────────────────────────────────────────────────────────────────────────────────
                     role (workspace_memberships / project_memberships): owner | admin | member
```

- **User** — email (unique, indexed), hashed password, full name, active flag.
- **Organization** — the billing/ownership boundary. Has a unique `slug` and an `owner_id`.
- **Workspace** — a team space inside an organization. `slug` is unique **per organization**
  (`uq_workspace_org_slug`), not globally.
- **WorkspaceMembership / ProjectMembership** — join tables carrying a shared `Role` enum
  (`app/models/roles.py`), backed by one Postgres enum (`member_role`). One row per
  `(workspace, user)` or `(project, user)` pair. `ROLE_RANK` (`member < admin < owner`) drives
  every "minimum role" RBAC dependency.
- **Project** — lives inside a workspace; creating one seeds the creator as an Owner-role member.
- **Task** — `status` / `priority` enums, optional `assignee_id`, self-referential
  `parent_task_id` for subtasks, `position` reserved for Kanban ordering.
- **Label** — project-scoped, many-to-many with tasks via `task_labels`.
- **Comment** — `task_id` / `author_id` / `body`.

Every table uses a UUID primary key (`default=uuid4`, generated app-side) and timezone-aware
`created_at` / `updated_at` columns via shared mixins in [`app/db/base.py`](backend/app/db/base.py).

## Real-time architecture

Every backend instance subscribes to Redis pub/sub (`project:{id}:events`, pattern-subscribed
once as `project:*:events`) and relays messages to whichever WebSocket clients happen to be
connected to *that* instance. A REST call that changes a task publishes to Redis rather than
pushing to local sockets directly — so a task updated via an API call served by instance A still
reaches a WebSocket client connected to instance B. Only one instance runs in this project's
setup, so that fan-out is presently a no-op round trip through Redis rather than something
observably necessary — but the code path is identical either way, which is the point: horizontal
scaling readiness without needing a rewrite to add it later.

Presence (who's viewing a project) is tracked in Redis as a per-project hash of
`user_id -> open-connection-count` (`app/ws/presence.py`), not a local in-process set — a ref
count because one user can hold multiple tabs/connections open, and a Redis-backed count (not an
in-memory one) because it needs to stay correct even if those connections land on different
instances. `GET /api/projects/{project_id}/presence` exposes the same data over REST for clients
that want a snapshot without opening a socket.

**Known simplification:** the WebSocket handshake passes the JWT access token as a query
parameter (`?token=...`), not an `Authorization` header — browsers' native WebSocket API can't
set custom headers on the handshake request. This means a short-lived access token can end up in
server access logs via the query string. A production system would issue a short-lived, single-use
WS ticket via an authenticated REST call instead of reusing the access token here. See
[`docs/PHASE-4.md`](docs/PHASE-4.md) for the four concurrency bugs found building this.

## API surface (Phase 1–4)

```
POST   /api/auth/register | login | refresh        GET /api/auth/me
POST   /api/organizations                           GET  /api/organizations
POST   /api/organizations/{org_id}/workspaces        GET  .../workspaces
GET/POST  /api/workspaces/{workspace_id}/members
POST   /api/workspaces/{workspace_id}/projects        GET  .../projects
GET/POST  /api/projects/{project_id}/members
POST   /api/projects/{project_id}/tasks
GET    /api/projects/{project_id}/tasks?status=&priority=&assignee_id=&label_id=
                                        &search=&sort_by=&sort_order=&page=&page_size=
GET/PATCH/DELETE  /api/tasks/{task_id}                 GET  .../subtasks
POST   /api/projects/{project_id}/labels               GET  .../labels
POST   /api/tasks/{task_id}/comments                    GET  .../comments
GET    /api/projects/{project_id}/activity?page=&page_size=
GET    /api/tasks/{task_id}/activity?page=&page_size=
GET    /api/projects/{project_id}/presence
WS     /ws/projects/{project_id}?token=<jwt>
GET    /api/notifications?page=&page_size=       GET  .../unread-count
POST   /api/notifications/{id}/read              POST .../read-all
WS     /ws/notifications?token=<jwt>
```

Full interactive docs at `/docs` once the server is running.

## Notifications & background jobs

In-app notifications (mentions, task assignments, workspace/project invites, due-soon reminders)
are delivered live over `/ws/notifications` and persisted to the `notifications` table. Each one
also queues a Celery task that sends an email — in local dev this goes to a MailDev container, not
a real inbox, so nothing needs real SMTP credentials to test the full flow. View sent mail at
`http://localhost:1080`. Celery Beat runs `send_due_soon_reminders` once daily (see
`app/workers/celery_app.py`) for tasks due the next day.

`@mentions` in comments use the mentioned user's **email** (e.g. `@alice@example.com`) — there's
no separate username field on `User`, and email is the only identifier a mention can unambiguously
resolve to one account. A mention only notifies if that email belongs to an actual member of the
task's project; mentioning a non-member's email is a silent no-op (not an error) — see
`app/services/comment_service.py`.

## Quickstart

**Requirements:** Python 3.12+, Docker (for Postgres, Redis, MailDev), or your own local instances.

```bash
# 1. Infrastructure
docker compose up -d postgres redis maildev

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

### Running the background worker

Needed for email sending and the due-soon reminder job — the API queues Celery tasks regardless
of whether a worker is running, so nothing breaks without one, but nothing gets delivered either.

```bash
celery -A app.workers.celery_app worker --loglevel=info   # processes queued tasks
celery -A app.workers.celery_app beat --loglevel=info      # schedules the daily reminder job
```

### Tests

```bash
cd backend
pytest
```

## Roadmap

| Phase | Scope | State |
|------:|-------|:-----:|
| **1** | Foundation — app skeleton, typed settings, async DB layer, org/workspace/membership models, first migration | ✅ **Done** |
| **2** | Auth (JWT register/login/refresh) + RBAC dependencies + projects, tasks, labels, comments | ✅ **Done** |
| **3** | Activity log + task filtering, sorting, search, pagination | ✅ **Done** |
| **4** | Real-time: WebSocket endpoint, Redis pub/sub fan-out, presence tracking | ✅ **Done** |
| **5** | Notifications (in-app + email via Celery) + due-soon reminders | ✅ **Done** |
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
