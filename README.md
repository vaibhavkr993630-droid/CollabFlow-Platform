<h1 align="center">CollabFlow</h1>

<p align="center">
  <b>A real-time collaboration and project-management platform.</b><br>
  A focused hybrid of Jira (projects, tasks, boards) and Slack (live updates, presence).
</p>

<p align="center">
  <a href="https://github.com/vaibhavkr993630-droid/CollabFlow-Platform/actions/workflows/backend-ci.yml"><img alt="Backend CI" src="https://github.com/vaibhavkr993630-droid/CollabFlow-Platform/actions/workflows/backend-ci.yml/badge.svg"></a>
  <img alt="Status" src="https://img.shields.io/badge/status-in%20development-blue">
  <img alt="Phase" src="https://img.shields.io/badge/phase-9%20%E2%80%94%20frontend%20complete-brightgreen">
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
| File storage | **S3-compatible object storage / MinIO** | Attachments never touch the app server's disk; downloads use presigned URLs |
| Frontend | **React 19 + TypeScript, Vite, Tailwind v4, TanStack Query, `@dnd-kit`** | Optimistic UI + live WS-driven refresh on the same data TanStack Query already caches |

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
POST   /api/auth/forgot-password | reset-password    (emailed, single-use, 30-minute link)
POST   /api/organizations                           GET  /api/organizations
POST   /api/organizations/{org_id}/workspaces        GET  .../workspaces
GET/POST  /api/workspaces/{workspace_id}/members
POST   /api/workspaces/{workspace_id}/projects        GET  .../projects
GET    /api/projects/{project_id}
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
POST   /api/tasks/{task_id}/attachments (multipart)   GET  .../attachments
GET    /api/tasks/{task_id}/attachments/{id}/download
DELETE /api/tasks/{task_id}/attachments/{id}
```

Full interactive docs at `/docs` once the server is running.

## Frontend

`frontend/` is a Vite + React 19 + TypeScript app. It's not yet in `docker-compose.yml` (that
predates the frontend existing) — run it separately:

```bash
cd frontend
npm install
npm run dev
```

Serves on `http://localhost:5173`; Vite's dev proxy (`vite.config.ts`) forwards `/api` and `/ws`
to the backend on `:8000`, so no CORS setup or `VITE_API_BASE_URL` is needed for local dev — that
env var exists for production only, where the frontend and backend are on different domains.

**WebSocket client** (`src/ws/useWebSocket.ts`) reconnects with exponential backoff (1s base,
capped at 30s, with jitter), resetting to a fresh backoff schedule on every successful reconnect.
It treats the backend's `4401` WS auth-failure close code specially (a higher base delay — retrying
instantly with a token that was just rejected is more likely hammering a dead session than
catching one about to refresh) and re-reads the current access token on every reconnect attempt
rather than one captured at connect time, so a reconnect after a token refresh picks up the new
one automatically.

**A note on this repo's location under `/mnt/d/...`:** if you're on WSL2 with the project on a
Windows-mounted drive, Vite's native file watcher may not pick up edits reliably (`vite.config.ts`
already sets `server.watch.usePolling` for this reason — see [`docs/PHASE-7.md`](docs/PHASE-7.md)
for how this was discovered). If HMR ever seems to silently stop working, that's the first thing
to suspect.

### What the UI covers

Organizations, workspaces and projects; a drag-and-drop Kanban board with live updates and
presence; task detail with description, status, priority, due date, **assignee**, labels,
**subtasks**, attachments and comments; **workspace and project members with role badges and
invite-by-email**; a **project activity feed**; notifications; and **search / filter / sort**
across the board.

Known gaps, all of them missing backend endpoints rather than missing screens: no renaming or
deleting an org/workspace/project, no changing a role or removing a member, no editing or
deleting a comment, and invites require the person to already have an account. See
[`docs/PHASE-9.md`](docs/PHASE-9.md).

## File attachments

Tasks can have file attachments, stored in MinIO (S3-compatible) rather than the app server's own
disk — the API server never proxies file bytes on download. Upload goes through the API
(`POST /api/tasks/{task_id}/attachments`, multipart), but download returns a **presigned URL**
(`GET .../attachments/{id}/download`) that the client fetches directly from MinIO, valid for 5
minutes. Files are capped at `MAX_ATTACHMENT_SIZE_MB` (10MB by default); there's no content-type
restriction beyond that — MinIO never executes stored objects, so this isn't a code-execution
surface the way serving uploads back through the app server would be.

MinIO's own console is at `http://localhost:9001` (login: the `S3_ACCESS_KEY`/`S3_SECRET_KEY`
values in `.env`) if you want to browse the bucket directly.

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

**Requirements:** Docker. For the second option also Python 3.12+ and Node 20+.

There are two ways to run the backend locally — pick whichever fits what you're doing.

### Option A: the whole backend stack in Docker (fastest way to just run it)

