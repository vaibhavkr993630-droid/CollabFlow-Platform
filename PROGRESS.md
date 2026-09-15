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

Phase 2 is done. Next: Phase 3 (activity log, task filtering/sorting/search/pagination).

---

## Phase 3 — Activity Log & Search ✅

**Goal:** every state-changing action leaves an audit trail, and task lists stop being
"fetch everything and filter client-side" — real filtering, sorting, search, and pagination
on the server.

### Delivered

- **`ActivityLog`** (`app/models/activity.py`) — append-only, written only by
  `activity_service.log(...)`, called from inside project/task/label/comment services right
  after their write, in the **same transaction** (flushed, not committed separately — the log
  entry only persists if the action it describes actually commits). Covers: project created,
  member invited, task created/updated/deleted, comment added, label created.
- **Activity feeds** — `GET /api/projects/{project_id}/activity` and
  `GET /api/tasks/{task_id}/activity`, both paginated (`page`/`page_size`, capped at 100),
  newest first, RBAC'd through the existing `require_project_role` /
  `require_task_project_role` dependencies — no new permission logic needed.
- **Task list filtering/sorting/search/pagination** —
  `GET /api/projects/{project_id}/tasks` now takes `status`, `priority`, `assignee_id`,
  `label_id`, `search` (title `ILIKE`), `sort_by` (`created_at` / `due_date` / `priority` /
  `status` / `position` / `title`), `sort_order` (`asc`/`desc`), `page`, `page_size` — all
  optional. Response changed from a bare list to `{items, total, page, page_size}`.
- **Closed a gap from Phase 2**: `TaskUpdate.label_ids` (full-replace) — Phase 2 built labels
  but never wired up attaching them to a task, which would have made the new `label_id` filter
  untestable. Added now rather than left as dead functionality.

### Decisions

- **`task_id` FK is `ON DELETE SET NULL`, not `CASCADE`** — a task's activity history should
  outlive the task itself. Deleting a task nulls `task_id` on *every* historical entry that
  referenced it (not just a "task deleted" entry) — correct Postgres FK semantics, verified
  against a live migrated database, not assumed.
- **`activity_metadata`, not `metadata`** — `metadata` is reserved by SQLAlchemy's declarative
  `Base.metadata`; the column holds actual structured detail as JSONB (e.g. which fields changed
  on a `task_updated` row).
- **Sort fields, not a bare column name** — `sort_by` is a closed `TaskSortField` enum mapped to
  actual columns server-side, not a raw string interpolated into `ORDER BY`. Status/priority sort
  correctly by severity (`todo < in_progress < in_review < done`,
  `low < medium < high < urgent`) because that's the *definition order* of the underlying
  Postgres native enum, which Postgres uses for ordering — chosen deliberately to match.
- **Search is a plain `ILIKE` on title**, not `tsvector`/GIN — full scans are fine at this data
  scale; the brief's guidance was "add full-text search only if needed," and it isn't yet.
- **The `{items, total, page, page_size}` envelope is a breaking change to Phase 2's task-list
  contract**, made deliberately rather than adding pagination as a second endpoint alongside the
  old bare-list one.

### Verify

```bash
docker compose up -d postgres redis
cd backend && pip install -e ".[dev]" && cp .env.example .env
alembic upgrade head       # now at fd31448fb5dc
uvicorn app.main:app --reload
pytest                     # + activity log, filtering, sort, search, pagination
```

### Next

Phase 3 is done. Next: Phase 4 (WebSockets, Redis pub/sub, presence).

---

## Phase 4 — Real-Time ✅

**Goal:** task and comment changes, and who's currently looking at a project, propagate to
every connected client live — no polling.

### Delivered

- **`ConnectionManager`** (`app/ws/connection_manager.py`) — process-local registry of live
  WebSocket connections, keyed `(project_id, user_id) -> set of sockets` (a set, not one socket,
  since a user can hold multiple tabs open to the same project). Its only job is fanning a
  message out to local sockets; it never decides *what* to broadcast.
- **Redis client singleton** (`app/core/redis.py`), mirroring the DB engine singleton pattern.
- **Events** (`app/ws/events.py`) — every event (task created/updated/deleted, comment created,
  presence joined/left/snapshot) publishes to a per-project Redis channel
  (`project:{id}:events`) — never pushed to local sockets directly, even by the instance that
  triggered it.
