# CollabFlow — Progress Log

A running record of what has been built, phase by phase, and the decisions behind it.
Read this before touching code.

---

## Phase 1 — Foundation ✅

**Goal:** a runnable backend skeleton with the identity/tenancy data model in place, so every
later phase has a database, a settings system, and a migration chain to build on.

### Delivered

- **Application skeleton** — `app/main.py`: FastAPI app, CORS middleware driven by settings,
  and a `/health` endpoint.
- **Typed configuration** — `app/core/config.py`: `pydantic-settings` `Settings` object,
  `.env`-backed, `@lru_cache`d accessor. Database URL, JWT parameters, Redis URL, and CORS
  origins are all declared now even though later phases consume some of them — one place to
  look for every knob.
- **Async database layer**
  - `app/db/base.py` — `DeclarativeBase` plus `UUIDPrimaryKeyMixin` (app-side `uuid4`) and
    `TimestampMixin` (timezone-aware `created_at` / `updated_at` with server defaults).
  - `app/db/session.py` — async engine over `asyncpg`, `async_sessionmaker`, and a
    `get_db()` dependency yielding a session per request.
- **Domain models** — `User`, `Organization`, `Workspace`, `WorkspaceMembership` with a
  `WorkspaceRole` enum (`owner` / `admin` / `member`) and a `ROLE_RANK` map for
  minimum-role checks.
- **Migrations** — Alembic configured with an **async** `env.py`; migration
  `34d09d87098c_phase1_foundation` creates all four tables, the `workspace_role` Postgres enum,
  and the indexes/unique constraints.
- **Local dev infra** — `docker-compose.yml` brings up Postgres 16, Redis 7, and MinIO.

### Decisions

- **UUID PKs, generated app-side** (`default=uuid.uuid4`), not DB sequences — IDs are known
  before flush, and there's no cross-table sequence contention or enumeration surface.
- **Workspace `slug` is unique per organization, not globally** — enforced by
  `uq_workspace_org_slug`. Two different orgs can both have a `design` workspace.
- **Membership is a first-class table with a role column**, not a simple many-to-many — the
  role belongs on the relationship, and Phase 2's RBAC reads it directly.
- **Enum stored by value** (`values_callable`) so the Postgres enum labels are the lowercase
  strings, not the Python member names.
- **No auto-generate in `env.py`'s online path** — migrations are written and reviewed by hand.
- **`redis_url` / JWT settings present but unused in Phase 1** — deliberately, so the config
  surface is stable from the start.

### Verify

```bash
docker compose up -d postgres redis
cd backend && pip install -e ".[dev]" && cp .env.example .env
alembic upgrade head        # creates users, organizations, workspaces, workspace_memberships
uvicorn app.main:app --reload
curl localhost:8000/health  # {"status":"ok"}
```

### Next

Phase 1 is done. Next: Phase 2 (auth, RBAC, and the core project/task domain).

---

## Phase 2 — Auth & Core Domain ✅

**Goal:** every user-facing concept the app is actually about — accounts, organizations,
workspaces, projects, tasks, labels, comments — with JWT auth and role-based access control
guarding every write.

### Delivered

- **Auth** — `app/core/security.py`: passlib bcrypt hashing, python-jose access/refresh JWT
  encode+decode with a `TokenType` check. `POST /api/auth/{register,login,refresh}`,
  `GET /api/auth/me`. `app/core/deps.py`'s `get_current_user` decodes the bearer token per request.
- **RBAC** — `require_workspace_role(min_role)`, `require_project_role(min_role)`, and
  `require_task_project_role(min_role)` — dependency factories that check the caller's
  membership role against a minimum via `ROLE_RANK`, scoped to workspace, project, or (by
  loading the task first) the task's own project. Kept out of router bodies so permission logic
  is reusable and unit-testable on its own.
- **Shared `Role` enum** (`app/models/roles.py`) — `owner` / `admin` / `member`, used at both
  workspace and project scope, backed by one Postgres enum (`member_role`).
- **Organizations & Workspaces** — create/list endpoints, workspace membership invite/list.
- **Projects** — `Project` + `ProjectMembership` (creator auto-seeded as Owner, same pattern as
  workspace creation), create/list + member invite.
- **Tasks** — title, description, `status` (todo/in_progress/in_review/done), `priority`
  (low/medium/high/urgent), assignee, due date, self-referential `parent_task_id` for subtasks,
  `position` for future Kanban ordering. Full CRUD + subtask listing.
- **Labels** — per-project, unique by name, many-to-many with tasks via `task_labels`.
- **Comments** — `task_id` / `author_id` / `body`. Mention parsing is deferred to Phase 5, once
  the notification system that would consume it exists.
- **Migration** `3690234f411b_phase2_core_domain` (chains onto `34d09d87098c`) creates the
  `member_role` enum and six new tables.
- **Tests** — auth, workspace RBAC, project/task RBAC, subtask validation, label uniqueness,
  comment create/list.

### Decisions

- **`Role` extracted to its own module instead of living on `Workspace`** — the moment a second
  thing (projects) needed the identical three-tier scheme, keeping it workspace-owned would have
  meant either duplicating the enum or having projects import from workspace's module for an
  unrelated concept. One shared enum, one shared Postgres type.
- **`require_task_project_role` returns the loaded `Task`**, not just the authorization result —
  route handlers that need both the permission check and the row (task detail, comment creation)
  get it in one dependency instead of fetching twice.
- **`Task.labels` is `lazy="selectin"`, deliberately** — see the bug below. Also incidentally
  avoids N+1 queries when listing a project's tasks with labels.
- **Mentions deferred, not dropped** — comments ship now; `@mention` parsing waits for Phase 5's
  notification system to actually have somewhere to deliver a mention to.

### Bug found and fixed

`Task.labels` (a default lazy-loaded relationship) was being accessed by Pydantic's response
serialization *after* the request's async DB session had already yielded control back —
FastAPI/Pydantic don't await SQLAlchemy's lazy-load machinery, so this raised `MissingGreenlet`
the first time a task-with-labels response was actually serialized. Fixed by setting
`lazy="selectin"` on the relationship, which eagerly loads labels in the same query rather than
lazily on attribute access.

### Verify

```bash
docker compose up -d postgres redis
cd backend && pip install -e ".[dev]" && cp .env.example .env
alembic upgrade head       # now at 3690234f411b
uvicorn app.main:app --reload
pytest                     # auth + RBAC + project/task/label/comment suite
```

### Next

**Phase 3 — Activity log & filtering:** an `ActivityLog` model recording who did what, plus
task filtering, sorting, search, and pagination query parameters.
