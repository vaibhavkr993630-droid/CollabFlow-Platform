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

**Phase 2 — Auth & core domain:** password hashing + JWT (register / login / refresh),
`get_current_user` dependency, RBAC dependencies built on `WorkspaceRole`, and the
Project / Task / Label / Comment models with their CRUD endpoints and tests.