- **`redis_listener.py`** — one long-lived background task, started in `main.py`'s `lifespan`,
  pattern-subscribed once to `project:*:events` (not one subscription per active project),
  relaying every message to `connection_manager.send_to_project`.
- **Presence** (`app/ws/presence.py`) — a Redis hash of `user_id -> open-connection-count` per
  project. `GET /api/projects/{project_id}/presence` exposes the same data over REST.
- **`WS /ws/projects/{project_id}`** — auth via `require_ws_project_role`, token as a `?token=`
  query param. On connect: presence snapshot sent to the new socket, *then* a `PRESENCE_JOINED`
  broadcast to everyone else. On disconnect: presence leave, `PRESENCE_LEFT` broadcast only if
  the count hits zero.
- **Task/comment writes now broadcast** after their DB transaction commits — a side effect that
  should only fire once the change is actually durable, unlike activity-log entries which log
  inside the same transaction.
- No new migration — Phase 4 state (presence, pub/sub) is entirely Redis-resident and
  intentionally never touches Postgres.

### Four bugs found and fixed (three of them concurrency-shaped)

1. **Presence-snapshot/self-join ordering race.** Publishing `PRESENCE_JOINED` before sending
   the new client its own snapshot let the Redis listener relay that join event back to the
   client before the direct snapshot send completed — a client could see itself "join" before
   knowing who else was online. Fixed by fully completing the snapshot send before publishing
   anything to Redis.
2. **WS auth wasn't overridable in tests.** A hand-rolled DB session inside the route bypassed
   the same `Depends(get_db)` pattern every HTTP route uses, so `tests/conftest.py`'s DB override
   had no effect — tests would have silently hit the real dev database. Fixed by discovering
   FastAPI/Starlette support raising `WebSocketException` from a `Depends()` (it closes the
   socket automatically, before accept), making auth a normal overridable dependency.
3. **Redis client singleton broke across pytest's per-test event loops** — identical root cause
   to the `NullPool` fix for the DB engine, but for `redis.asyncio.Redis`: a module-level
   singleton binds to whichever event loop first creates it, and pytest-asyncio hands each test a
   fresh loop. Fixed with an autouse fixture that closes and resets the singleton after every
   test.
4. **`send_to_project` iterated a live, mutable set while `await`ing inside the loop.**
   `websocket.send_json(...)` yields control back to the event loop; a real client disconnecting
   at that exact moment mutates the very dict/set structure being iterated, raising a
   "changed size during iteration" error. Fixed by snapshotting both the outer dict and each
   inner set into plain lists before the loop starts.

### Known simplifications

- WS auth token travels as `?token=...`, not a header — browsers' native WebSocket API can't set
  custom headers on the handshake. Tradeoff: the access token can appear in server access logs.
  A production system would issue a short-lived, single-use WS ticket via an authenticated REST
  call instead.
- Redis pub/sub fan-out is real, exercised on every event, but only one backend instance runs in
  this project's setup — the "reaches clients on a different instance" benefit is
  architecturally present, not something this deployment currently needs.
- `presence.leave`'s decrement-then-conditional-delete isn't a single atomic operation — a rare
  race between two concurrent disconnects at the exact moment a count hits zero could
  theoretically leave a stale zero-count entry. Not fixed with Lua scripting given the scope.
- No client-side reconnect/backoff logic yet — that's a Phase 7 (frontend) concern.

### Verify

```bash
docker compose up -d postgres redis
cd backend && pip install -e ".[dev]" && cp .env.example .env
alembic upgrade head       # unchanged — no new migration this phase
uvicorn app.main:app --reload
pytest                     # + WebSocket connect/auth/broadcast/presence
```

### Next

Phase 4 is done. Next: Phase 5 (notifications, Celery, email, reminders).

---

## Phase 5 — Notifications & Background Jobs ✅

**Goal:** every event a user actually cares about — being mentioned, assigned, invited, or
having a task due tomorrow — reaches them two ways: live in-app and via email, without the
request that triggered it waiting on either.

### Delivered