```bash
docker compose up -d --build
```

Brings up Postgres, Redis, MinIO, MailDev, the API, a Celery worker and Celery Beat, building the
backend image from [`backend/Dockerfile`](backend/Dockerfile). A one-shot `migrate` service applies
the Alembic migrations first; `backend`, `worker` and `beat` wait for it to exit successfully. The
API is then at <http://localhost:8000/docs>. The frontend is not part of Compose — run it as in
step 5 below.

### Option B: infrastructure in Docker, backend on your machine (for active backend work)

```bash
# 1. Infrastructure
docker compose up -d postgres redis maildev minio

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# 3. Schema
alembic upgrade head

# 4. Run
uvicorn app.main:app --reload

# 5. Frontend (separate terminal)
cd ../frontend
npm install
npm run dev
```

- API + interactive docs: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health> — checks Postgres and Redis, not just that the
  process is alive: `200 {"status": "ok"}` when both answer, `503` naming the one that didn't
- Frontend: <http://localhost:5173>

### Running the background worker (Option B only — Option A already runs these)

Needed for email sending and the due-soon reminder job — the API queues Celery tasks regardless
of whether a worker is running, so nothing breaks without one, but nothing gets delivered either.

```bash
celery -A app.workers.celery_app worker --loglevel=info   # processes queued tasks
celery -A app.workers.celery_app beat --loglevel=info      # schedules the daily reminder job
```

### Tests

```bash
cd backend
pytest                              # against real Postgres, Redis and MinIO
ruff check app tests migrations     # the lint step CI runs
```

CI (`.github/workflows/backend-ci.yml`) runs exactly this on every push or pull request touching
`backend/**`, plus `alembic upgrade head` against a real Postgres — see
[`docs/PHASE-8.md`](docs/PHASE-8.md) for why each step is there.

## Operations

- **Logs** are one JSON object per line (`timestamp`, `level`, `logger`, `message`, and
  `exception` when there is a traceback), from both the API and the Celery worker.
- **Error tracking:** set `SENTRY_DSN` to enable Sentry. Unset (the default), it never
  initializes and the app behaves identically.
- **S3 endpoints:** `S3_ENDPOINT_URL` is what the backend itself uses for uploads and deletes
  (inside Compose, the service name `http://minio:9000`). `S3_PUBLIC_ENDPOINT_URL` is what gets
  baked into presigned download URLs handed to browsers, which cannot resolve `minio`
  (`http://localhost:9000` in Compose). Leave it unset outside Docker, where both are localhost.

## Roadmap

| Phase | Scope | State |
|------:|-------|:-----:|
| **1** | Foundation — app skeleton, typed settings, async DB layer, org/workspace/membership models, first migration | ✅ **Done** |
| **2** | Auth (JWT register/login/refresh) + RBAC dependencies + projects, tasks, labels, comments | ✅ **Done** |
| **3** | Activity log + task filtering, sorting, search, pagination | ✅ **Done** |
| **4** | Real-time: WebSocket endpoint, Redis pub/sub fan-out, presence tracking | ✅ **Done** |
| **5** | Notifications (in-app + email via Celery) + due-soon reminders | ✅ **Done** |
| **6** | File attachments on tasks (S3-compatible storage, presigned downloads) | ✅ **Done** |
| **7** | Frontend — React 19 + TypeScript, boards, real-time client | ✅ **Done** |
| **8** | Hardening — Docker Compose stack, structured logging, CI, health checks | ✅ **Done** |
| **9** | Frontend completeness — members & roles, assignees, subtasks, label creation, search/filter/sort, activity feed, HTML email | ✅ **Done** |
| 10 | Deployment — managed Postgres/Redis/object storage + hosted frontend | ⏳ In progress |

## Repository layout

```
backend/
  app/
    core/config.py       # typed settings (pydantic-settings)
    db/base.py           # DeclarativeBase + UUID / timestamp mixins
    db/session.py        # async engine + session dependency
    models/              # User, Organization, Workspace, WorkspaceMembership, ...
    main.py              # FastAPI app + lifespan + /health
  migrations/            # Alembic (async env) + versioned scripts
  pyproject.toml
frontend/
  src/
    api/                 # typed wrappers over the backend REST API
    auth/                 # AuthContext, ProtectedRoute
    ws/                    # WebSocket client (reconnect/backoff)
    pages/, components/    # dashboard, Kanban board, task detail, members, activity
    lib/, hooks/           # formatting/error helpers, shared queries
  vercel.json            # SPA rewrite for client-side routes
.railway/railway.ts      # Railway infrastructure-as-code
docker-compose.yml       # Postgres, Redis, MailDev, MinIO + API, worker, beat, one-shot migrate
docs/                    # per-phase reports
PROGRESS.md              # running phase log
```

## License

MIT — see [`LICENSE`](LICENSE).