- **`Notification`** model — `user_id`, `type` (mention / task_assigned / workspace_invite /
  project_invite / task_due_soon), title/body, optional `project_id`/`task_id` (both
  `ON DELETE SET NULL`, same "history outlives the referenced entity" reasoning as Phase 3's
  `ActivityLog`), `read_at` nullable (unread = `NULL`, no separate boolean to drift out of sync).
- **`notification_service.create_and_dispatch`** — the single choke point every trigger calls
  through: persists + commits **as its own unit of work**, broadcasts live over
  `/ws/notifications`, and always queues a Celery email task regardless of whether the recipient
  is currently connected.
- **Real-time delivery generalized, not duplicated** — Phase 4's `run_redis_listener` became a
  generic `run_pattern_listener(pattern, extract_id, deliver)`; `main.py`'s lifespan now runs two
  instances of it (`project:*:events` → `ConnectionManager`, `user:*:notifications` →
  `NotificationConnectionManager`) instead of two different pieces of listener code.
- **`WS /ws/notifications`** — any authenticated user, no project membership check (deliberately
  separate from `/ws/projects/{id}`: a user should be notified even for a project they don't
  have open). REST: `GET /api/notifications` (paginated), `.../unread-count`,
  `POST .../{id}/read`, `POST .../read-all`.
- **Triggers wired into existing services**, not new endpoints: task assignment (create +
  reassignment, not self-assignment), workspace/project invite, and `@mention` parsing in
  comments (`app/core/mentions.py`, resolved by email — only notifies if the mentioned email
  belongs to an actual project member; a non-member mention is a silent no-op).
- **Celery** (`app/workers/celery_app.py`, Redis as broker+backend) + `send_notification_email`
  (blocking `smtplib`, fine since it only runs on a worker thread) + Celery Beat's
  `send_due_soon_reminders`, daily, matching tasks due **exactly tomorrow**.
- **MailDev** in `docker-compose.yml` for real local SMTP delivery without real credentials —
  viewable at `http://localhost:1080`.
- **Closes Phase 2's deferred mention-parsing item** — comments got `@mention` syntax now that
  there's a notification system to actually deliver one to.

### Decisions

- **Due-soon reminder matches `due_date == tomorrow` exactly, not "due within N days."** The job
  runs once daily; an exact match fires once per task, the day before it's due. A range match
  would re-notify the same still-open task every day the job runs until it's done — more
  thorough-looking, but actually a spam generator. Tradeoff, stated honestly: a task whose due
  date passes during job downtime never gets reminded.
- **`create_and_dispatch` commits on its own, not inside the caller's transaction** — a single
  comment can `@mention` several members, so one `create_comment` call may invoke it multiple
  times; each notification needs to succeed or fail independently, not roll back the others (or
  the comment itself) over one bad recipient lookup. Same reasoning as Phase 4's
  broadcast-after-commit, one layer further.
- **A genuine test-writing lesson, not a code bug:** early notification tests asserted the wrong
  count after an invite-then-assign flow, because inviting a user *also* creates a
  `project_invite` notification for that same recipient — both fire correctly. The app was right;
  the test assertions were checked against actual behavior before being corrected, not just
  adjusted until green.

### Bug found and fixed

**MailDev's `:latest` tag pulled a release candidate (3.0.0-rc.3) with a different, API-only
routing scheme** — the web UI and `/email` endpoint both 404'd even though the SMTP server and
container were genuinely healthy (confirmed via container logs before assuming misconfiguration).
Pinning to `2.1.0`, a known stable release, fixed it immediately. `:latest` on a fast-moving
dev-tool image is a real risk, not a hygiene nitpick.

### Verify

```bash
docker compose up -d postgres redis
cd backend && pip install -e ".[dev]" && cp .env.example .env
alembic upgrade head        # now at c18c809922b5
uvicorn app.main:app --reload &
celery -A app.workers.celery_app worker --loglevel=info &
celery -A app.workers.celery_app beat --loglevel=info &
pytest
```

### Next

**Phase 6 — Files:** MinIO integration, attachment upload/validation on tasks, file metadata in
the DB. MinIO has been in `docker-compose.yml` since Phase 1 but never actually used until now.
